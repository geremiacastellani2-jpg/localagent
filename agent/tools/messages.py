"""Strumenti messaggi (Matrix → WhatsApp/SMS/iMessage/Telegram).

Lettura diretta dal buffer del bridge; l'invio passa dalla coda di approvazioni,
esattamente come le email — automatizzare WhatsApp è delicato, quindi ogni
messaggio in uscita richiede la tua conferma.
"""

from __future__ import annotations

from datetime import datetime

from .. import outbox
from ..matrix_client import bridge, status
from .base import Tool, obj


def _dispatch_send(payload: dict) -> str:
    return bridge.send(payload["room"], payload["text"])


outbox.register("matrix.send", _dispatch_send)


def _guard() -> str | None:
    if not bridge.available():
        return status()
    return None


def _list_chats(_args: dict, _ctx: dict) -> str:
    if (g := _guard()):
        return g
    rooms = bridge.rooms()
    if not rooms:
        return "Nessuna chat ancora sincronizzata (il bridge sta caricando o non ci sono messaggi recenti)."
    rooms.sort(key=lambda r: r["count"], reverse=True)
    return "Chat:\n" + "\n".join(f"· {r['name']} ({r['count']} messaggi)" for r in rooms[:20])


def _read_chat(args: dict, _ctx: dict) -> str:
    if (g := _guard()):
        return g
    room = (args.get("room") or "").strip()
    if not room:
        return "[errore] indica la chat (nome o id stanza)"
    limit = int(args.get("limit") or 15)
    res = bridge.recent(room, limit=limit)
    if res is None:
        return f"Chat non trovata: {room}"
    name, msgs = res
    if not msgs:
        return f"Nessun messaggio recente in «{name}»."
    lines = []
    for m in msgs:
        ts = datetime.fromtimestamp(m["ts"] / 1000).strftime("%d/%m %H:%M") if m.get("ts") else ""
        lines.append(f"[{ts}] {m['sender']}: {m['body']}")
    return f"«{name}»:\n" + "\n".join(lines)


def _send_message(args: dict, _ctx: dict) -> str:
    if (g := _guard()):
        return g
    room = (args.get("room") or "").strip()
    text = (args.get("text") or "").strip()
    if not room or not text:
        return "[errore] servono 'room' e 'text'"
    summary = f"Messaggio a «{room}»: {text[:60]}" + ("…" if len(text) > 60 else "")
    aid = outbox.enqueue("matrix.send", summary, {"room": room, "text": text})
    return (
        f"Messaggio pronto in coda di approvazione #{aid}:\n"
        f"A: {room}\n{text}\n\nConfermi l'invio? (approva #{aid})"
    )


TOOLS = [
    Tool(
        name="list_chats",
        description="Elenca le chat di messaggistica (WhatsApp/SMS/… via Matrix) con messaggi recenti.",
        parameters=obj({}),
        run=_list_chats,
    ),
    Tool(
        name="read_chat",
        description="Legge i messaggi recenti di una chat (per nome del contatto o id stanza).",
        parameters=obj(
            {
                "room": {"type": "string", "description": "Nome del contatto/chat o id stanza."},
                "limit": {"type": "integer"},
            },
            required=["room"],
        ),
        run=_read_chat,
    ),
    Tool(
        name="send_message",
        description=(
            "Prepara un messaggio (WhatsApp/SMS/… via Matrix) e lo mette in coda di "
            "approvazione. NON viene inviato finché non lo confermi con approve_action."
        ),
        parameters=obj(
            {
                "room": {"type": "string", "description": "Nome del contatto/chat o id stanza."},
                "text": {"type": "string"},
            },
            required=["room", "text"],
        ),
        run=_send_message,
    ),
]
