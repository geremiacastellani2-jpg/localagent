"""Client email via IMAP/SMTP, solo libreria standard.

Lettura (IMAP) e invio (SMTP). L'invio non parte da qui direttamente: passa dalla
coda di approvazioni (outbox), così ogni email in uscita richiede la tua conferma.

Per Gmail: attiva la verifica in due passaggi e crea una "password per le app"
(myaccount.google.com → Sicurezza), poi usala come EMAIL_PASSWORD.
"""

from __future__ import annotations

import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

from .config import settings


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _imap() -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    conn.login(settings.email_address, settings.email_password)
    conn.select("INBOX")
    return conn


def list_messages(limit: int = 10, unread_only: bool = False, query: str | None = None) -> list[dict]:
    conn = _imap()
    try:
        if query:
            typ, data = conn.uid("search", None, "TEXT", f'"{query}"')
        else:
            typ, data = conn.uid("search", None, "UNSEEN" if unread_only else "ALL")
        if typ != "OK":
            return []
        uids = data[0].split()
        uids = uids[-limit:][::-1]  # i più recenti prima
        out = []
        for uid in uids:
            typ, msg_data = conn.uid("fetch", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            flags = msg_data[0][0].decode(errors="ignore")
            msg = email.message_from_bytes(msg_data[0][1])
            out.append(
                {
                    "uid": uid.decode(),
                    "from": _decode(msg.get("From")),
                    "subject": _decode(msg.get("Subject")) or "(senza oggetto)",
                    "date": _decode(msg.get("Date")),
                    "unread": "\\Seen" not in flags,
                }
            )
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        # preferisci text/plain
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                except Exception:
                    continue
        return "(nessun testo semplice; probabilmente HTML)"
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
    except Exception:
        return str(msg.get_payload())


def read_message(uid: str) -> dict | None:
    conn = _imap()
    try:
        typ, msg_data = conn.uid("fetch", uid.encode(), "(BODY.PEEK[])")
        if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            return None
        msg = email.message_from_bytes(msg_data[0][1])
        body = _extract_body(msg).strip()
        if len(body) > 4000:
            body = body[:4000] + "\n…[troncato]"
        return {
            "uid": uid,
            "from": _decode(msg.get("From")),
            "to": _decode(msg.get("To")),
            "subject": _decode(msg.get("Subject")) or "(senza oggetto)",
            "date": _decode(msg.get("Date")),
            "body": body,
        }
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def send_message(payload: dict) -> str:
    """Dispatcher SMTP (chiamato dalla coda di approvazioni)."""
    to = payload["to"]
    subject = payload.get("subject", "")
    body = payload.get("body", "")

    msg = EmailMessage()
    msg["From"] = settings.email_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.email_address, settings.email_password)
        server.send_message(msg)
    return f"email inviata a {parseaddr(to)[1] or to}"
