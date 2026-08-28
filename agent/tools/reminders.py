"""Strumenti per i promemoria (archivio locale SQLite).

Nota: in questa fase i promemoria vengono salvati e consultati. Lo scheduler che
li fa "scattare" (notifiche proattive) arriva nella fase Proattività.
"""

from __future__ import annotations

from ..calendar_store import normalize_dt
from ..db import connect
from .base import Tool, obj


def _add_reminder(args: dict, _ctx: dict) -> str:
    text = (args.get("text") or "").strip()
    if not text:
        return "[errore] testo del promemoria mancante"
    due_at = (args.get("due_at") or "").strip() or None
    if due_at:
        try:
            due_at = normalize_dt(due_at)  # ISO canonico: confrontabile dallo scheduler
        except ValueError:
            return "[errore] scadenza non valida: usa ISO 8601 (es. 2026-08-29T09:00)"
    conn = connect()
    try:
        cur = conn.execute("INSERT INTO reminders (text, due_at) VALUES (?, ?)", (text, due_at))
        conn.commit()
        when = f" (scadenza {due_at})" if due_at else ""
        return f"Promemoria #{cur.lastrowid} creato{when}."
    finally:
        conn.close()


def _list_reminders(args: dict, _ctx: dict) -> str:
    include_done = bool(args.get("include_done"))
    conn = connect()
    try:
        sql = "SELECT id, text, due_at, done FROM reminders"
        if not include_done:
            sql += " WHERE done = 0"
        sql += " ORDER BY (due_at IS NULL), due_at ASC, id ASC"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()
    if not rows:
        return "Nessun promemoria."
    out = []
    for r in rows:
        mark = "✓" if r["done"] else "○"
        when = f" — {r['due_at']}" if r["due_at"] else ""
        out.append(f"{mark} #{r['id']} {r['text']}{when}")
    return "\n".join(out)


def _complete_reminder(args: dict, _ctx: dict) -> str:
    rid = args.get("id")
    if rid is None:
        return "[errore] id mancante"
    conn = connect()
    try:
        cur = conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (int(rid),))
        conn.commit()
        return f"Promemoria #{rid} completato." if cur.rowcount else f"Nessun promemoria #{rid}."
    finally:
        conn.close()


TOOLS = [
    Tool(
        name="add_reminder",
        description="Crea un promemoria, con scadenza opzionale.",
        parameters=obj(
            {
                "text": {"type": "string", "description": "Cosa ricordare."},
                "due_at": {
                    "type": "string",
                    "description": "Scadenza in formato ISO, es. 2026-08-29 09:00 (facoltativo).",
                },
            },
            required=["text"],
        ),
        run=_add_reminder,
    ),
    Tool(
        name="list_reminders",
        description="Elenca i promemoria aperti (o tutti).",
        parameters=obj({"include_done": {"type": "boolean"}}),
        run=_list_reminders,
    ),
    Tool(
        name="complete_reminder",
        description="Segna un promemoria come completato.",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_complete_reminder,
    ),
]
