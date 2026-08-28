"""Rassegna: un riepilogo di agenda, promemoria, email e code.

Usata sia dallo scheduler (rassegna del mattino) sia dal tool `daily_brief`
(su richiesta). È deterministica — non dipende dal modello — così è affidabile.
"""

from __future__ import annotations

from datetime import datetime

from . import calendar_store as cal
from .config import settings
from .db import connect


def compose_brief() -> str:
    now = datetime.now()
    s, e = cal.day_bounds(now.strftime("%Y-%m-%d"))
    events = cal.list_events(s, e)

    conn = connect()
    try:
        reminders = conn.execute(
            "SELECT text, due_at FROM reminders WHERE done = 0 "
            "ORDER BY (due_at IS NULL), due_at ASC LIMIT 8"
        ).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM pending_actions WHERE status = 'pending'"
        ).fetchone()["c"]
    finally:
        conn.close()

    lines = [f"☀️ Rassegna di {now.strftime('%A %d %B, %H:%M')}"]

    if events:
        lines.append("\n📅 Agenda di oggi:")
        lines += ["  " + cal.format_event(ev) for ev in events]
    else:
        lines.append("\n📅 Nessun evento in agenda oggi.")

    if reminders:
        lines.append("\n○ Promemoria aperti:")
        lines += [
            "  · " + r["text"] + (f" ({r['due_at']})" if r["due_at"] else "") for r in reminders
        ]

    if settings.email_configured():
        try:
            from . import email_client

            unread = email_client.list_messages(limit=50, unread_only=True)
            lines.append(f"\n✉️ Email non lette: {len(unread)}")
        except Exception:
            pass

    if pending:
        lines.append(f"\n✅ Azioni in attesa di conferma: {pending}")

    return "\n".join(lines)
