from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.config import load_course_config, list_courses
from app.core.retriever import retrieve
from app.core.llm import chat_with_ollama
from app.core.prompts import build_user_prompt, build_peer_review_prompt
from app.core.exporters import render_markdown_export
from app.core.student_memory import (
    build_learning_context,
    append_history,
    update_progress_from_question,
)

router = APIRouter()


class ChatRequest(BaseModel):
    course_id: str
    question: str
    mode: str = "explain"
    peer_text: str | None = None
    user_id: str = "default_user"


class ExportRequest(BaseModel):
    course_id: str
    question: str
    answer: str
    sources: list[dict]
    mode: str = "explain"


@router.get("/courses")
def courses():
    return {"courses": list_courses()}


@router.post("/chat")
def chat_endpoint(req: ChatRequest):
    try:
        cfg = load_course_config(req.course_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    prompt_path = Path("courses") / req.course_id / "system_prompt.md"
    if not prompt_path.exists():
        raise HTTPException(status_code=500, detail=f"Systemprompt fehlt: {prompt_path}")

    default_system_prompt = prompt_path.read_text(encoding="utf-8")
    if req.mode == "quiz_mc":
        system_prompt = """
    Du bist ein Generator für Multiple-Choice-Quizze.
    Gib ausschließlich gültiges JSON zurück.
    Gib keine Einleitung, keine Erklärung, keine Bestätigung, keine Meta-Antwort, kein Markdown und keine Codeblöcke aus.
    Verwende nur die in der Nutzeranweisung verlangten Felder.
    """.strip()
    else:
        system_prompt = default_system_prompt
    
    learning_context = build_learning_context(req.user_id, req.course_id)

    critical_hits = None

    if req.mode == "critical_ai_literacy":
        hits = retrieve(
            course_id=req.course_id,
            question=req.question,
            embedding_model=cfg["llm"]["embedding_model"],
            top_k=cfg["retrieval"]["top_k"],
            allowed_content_types=["material"],

        )

        critical_query = (
            req.question
            + " Critical AI Literacy künstliche Intelligenz KI-Antworten kritisch prüfen "
            + "Transparenz Scheingenauigkeit Materialbezug Quellenprüfung Verantwortung "
            + "Gruppenarbeit kollaboratives Lernen"
        )

        critical_hits = retrieve(
            course_id=req.course_id,
            question=critical_query,
            embedding_model=cfg["llm"]["embedding_model"],
            top_k=cfg["retrieval"]["top_k"],
            allowed_content_types=["critical"],
        )

    elif req.mode == "quiz_mc":
        hits = retrieve(
            course_id=req.course_id,
            question=req.question,
            embedding_model=cfg["llm"]["embedding_model"],
            top_k=cfg["retrieval"]["top_k"],
            allowed_content_types=["material"],
        )

    elif req.mode == "collaborative_work":
        hits = retrieve(
            course_id=req.course_id,
            question=req.question,
            embedding_model=cfg["llm"]["embedding_model"],
            top_k=cfg["retrieval"]["top_k"],
            allowed_content_types=["material", "critical"],
        )
    else:
        hits = retrieve(
            course_id=req.course_id,
            question=req.question,
            embedding_model=cfg["llm"]["embedding_model"],
            top_k=cfg["retrieval"]["top_k"],
            allowed_content_types=["material"],
        )

    if req.mode == "peer_review":
        user_prompt = build_peer_review_prompt(
            req.question,
            req.peer_text or "",
            hits,
            learning_context=learning_context,
        )
    else:
        user_prompt = build_user_prompt(
            req.question,
            hits,
            req.mode,
            learning_context=learning_context,
            critical_hits=critical_hits,
        )

    answer = chat_with_ollama(
        model=cfg["llm"]["chat_model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=cfg["response"]["temperature"],
    )

    source_hits = hits.copy()
    if critical_hits:
        source_hits = hits + critical_hits

    sources = [
        {
            "document": h["meta"].get("document"),
            "chunk_id": h["meta"].get("chunk_id"),
            "distance": h["distance"],
            "snippet": h["text"][:400],
            "source_pdf": h["meta"].get("source_pdf", ""),
            "page_start": h["meta"].get("page_start", -1),
            "page_end": h["meta"].get("page_end", -1),
            "course_id": req.course_id,
            "content_type": h["meta"].get("content_type", "material"),
        }
        for h in source_hits
    ]

    append_history(
        course_id=req.course_id,
        mode=req.mode,
        question=req.question,
        answer=answer,
        topics=[],
        user_id=req.user_id,
    )

    update_progress_from_question(
        question=req.question,
        answer=answer,
        user_id=req.user_id,
        course_id=req.course_id,
        mode=req.mode,
    )

    return {
        "answer": answer,
        "sources": sources,
        "used_mode": req.mode,
    }


@router.post("/export_markdown", response_class=PlainTextResponse)
def export_markdown(req: ExportRequest):
    return render_markdown_export(
        course_id=req.course_id,
        question=req.question,
        answer=req.answer,
        sources=req.sources,
        mode=req.mode,
    )