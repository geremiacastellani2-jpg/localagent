"""Memoria a lungo termine — livello 1: fatti strutturati.

Fatti espliciti, modificabili e verificabili (persone, preferenze, progetti).
Il richiamo qui è per parola chiave; il livello 2 (embedding + vettori) arriva
nella fase Memoria. Tenere i due livelli separati è una scelta di progetto.
"""

from __future__ import annotations

from ..db import connect
from .base import Tool, obj


def _remember(args: dict, _ctx: dict) -> str:
    subject = (args.get("subject") or "").strip()
    fact = (args.get("fact") or "").strip()
    if not subject or not fact:
        return "[errore] servono sia 'subject' sia 'fact'"
    source = (args.get("source") or "chat").strip()
    conn = connect()
    try:
        # se esiste già lo stesso soggetto+fatto, aggiorna il timestamp invece di duplicare
        existing = conn.execute(
            "SELECT id FROM memory_facts WHERE subject = ? AND fact = ?", (subject, fact)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memory_facts SET updated_at = datetime('now','localtime') WHERE id = ?",
                (existing["id"],),
            )
            conn.commit()
            return f"Già in memoria (fatto #{existing['id']}), aggiornato."
        cur = conn.execute(
            "INSERT INTO memory_facts (subject, fact, source) VALUES (?, ?, ?)",
            (subject, fact, source),
        )
        conn.commit()
        return f"Ricordato (fatto #{cur.lastrowid}): {subject} — {fact}"
    finally:
        conn.close()


def _recall(args: dict, _ctx: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = int(args.get("limit") or 10)
    conn = connect()
    try:
        if query:
            rows = conn.execute(
                "SELECT id, subject, fact, source, updated_at FROM memory_facts "
                "WHERE subject LIKE ? OR fact LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, subject, fact, source, updated_at FROM memory_facts "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    if not rows:
        return "Nessun ricordo pertinente."
    return "\n".join(f"#{r['id']} {r['subject']}: {r['fact']}  ({r['source']})" for r in rows)


def _forget(args: dict, _ctx: dict) -> str:
    fid = args.get("id")
    if fid is None:
        return "[errore] id mancante"
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM memory_facts WHERE id = ?", (int(fid),))
        conn.commit()
        return f"Dimenticato fatto #{fid}." if cur.rowcount else f"Nessun fatto #{fid}."
    finally:
        conn.close()


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
        description="Cerca nei fatti ricordati per rispondere a domande sull'utente.",
        parameters=obj(
            {
                "query": {"type": "string", "description": "Parole chiave da cercare."},
                "limit": {"type": "integer"},
            }
        ),
        run=_recall,
    ),
    Tool(
        name="forget_fact",
        description="Elimina un fatto dalla memoria dato il suo id.",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_forget,
    ),
]
