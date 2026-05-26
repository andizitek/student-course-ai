import requests

OLLAMA_URL = "http://localhost:11434"


def embed_text(text: str, model: str) -> list[float]:
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": model, "input": text},
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    embeddings = data.get("embeddings", [])
    if not embeddings:
        raise RuntimeError("Keine Embeddings von Ollama erhalten.")
    return embeddings[0]


def chat_with_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    num_predict: int = 250,
) -> str:
    print(f"DEBUG OLLAMA: starte Anfrage an {model}", flush=True)

    final_user_prompt = f"""
{user_prompt}

WICHTIG:
Antworte direkt auf die Nutzerfrage.
Antworte immer auf Deutsch, außer die Nutzerfrage verlangt ausdrücklich Englisch.
Beantworte nur die gestellte Frage.
Füge keine weiteren Fragen oder Unterfragen hinzu.
Beende die Antwort nach der direkten Erklärung.
Wiederhole nicht den Lernkontext.
Wiederhole nicht den verfügbaren Kontext.
Wiederhole nicht die Aufgabenstellung.
Erfinde keine zusätzlichen Begriffe.

Form:
- Antworte kurz, aber vollständig.
- Verwende 1 kurzen Absatz oder maximal 3 Stichpunkte.
- Keine zusätzlichen Fragen.
- Keine langen Einleitungen.
""".strip()

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": 2048,
            },
        },
        timeout=180,
    )

    print("DEBUG OLLAMA: Antwort von Ollama erhalten", flush=True)

    response.raise_for_status()
    data = response.json()

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        return "Ollama hat keine Antwort zurückgegeben."

    return content