"""Strumenti email: leggere la posta e mettere in coda gli invii (con conferma).

L'invio non è immediato: `send_email` crea un'azione nella coda di approvazioni;
l'utente la conferma con `approve_action`. Il triage ("è importante?") lo fa il
modello leggendo la lista; qui esponiamo solo lettura + invio controllato.
"""

from __future__ import annotations

from .. import email_client, outbox
from ..config import settings
from .base import Tool, obj

# registra il dispatcher: quando un'azione 'email.send' viene approvata, invia via SMTP
outbox.register("email.send", email_client.send_message)


def _guard() -> str | None:
    if not settings.email_configured():
        return (
            "Email non configurata. Imposta EMAIL_ADDRESS/EMAIL_PASSWORD (per Gmail, "
            "una password per le app) e IMAP_HOST/SMTP_HOST nel file .env."
        )
    return None


def _list_emails(args: dict, _ctx: dict) -> str:
    if (g := _guard()):
        return g
    limit = int(args.get("limit") or 10)
    unread = bool(args.get("unread_only", False))
    query = (args.get("query") or "").strip() or None
    try:
        msgs = email_client.list_messages(limit=limit, unread_only=unread, query=query)
    except Exception as exc:  # noqa: BLE001
        return f"[errore email] {exc}"
    if not msgs:
        return "Nessuna email trovata."
    lines = []
    for m in msgs:
        mark = "●" if m["unread"] else "○"
        lines.append(f"{mark} uid {m['uid']} — {m['from']} — {m['subject']}")
    return "\n".join(lines)


def _read_email(args: dict, _ctx: dict) -> str:
    if (g := _guard()):
        return g
    uid = str(args.get("uid") or "").strip()
    if not uid:
        return "[errore] uid mancante"
    try:
        msg = email_client.read_message(uid)
    except Exception as exc:  # noqa: BLE001
        return f"[errore email] {exc}"
    if not msg:
        return f"Nessuna email con uid {uid}."
    return (
        f"Da: {msg['from']}\nA: {msg['to']}\nData: {msg['date']}\n"
        f"Oggetto: {msg['subject']}\n\n{msg['body']}"
    )


def _send_email(args: dict, _ctx: dict) -> str:
    if (g := _guard()):
        return g
    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not body:
        return "[errore] servono almeno 'to' e 'body'"
    summary = f"Email a {to} — «{subject or '(senza oggetto)'}»"
    aid = outbox.enqueue("email.send", summary, {"to": to, "subject": subject, "body": body})
    preview = body if len(body) < 300 else body[:300] + "…"
    return (
        f"Bozza pronta in coda di approvazione #{aid}:\n"
        f"A: {to}\nOggetto: {subject}\n\n{preview}\n\n"
        f"Confermi l'invio? (approva #{aid})"
    )


TOOLS = [
    Tool(
        name="list_emails",
        description="Elenca le email recenti (o solo le non lette / una ricerca testuale).",
        parameters=obj(
            {
                "limit": {"type": "integer"},
                "unread_only": {"type": "boolean"},
                "query": {"type": "string", "description": "Testo da cercare (facoltativo)."},
            }
        ),
        run=_list_emails,
    ),
    Tool(
        name="read_email",
        description="Legge il contenuto di un'email dato il suo uid (non la segna come letta).",
        parameters=obj({"uid": {"type": "string"}}, required=["uid"]),
        run=_read_email,
    ),
    Tool(
        name="send_email",
        description=(
            "Prepara un'email e la mette in coda di approvazione. NON viene inviata "
            "finché l'utente non conferma con approve_action."
        ),
        parameters=obj(
            {
                "to": {"type": "string", "description": "Destinatario."},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            required=["to", "body"],
        ),
        run=_send_email,
    ),
]
