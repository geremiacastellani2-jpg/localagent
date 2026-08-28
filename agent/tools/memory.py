"""Memoria a lungo termine.

  Livello 1 (fatti):      righe esplicite in `memory_facts`, modificabili.
  Livello 2 (semantico):  indice vettoriale in `memory_vectors` per il richiamo
                          per significato (vedi semantic_memory.py).

`remember_fact` scrive il fatto e lo indicizza. `recall` cerca prima per
significato; se gli embedding non sono disponibili, ricade sulle parole chiave.
"""

from __future__ import annotations

from .. import semantic_memory as sem
from ..config import settings
from ..db import connect
from .base import Tool, obj


def _index_fact(fact_id: int, subject: str, fact: str) -> None:
    try:
        sem.index_text("fact", fact_id, f"{subject}: {fact}")
    except Exception:
        pass  # l'indicizzazione è best-effort; il fatto è comunque salvato


def _remember(args: dict, _ctx: dict) -> str:
    subject = (args.get("subject") or "").strip()
    fact = (args.get("fact") or "").strip()
    if not subject or not fact:
        return "[errore] servono sia 'subject' sia 'fact'"
    source = (args.get("source") or "chat").strip()
    conn = connect()
    try:
        existing = conn.execute(
            "SELECT id FROM memory_facts WHERE subject = ? AND fact = ?", (subject, fact)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memory_facts SET updated_at = datetime('now','localtime') WHERE id = ?",
                (existing["id"],),
            )
            conn.commit()
            _index_fact(existing["id"], subject, fact)
            return f"Già in memoria (fatto #{existing['id']}), aggiornato."
        cur = conn.execute(
            "INSERT INTO memory_facts (subject, fact, source) VALUES (?, ?, ?)",
            (subject, fact, source),
        )
        conn.commit()
        fact_id = cur.lastrowid
    finally:
        conn.close()
    _index_fact(fact_id, subject, fact)  # type: ignore[arg-type]
    return f"Ricordato (fatto #{fact_id}): {subject} — {fact}"


def _keyword_recall(query: str, limit: int) -> str:
    conn = connect()
    try:
        if query:
            rows = conn.execute(
                "SELECT id, subject, fact, source FROM memory_facts "
                "WHERE subject LIKE ? OR fact LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, subject, fact, source FROM memory_facts ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    if not rows:
        return "Nessun ricordo pertinente."
    return "\n".join(f"#{r['id']} {r['subject']}: {r['fact']}  ({r['source']})" for r in rows)


def _recall(args: dict, _ctx: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = int(args.get("limit") or 5)
    if not query:
        return _keyword_recall("", limit)

    results = sem.search(query, k=limit)
    if results:  # richiamo semantico riuscito
        lines = [f"{r['text']}  (sim {r['score']})" for r in results]
        return "Ricordi pertinenti:\n" + "\n".join(lines)
    # results è None (embedding non disponibili) o [] (indice vuoto): parole chiave
    return _keyword_recall(query, limit)


def _forget(args: dict, _ctx: dict) -> str:
    fid = args.get("id")
    if fid is None:
        return "[errore] id mancante"
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM memory_facts WHERE id = ?", (int(fid),))
        conn.commit()
    finally:
        conn.close()
    sem.delete_ref("fact", int(fid))
    return f"Dimenticato fatto #{fid}." if cur.rowcount else f"Nessun fatto #{fid}."


def _reindex(_args: dict, _ctx: dict) -> str:
    if not sem.available():
        return (
            "Embedding non disponibili: assicurati che Ollama sia attivo e che il "
            f"modello '{settings.embed_model}' sia scaricato (ollama pull nomic-embed-text)."
        )
    conn = connect()
    try:
        rows = conn.execute("SELECT id, subject, fact FROM memory_facts").fetchall()
    finally:
        conn.close()
    done = 0
    for r in rows:
        if sem.index_text("fact", r["id"], f"{r['subject']}: {r['fact']}"):
            done += 1
    return f"Reindicizzati {done}/{len(rows)} fatti nella memoria semantica."


TOOLS = [
    Tool(
        name="remember_fact",
        description=(
            "Salva un fatto durevole su una persona, una preferenza o un progetto. "
            "Usalo quando l'utente dice qualcosa che vale la pena ricordare a lungo termine."
        ),
        parameters=obj(
            {
                "subject": {"type": "string", "description": "A cosa/chi si riferisce il fatto."},
                "fact": {"type": "string", "description": "Il fatto da ricordare."},
                "source": {"type": "string", "description": "Da dove viene (default: chat)."},
            },
            required=["subject", "fact"],
        ),
        run=_remember,
    ),
    Tool(
        name="recall",
        description=(
            "Cerca nei ricordi per rispondere a domande sull'utente. Usa la ricerca "
            "semantica (per significato), con fallback alle parole chiave."
        ),
        parameters=obj(
            {
                "query": {"type": "string", "description": "Cosa vuoi ricordare."},
                "limit": {"type": "integer"},
            }
        ),
        run=_recall,
    ),
    Tool(
        name="forget_fact",
        description="Elimina un fatto dalla memoria (e dall'indice) dato il suo id.",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_forget,
    ),
    Tool(
        name="reindex_memory",
        description="Ricostruisce l'indice semantico da tutti i fatti salvati.",
        parameters=obj({}),
        run=_reindex,
    ),
]
