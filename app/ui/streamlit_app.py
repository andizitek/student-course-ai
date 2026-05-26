import json
import random
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st

from app.core.quiz_eval import mc_is_correct
from app.core.quiz_analytics import (
    append_quiz_result,
    compute_quiz_analytics,
    load_quiz_results,
    make_quiz_session_id,
)

API_URL = "http://127.0.0.1:8000"
USER_ID = "default_user"

st.set_page_config(page_title="Lokale Kurs-KI", layout="wide")
st.title("Lokale Kurs-KI")

if "quiz_data" not in st.session_state:
    st.session_state["quiz_data"] = None

if "quiz_generated_for_topic" not in st.session_state:
    st.session_state["quiz_generated_for_topic"] = ""

if "last_quiz_results" not in st.session_state:
    st.session_state["last_quiz_results"] = None

if "last_quiz_score" not in st.session_state:
    st.session_state["last_quiz_score"] = None

if "current_quiz_session_id" not in st.session_state:
    st.session_state["current_quiz_session_id"] = None


def load_courses():
    try:
        response = requests.get(f"{API_URL}/courses", timeout=30)
        response.raise_for_status()
        return response.json()["courses"]
    except Exception as exc:
        st.error(f"Kurse konnten nicht geladen werden: {exc}")
        return []


def load_local_json(path: str, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_profile():
    return load_local_json(
        f"student_data/{USER_ID}/profile.json",
        {
            "user_id": USER_ID,
            "language": "de",
            "preferred_style": "klar, strukturiert, fachlich",
            "level": "unbekannt",
            "preferred_term_mode": "de_with_en_in_brackets",
            "learning_goals": [],
        },
    )


def load_progress():
    return load_local_json(
        f"student_data/{USER_ID}/progress.json",
        {
            "seen_topics": [],
            "difficult_topics": [],
            "open_questions": [],
            "last_session_summary": "",
            "last_question": "",
        },
    )


def load_topic_names(course_id: str) -> list[str]:
    topic_map_path = Path("courses") / course_id / "topic_map.json"

    if not topic_map_path.exists():
        return []

    with topic_map_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return sorted([key for key in data.keys() if not key.startswith("_")])


def try_parse_quiz_json(text: str) -> dict | None:
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    return None


def shuffle_quiz_options(quiz_data: dict) -> dict:
    questions = quiz_data.get("questions", [])

    for item in questions:
        options = item.get("options", [])
        correct_index = item.get("correct_index", -1)

        if len(options) != 4 or correct_index not in [0, 1, 2, 3]:
            continue

        correct_option = options[correct_index]
        wrong_options = [opt for i, opt in enumerate(options) if i != correct_index]

        new_correct_index = random.randint(0, 3)
        new_options = wrong_options[:]
        new_options.insert(new_correct_index, correct_option)

        item["options"] = new_options
        item["correct_index"] = new_correct_index

    return quiz_data


def attach_sources_to_quiz(quiz_data: dict, sources: list[dict]) -> dict:
    questions = quiz_data.get("questions", [])
    if not questions or not sources:
        return quiz_data

    for idx, item in enumerate(questions):
        src = sources[min(idx, len(sources) - 1)]
        item["source"] = {
            "document": src.get("document", ""),
            "source_pdf": src.get("source_pdf", ""),
            "page": src.get("page_start", -1),
        }

    return quiz_data


def reset_progress():
    progress_path = Path(f"student_data/{USER_ID}/progress.json")
    default_progress = {
        "seen_topics": [],
        "difficult_topics": [],
        "open_questions": [],
        "last_session_summary": "",
        "last_question": "",
    }
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(default_progress, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def reset_profile():
    profile_path = Path(f"student_data/{USER_ID}/profile.json")
    default_profile = {
        "user_id": USER_ID,
        "language": "de",
        "preferred_style": "klar, strukturiert, fachlich",
        "level": "unbekannt",
        "preferred_term_mode": "de_with_en_in_brackets",
        "learning_goals": [],
    }
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(default_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_history():
    history_path = Path(f"student_data/{USER_ID}/history.jsonl")
    if history_path.exists():
        history_path.unlink()


def reset_quiz_results():
    quiz_path = Path(f"student_data/{USER_ID}/quiz_results.json")
    quiz_path.parent.mkdir(parents=True, exist_ok=True)
    quiz_path.write_text("[]", encoding="utf-8")


def build_pdf_http_url(course_id: str, source_pdf: str, page_start: int = -1) -> str:
    parts = [quote(part) for part in Path(source_pdf).parts]
    rel_path = "/".join(parts)
    base_url = f"{API_URL}/course_files/{quote(course_id)}/{rel_path}"
    if page_start != -1:
        return f"{base_url}#page={page_start}"
    return base_url


courses = load_courses()
if not courses:
    st.stop()

profile = load_profile()
progress = load_progress()

with st.sidebar:
    st.header("Lernprofil")

    st.write(f"**Sprache:** {profile.get('language', 'de')}")
    st.write(f"**Stil:** {profile.get('preferred_style', '-')}")
    st.write(f"**Niveau:** {profile.get('level', '-')}")

    goals = profile.get("learning_goals", [])
    st.subheader("Lernziele")
    if goals:
        for goal in goals:
            st.markdown(f"- {goal}")
    else:
        st.caption("Noch keine Lernziele eingetragen.")

    seen_topics = progress.get("seen_topics", [])
    st.subheader("Bearbeitete Themen")
    if seen_topics:
        for topic in seen_topics:
            st.markdown(f"- {topic}")
    else:
        st.caption("Noch keine Themen gespeichert.")

    difficult_topics = progress.get("difficult_topics", [])
    st.subheader("Schwierige Themen")
    if difficult_topics:
        for topic in difficult_topics:
            st.markdown(f"- {topic}")
    else:
        st.caption("Noch keine schwierigen Themen gespeichert.")

    open_questions = progress.get("open_questions", [])
    st.subheader("Offene Fragen")
    if open_questions:
        for item in open_questions:
            st.markdown(f"- {item}")
    else:
        st.caption("Noch keine offenen Fragen gespeichert.")

    last_summary = progress.get("last_session_summary", "")
    st.subheader("Letzte Sitzung")
    if last_summary:
        st.write(last_summary)
    else:
        st.caption("Noch keine Sitzung gespeichert.")

    analytics = compute_quiz_analytics(USER_ID)

    st.subheader("Quiz-Analytics")
    st.write(f"**Bearbeitete Quizfragen:** {analytics['total_quiz_items']}")
    st.write(f"**Richtig:** {analytics['correct_count']}")
    st.write(f"**Falsch:** {analytics['incorrect_count']}")
    st.write(f"**Trefferquote:** {analytics['accuracy']:.0%}")

    if analytics["difficult_topics_from_quiz"]:
        st.markdown("**Im Quiz eher unsichere Themen**")
        for topic in analytics["difficult_topics_from_quiz"]:
            st.markdown(f"- {topic}")
    else:
        st.caption("Noch keine quizbasierten schwierigen Themen erkannt.")

    sessions = analytics.get("sessions", {})
    if sessions:
        st.subheader("Letzte Quizdurchgänge")
        for _, session_data in list(sessions.items())[-3:]:
            st.write(
                f"{session_data['topic']}: "
                f"{session_data['correct']}/{session_data['total']} richtig"
            )

    st.markdown("---")
    st.subheader("Verlauf verwalten")

    if st.button("Lernverlauf löschen", use_container_width=True):
        delete_history()
        st.success("history.jsonl wurde gelöscht.")

    if st.button("Fortschritt zurücksetzen", use_container_width=True):
        reset_progress()
        st.success("progress.json wurde zurückgesetzt.")

    if st.button("Quiz-Analytics zurücksetzen", use_container_width=True):
        reset_quiz_results()
        st.success("quiz_results.json wurde zurückgesetzt.")

    if st.button("Alles zurücksetzen", use_container_width=True):
        delete_history()
        reset_progress()
        reset_profile()
        reset_quiz_results()
        st.success("Profil, Fortschritt, Verlauf und Quizdaten wurden zurückgesetzt.")

course_map = {f"{c['course_name']} ({c['course_id']})": c["course_id"] for c in courses}
selected_label = st.selectbox("Kurs wählen", list(course_map.keys()))
course_id = course_map[selected_label]

mode = st.selectbox(
    "Modus",
    [
        "explain",
        "summarize",
        "quiz",
        "quiz_mc",
        "flashcards",
        "study_guide",
        "group_prep",
        "discussion",
        "peer_review",
        "group_summary",
        "critical_ai_literacy",
        "collaborative_work",
    ],
    index=0,
)

if mode == "quiz_mc":
    st.markdown("## Multiple-Choice-Quiz")

    topic_options = load_topic_names(course_id)

    selected_topic = st.selectbox(
        "Thema für das Quiz",
        options=topic_options if topic_options else ["Kein Thema verfügbar"],
    )

    custom_topic = st.text_input("Oder eigenes Thema eingeben (optional)")
    quiz_topic = custom_topic.strip() if custom_topic.strip() else selected_topic

    num_questions = st.selectbox(
        "Anzahl der Fragen",
        options=[3, 5, 10],
        index=1,
    )

    col_quiz_1, col_quiz_2 = st.columns(2)

    with col_quiz_1:
        if st.button("Neues Quiz generieren", use_container_width=True):
            if not quiz_topic or quiz_topic == "Kein Thema verfügbar":
                st.warning("Bitte zuerst ein Thema auswählen oder eingeben.")
            else:
                quiz_request = (
                    f"Erstelle {num_questions} Multiple-Choice-Fragen zum Thema "
                    f"'{quiz_topic}' auf Basis der Kursmaterialien."
                )

                payload = {
                    "course_id": course_id,
                    "question": quiz_request,
                    "mode": "quiz_mc",
                    "user_id": USER_ID,
                }

                with st.spinner("Quiz wird erzeugt ..."):
                    response = requests.post(
                        f"{API_URL}/chat",
                        json=payload,
                        timeout=900,
                    )
                    response.raise_for_status()
                    data = response.json()

                answer = data["answer"]
                quiz_data = try_parse_quiz_json(answer)

                if quiz_data is None:
                    st.error("Die Quiz-Ausgabe konnte nicht als JSON gelesen werden.")
                    st.code(answer)
                    st.session_state["quiz_data"] = None
                else:
                    quiz_data = shuffle_quiz_options(quiz_data)
                    quiz_data = attach_sources_to_quiz(quiz_data, data.get("sources", []))

                    st.session_state["quiz_data"] = quiz_data
                    st.session_state["quiz_generated_for_topic"] = quiz_topic
                    st.session_state["current_quiz_session_id"] = make_quiz_session_id(
                        course_id, quiz_topic
                    )
                    st.session_state["last_quiz_results"] = None
                    st.session_state["last_quiz_score"] = None
                    st.success("Quiz wurde erzeugt.")

    with col_quiz_2:
        if st.button("Quiz zurücksetzen", use_container_width=True):
            st.session_state["quiz_data"] = None
            st.session_state["quiz_generated_for_topic"] = ""
            st.session_state["current_quiz_session_id"] = None
            st.session_state["last_quiz_results"] = None
            st.session_state["last_quiz_score"] = None
            st.success("Quiz wurde zurückgesetzt.")

question = ""
if mode != "quiz_mc":
    question = st.text_area(
        "Frage an die Kurs-KI",
        height=140,
        placeholder="Stelle hier deine Frage zu den Kursmaterialien ...",
    )

peer_text = ""
if mode == "peer_review":
    peer_text = st.text_area(
        "Text für Peer-Review",
        height=200,
        placeholder="Füge hier einen studentischen Text oder Entwurf ein ...",
    )

if mode != "quiz_mc" and st.button("Antwort erzeugen", use_container_width=True):
    if not question.strip():
        st.warning("Bitte zuerst eine Frage eingeben.")
        st.stop()

    payload = {
        "course_id": course_id,
        "question": question,
        "mode": mode,
        "user_id": USER_ID,
    }

    if mode == "peer_review":
        payload["peer_text"] = peer_text

    with st.spinner("Antwort wird erzeugt ..."):
        response = requests.post(
            f"{API_URL}/chat",
            json=payload,
            timeout=900,
        )
        response.raise_for_status()
        data = response.json()

    st.session_state["last_answer"] = data
    st.session_state["last_question"] = question
    st.session_state["last_mode"] = mode
    st.session_state["last_course_id"] = course_id

if "last_answer" in st.session_state and mode != "quiz_mc":
    data = st.session_state["last_answer"]

    st.subheader("Antwort")
    st.write(data["answer"])

    st.subheader("Verwendete Quellen")
    if not data["sources"]:
        st.info("Es wurden keine Quellen aus dem lokalen Index gefunden.")
    else:
        for src in data["sources"]:
            title = f"{src['document']} · {src['chunk_id']}"
            with st.expander(title):
                source_pdf = (src.get("source_pdf") or "").strip()
                page_start = src.get("page_start", -1)
                page_end = src.get("page_end", -1)
                src_course_id = src.get(
                    "course_id",
                    st.session_state.get("last_course_id", course_id),
                )

                if source_pdf:
                    pdf_url = build_pdf_http_url(src_course_id, source_pdf, page_start)

                    st.markdown(f"**Originalquelle:** `{source_pdf}`")

                    if page_start != -1:
                        if page_end != -1 and page_end != page_start:
                            st.markdown(f"**Seiten:** {page_start}-{page_end}")
                        else:
                            st.markdown(f"**Seite:** {page_start}")

                    st.markdown(f"[PDF öffnen]({pdf_url})")
                else:
                    st.caption("Keine Original-PDF hinterlegt.")

                st.write(src["snippet"])
                st.caption(f"Distanzwert: {src['distance']}")

    col1, col2 = st.columns(2)

    with col1:
        export_md = requests.post(
            f"{API_URL}/export_markdown",
            json={
                "course_id": st.session_state["last_course_id"],
                "question": st.session_state["last_question"],
                "answer": data["answer"],
                "sources": data["sources"],
                "mode": st.session_state["last_mode"],
            },
            timeout=60,
        ).text

        st.download_button(
            "Als Markdown exportieren",
            data=export_md,
            file_name=f"{st.session_state['last_course_id']}_{st.session_state['last_mode']}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col2:
        st.download_button(
            "Als JSON exportieren",
            data=json.dumps(data, ensure_ascii=False, indent=2),
            file_name=f"{st.session_state['last_course_id']}_{st.session_state['last_mode']}.json",
            mime="application/json",
            use_container_width=True,
        )

quiz_data = st.session_state.get("quiz_data")

if mode == "quiz_mc" and quiz_data:
    st.markdown("---")
    st.subheader("Quiz bearbeiten")

    quiz_topic_display = quiz_data.get(
        "topic",
        st.session_state.get("quiz_generated_for_topic", "Unbekannt"),
    )
    questions = quiz_data.get("questions", [])

    st.write(f"**Thema:** {quiz_topic_display}")

    valid_questions = []

    if not questions:
        st.info("Keine Fragen im Quiz gefunden.")
    else:
        for idx, item in enumerate(questions, start=1):
            st.markdown(f"### Frage {idx}")
            st.write(item.get("question", ""))

            options = item.get("options", [])
            if len(options) != 4:
                st.warning(f"Frage {idx} hat nicht genau 4 Antwortoptionen.")
                continue

            valid_questions.append((idx, item))

            st.radio(
                f"Antwort für Frage {idx}",
                options=range(len(options)),
                format_func=lambda i, opts=options: opts[i],
                key=f"quiz_radio_{idx}",
            )

        if valid_questions and st.button("Alle Antworten prüfen und speichern"):
            correct_total = 0
            evaluated_items = []
            quiz_session_id = st.session_state.get(
                "current_quiz_session_id",
                "unknown_session",
            )

            for idx, item in valid_questions:
                options = item.get("options", [])
                correct_index = item.get("correct_index", -1)
                selected_option = st.session_state.get(f"quiz_radio_{idx}", None)

                if selected_option is None:
                    continue

                is_correct = mc_is_correct(selected_option, correct_index)

                append_quiz_result(
                    quiz_session_id=quiz_session_id,
                    course_id=course_id,
                    topic=quiz_topic_display,
                    question=item.get("question", ""),
                    options=options,
                    correct_index=correct_index,
                    selected_index=selected_option,
                    is_correct=is_correct,
                    user_id=USER_ID,
                )

                if is_correct:
                    correct_total += 1

                evaluated_items.append(
                    {
                        "question": item.get("question", ""),
                        "options": options,
                        "selected_index": selected_option,
                        "correct_index": correct_index,
                        "is_correct": is_correct,
                        "source": item.get("source", {}),
                    }
                )

            st.session_state["last_quiz_results"] = evaluated_items
            st.session_state["last_quiz_score"] = {
                "correct": correct_total,
                "total": len(evaluated_items),
            }

            st.success(
                f"Quiz gespeichert. Richtig: {correct_total} von {len(evaluated_items)}."
            )

last_quiz_results = st.session_state.get("last_quiz_results")
last_quiz_score = st.session_state.get("last_quiz_score")

if mode == "quiz_mc" and last_quiz_results and last_quiz_score:
    st.markdown("---")
    st.subheader("Ergebnis des letzten Quizdurchgangs")
    st.write(
        f"**Richtig:** {last_quiz_score['correct']} "
        f"von {last_quiz_score['total']}"
    )

    for idx, item in enumerate(last_quiz_results, start=1):
        status = "✅" if item["is_correct"] else "❌"
        st.markdown(f"**Frage {idx}: {status}**")
        st.write(item["question"])

        source = item.get("source", {})
        document = source.get("document", "")
        source_pdf = source.get("source_pdf", "")
        page = source.get("page", -1)

        if source_pdf.endswith(".md"):
            source_pdf = source_pdf[:-3] + ".pdf"

        if source_pdf and not source_pdf.startswith("source_pdfs/"):
            source_pdf = f"source_pdfs/{Path(source_pdf).name}"

        if source_pdf:
            pdf_url = build_pdf_http_url(course_id, source_pdf, page)

            if document:
                if page != -1:
                    st.caption(f"Quelle: {document}, S. {page}")
                else:
                    st.caption(f"Quelle: {document}")

            st.markdown(f"[PDF zur Quelle öffnen]({pdf_url})")

        elif document:
            if page != -1:
                st.caption(f"Quelle: {document}, S. {page}")
            else:
                st.caption(f"Quelle: {document}")

        selected_index = item["selected_index"]
        correct_index = item["correct_index"]
        options = item["options"]

        if 0 <= selected_index < len(options):
            st.write(f"**Deine Antwort:** {options[selected_index]}")
        if 0 <= correct_index < len(options):
            st.write(f"**Richtige Antwort:** {options[correct_index]}")

if mode == "quiz_mc" and last_quiz_results and last_quiz_score:
    st.markdown("---")
    st.subheader("Was war falsch?")

    wrong_items = [item for item in last_quiz_results if not item["is_correct"]]

    if wrong_items:
        for idx, item in enumerate(wrong_items, start=1):
            st.markdown(f"**Fehler {idx}**")
            st.write(item["question"])

            selected_index = item["selected_index"]
            correct_index = item["correct_index"]
            options = item["options"]

            if 0 <= selected_index < len(options):
                st.write(f"**Deine Antwort:** {options[selected_index]}")
            if 0 <= correct_index < len(options):
                st.write(f"**Richtige Antwort:** {options[correct_index]}")
    else:
        st.write("In diesem Quizdurchgang war keine Frage falsch.")

quiz_results = load_quiz_results(USER_ID)

if mode == "quiz_mc":
    st.markdown("---")
    st.subheader("Letzte 5 gespeicherte Quizantworten")

    if quiz_results:
        for item in reversed(quiz_results[-5:]):
            status = "✅" if item.get("is_correct") else "❌"
            st.write(
                f"{status} {item.get('topic', 'Unbekannt')} – "
                f"{item.get('question', '')}"
            )
    else:
        st.caption("Noch keine Quiz-Ergebnisse gespeichert.")

st.markdown("---")
st.markdown("### Hinweise für Gruppenarbeit")
st.markdown(
    """
- **group_prep** für Gruppenbeiträge vorbereiten
- **discussion** für Diskussionsfragen und Perspektiven
- **peer_review** für Rückmeldung zu Textentwürfen
- **group_summary** für einen kompakten Beitrag der Gruppe
"""
)