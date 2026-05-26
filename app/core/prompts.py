def _format_hits(hits: list[dict], label_prefix: str = "Kontext") -> str:
    if not hits:
        return "Kein passender Kontext gefunden."

    blocks = []
    for i, hit in enumerate(hits, start=1):
        doc = hit["meta"].get("document", "unbekanntes_dokument")
        page_start = hit["meta"].get("page_start", -1)
        page_info = f", Seite {page_start}" if page_start != -1 else ""
        blocks.append(f"[{label_prefix} {i} | {doc}{page_info}]\n{hit['text']}")

    return "\n\n".join(blocks)


def build_user_prompt(
    question: str,
    hits: list[dict],
    mode: str,
    learning_context: str = "",
    critical_hits: list[dict] | None = None,
) -> str:
    context = _format_hits(hits, "Fachkontext")
    critical_context = _format_hits(critical_hits or [], "Reflexionskontext")
# Sonderfall: critical_ai_literacy mit getrenntem Fach- und Reflexionskontext
    if mode == "critical_ai_literacy":
        return f"""
{learning_context}

Konkrete Nutzerfrage:
{question}

Fachkontext:
{context}

Zusätzlicher Reflexionskontext:
{critical_context}

Arbeitsauftrag:
Beantworte die konkrete Nutzerfrage zuerst fachlich und direkt.
Ordne die Antwort danach kurz kritisch ein.
Nutze den Fachkontext für die eigentliche Antwort.
Nutze den Reflexionskontext nur für relevante Grenzen, Risiken oder Unsicherheiten.
Ignoriere Kontexte, die zur konkreten Frage nicht passen.

Form:
1. Direkte Antwort:
   Beantworte die Frage in 2–4 Sätzen.

2. Kritische Einordnung:
   Nenne 1–3 Punkte, die bei der Nutzung, Bewertung oder Weiterverwendung kritisch zu beachten sind.

3. Bezug zum Material:
   Nenne kurz, auf welches Dokument oder welche Seite sich die Antwort stützt.

Wichtige Regeln:
- Keine Meta-Antwort über den KI-Einsatz, außer die Nutzerfrage fragt ausdrücklich danach.
- Verwende niemals Formulierungen wie "Fachkontext 1", "Fachkontext 2" oder "Reflexionskontext 1".
- Nenne stattdessen den Dokumentnamen direkt, z. B. "im Goldstandard-Dokument" oder "in critical_ai_literacy.md".
- Keine Aufforderung, die Frage zu präzisieren, wenn eine fachliche Antwort im Kontext möglich ist.
- Nutze nur den bereitgestellten Kontext.
- Wenn die Antwort nicht im Kontext steht, sage das offen.
- Antworte auf Deutsch.
""".strip()

    mode_instruction = {
        "explain": "Erkläre die Antwort didaktisch und verständlich in klaren Schritten.",
        "summarize": "Gib eine knappe strukturierte Zusammenfassung.",
        "quiz": "Erkläre kurz und stelle danach 3 Quizfragen ohne sofortige Lösung.",
        "quiz_mc": "Erstelle die angeforderte Anzahl von Multiple-Choice-Fragen zum Thema auf Basis des bereitgestellten Materials. Nutze ausschließlich den bereitgestellten Kontext. Die richtige Antwort muss inhaltlich eindeutig mit dem Material übereinstimmen. Wenn eine Frage nicht eindeutig aus dem Material ableitbar ist, stelle sie nicht. Gib genau 4 Antwortoptionen pro Frage an. Die richtige Antwort darf nicht immer an derselben Position stehen. Verteile die richtigen Antworten über unterschiedliche Positionen. Antworte ausschließlich als gültiges JSON und ohne Einleitung, ohne Erklärung, ohne Markdown. Format: {\"topic\": \"...\", \"questions\": [{\"question\": \"...\", \"options\": [\"...\", \"...\", \"...\", \"...\"], \"correct_index\": 1}]}.",
        "flashcards": """
Erstelle jetzt genau 5 Lernkarten aus dem bereitgestellten Kontext.

Format:
1. Vorderseite: ...
   Rückseite: ...

2. Vorderseite: ...
   Rückseite: ...

Regeln:
- Nutze nur den bereitgestellten Kontext.
- Keine Einleitung.
- Keine Bestätigung.
- Keine Meta-Antwort wie "Verstanden".
- Fordere keinen weiteren Kontext an.
- Jede Vorderseite enthält einen Begriff oder eine kurze Frage.
- Jede Rückseite enthält eine kurze Erklärung mit maximal 2 Sätzen.
- Wenn möglich, nenne in der Rückseite kurz das Bezugsdokument oder die Seite.
""",
        "study_guide": "Erstelle einen Lernleitfaden mit den wichtigsten Punkten, Reihenfolge und typischen Missverständnissen.",
        "group_prep": """
Bereite die konkrete Nutzerfrage für eine Lerngruppe vor.

Format:
1. Kurze Kernaussage
2. Drei zentrale Punkte aus dem Material
3. Zwei Diskussionsfragen
4. Eine offene Unsicherheit oder Prüffrage
5. Ein konkreter Arbeitsauftrag für die Gruppe

Regeln:
- Beginne direkt mit der Gruppenarbeits-Vorbereitung.
- Keine Meta-Antwort über deine Rolle.
- Keine Formulierungen wie "Als Assistent...".
- Fordere keinen weiteren Kontext an.
- Nutze nur den bereitgestellten Kontext.
- Wenn möglich, nenne kurz das Bezugsdokument oder die Seite.
- Antworte auf Deutsch.
""",
        "discussion": """
Erzeuge direkt Material für eine Gruppendiskussion zur konkreten Nutzerfrage.

Format:
1. Ausgangspunkt der Diskussion:
   Eine kurze fachliche Erklärung in 2–3 Sätzen.

2. Perspektive A:
   Eine mögliche Position oder Deutung aus dem Material.

3. Perspektive B:
   Eine zweite mögliche Position, Grenze oder Gegenperspektive.

4. Kritische Rückfragen:
   - Frage 1
   - Frage 2

5. Kontroverser Punkt:
   Ein Punkt, über den die Gruppe sinnvoll diskutieren kann.

Regeln:
- Beginne direkt mit dem Diskussionsmaterial.
- Keine Meta-Antwort über deine Rolle.
- Keine Formulierungen wie "Als Assistent...".
- Fordere keinen weiteren Kontext an.
- Nutze nur den bereitgestellten Kontext.
- Wenn möglich, nenne kurz das Bezugsdokument oder die Seite.
- Antworte auf Deutsch.
""",
        "group_summary": "Formuliere einen kompakten Gruppenbeitrag mit Kernaussage, Begriffen, Relevanz und offener Rückfrage.",
        "collaborative_work":  """
Unterstütze die Gruppe bei einem kollaborativen Arbeitsprozess zur konkreten Nutzerfrage.

Wichtig:
Die Antwort ist eine Arbeitsanleitung an die Gruppe.
Sie soll nicht die Aufgabe vollständig lösen.
Sie soll keine längere inhaltliche Analyse schreiben.

Format:
1. Gemeinsames Ziel:
   Formuliere in 1 Satz, worauf ihr als Gruppe hinarbeitet.

2. Erste Arbeitsschritte:
   - Lest die wichtigsten Textstellen.
   - Markiert zentrale Aussagen.
   - Sammelt offene Fragen.
   - Prüft, welche Aussagen wirklich belegt sind.

3. Zusammenarbeit:
   Beschreibe kurz, wie ihr gemeinsam arbeiten könnt, ohne feste Rollen vorzuschreiben.

4. Prüffragen:
   - Was ist im Material direkt belegt?
   - Was ist Interpretation?
   - Was fehlt oder bleibt unklar?
   - Welche Aussagen müsst ihr mit Originalquellen prüfen?

5. Gemeinsames Ergebnis:
   Beschreibe kurz, wie ihr aus euren Notizen eine gemeinsame Antwort formuliert.

Regeln:
- Sprich die Gruppe direkt mit "ihr" an.
- Gib keine fertige Endantwort als Essay.
- Löse die Aufgabe nicht vollständig.
- Nenne keine "Fachkontext 1", "Fachkontext 2" oder ähnliche Kontextnummern.
- Wenn du Quellen nennst, nenne den Dokumentnamen natürlich im Satz.
- Keine Meta-Antwort über deine Rolle.
- Keine Formulierungen wie "Als Assistent".
- Keine Wiederholungen zwischen Arbeitsschritten, Zusammenarbeit und Zusammenführung.
- Antworte kurz, klar und auf Deutsch.
""",

    }.get(mode, "Erkläre die Antwort didaktisch und verständlich in klaren Schritten.")

    return f"""
{learning_context}

Aufgabe:
{question}

Arbeitsmodus:
{mode_instruction}

Verfügbarer Kontext:
{context}

Wichtige Regeln:
- Nutze nur den bereitgestellten Kontext.
- Wenn etwas im Material nicht klar belegt ist, sage das offen.
- Verwende im Fließtext keine Platzhalter wie "Quelle 1" oder "Quelle 2".
- Nenne stattdessen direkt den Dokumentnamen, wenn du auf Kontext Bezug nimmst.
- Wenn Seiten vorhanden sind, nenne sie als (Dokumentname, S. X).
- Keine erfundenen bibliografischen Angaben.
- Keine separate Literaturliste am Ende, wenn die Quellen im Text bereits genannt sind.
- Beginne neue Nummerierungen immer wieder bei 1.
""".strip()


def build_peer_review_prompt(
    question: str,
    peer_text: str,
    hits: list[dict],
    learning_context: str = "",
) -> str:
    context = _format_hits(hits, "Kontext")

    return f"""
{learning_context}

Aufgabe:
{question}

Zu begutachtender Text:
{peer_text}

Verfügbarer Kontext:
{context}

Bitte gib konstruktives Peer-Feedback:
1. Was ist gelungen?
2. Was ist unklar oder ausbaufähig?
3. Wo fehlt Materialbezug?
4. Welche Verbesserungsvorschläge ergeben sich?

Wichtige Regeln:
- Nutze nur den bereitgestellten Kontext.
- Keine erfundenen Quellen.
- Nenne Dokumentnamen direkt statt "Quelle 1" usw.
""".strip()
