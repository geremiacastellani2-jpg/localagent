"""Strumenti per la coda di approvazioni (condivisi da email, messaggi…)."""

from __future__ import annotations

from .. import outbox
from .base import Tool, obj


def _list_pending(_args: dict, _ctx: dict) -> str:
    rows = outbox.list_pending()
    if not rows:
        return "Nessuna azione in attesa di approvazione."
    return "In attesa di approvazione:\n" + "\n".join(
        f"#{r['id']} [{r['kind']}] {r['summary']}" for r in rows
    )


def _approve(args: dict, _ctx: dict) -> str:
    aid = args.get("id")
    if aid is None:
        return "[errore] id mancante"
    return outbox.approve(int(aid))


def _reject(args: dict, _ctx: dict) -> str:
    aid = args.get("id")
    if aid is None:
        return "[errore] id mancante"
    return outbox.reject(int(aid))


TOOLS = [
    Tool(
        name="list_pending_actions",
        description="Elenca le azioni in uscita in attesa di conferma (email, messaggi).",
        parameters=obj({}),
        run=_list_pending,
    ),
    Tool(
        name="approve_action",
        description="Conferma ed esegue un'azione in coda (es. inviare l'email/messaggio).",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_approve,
    ),
    Tool(
        name="reject_action",
        description="Annulla un'azione in coda senza eseguirla.",
        parameters=obj({"id": {"type": "integer"}}, required=["id"]),
        run=_reject,
    ),
]
