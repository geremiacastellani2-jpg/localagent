"""Strumenti per le note (archivio locale SQLite)."""

from __future__ import annotations

from ..db import connect
from .base import Tool, obj


def _add_note(args: dict, _ctx: dict) -> str:
    text = (args.get("text") or "").strip()
    if not text:
        return "[errore] testo della nota mancante"
    tags = (args.get("tags") or "").strip()
    conn = connect()
    try:
        cur = conn.execute("INSERT INTO notes (text, tags) VALUES (?, ?)", (text, tags))
        conn.commit()
        return f"Nota #{cur.lastrowid} salvata."
    finally:
        conn.close()


def _list_notes(args: dict, _ctx: dict) -> str:
    query = (args.get("query") or "").strip()
    limit = int(args.get("limit") or 20)
    conn = connect()
    try:
        if query:
            rows = conn.execute(
                "SELECT id, text, tags, created_at FROM notes "
                "WHERE text LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, text, tags, created_at FROM notes ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    if not rows:
        return "Nessuna nota trovata."
    return "\n".join(
        f"#{r['id']} [{r['created_at']}] {r['text']}" + (f"  ({r['tags']})" if r["tags"] else "")
        for r in rows
    )


def _delete_note(args: dict, _ctx: dict) -> str:
    note_id = args.get("id")
    if note_id is None:
        return "[errore] id mancante"
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (int(note_id),))
        conn.commit()
        return f"Eliminata nota #{note_id}." if cur.rowcount else f"Nessuna nota #{note_id}."
    finally:
        conn.close()


TOOLS = [
    Tool(
        name="add_note",
        description="Salva una nota testuale nell'archivio locale.",
        parameters=obj(
            {
                "text": {"type": "string", "description": "Il contenuto della nota."},
                "tags": {"type": "string", "description": "Etichette separate da spazio (facoltativo)."},
            },
            required=["text"],
        ),
        run=_add_note,
    ),
    Tool(
        name="list_notes",
        description="Elenca o cerca le note salvate.",
        parameters=obj(
            {
                "query": {"type": "string", "description": "Testo da cercare (facoltativo)."},
                "limit": {"type": "integer", "description": "Numero massimo di risultati."},
            }
        ),
        run=_list_notes,
    ),
    Tool(
        name="delete_note",
        description="Elimina una nota dato il suo id.",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_delete_note,
    ),
]
