"""Strumento: rassegna su richiesta (agenda, promemoria, email, code)."""

from __future__ import annotations

from .. import briefing
from .base import Tool, obj


def _daily_brief(_args: dict, _ctx: dict) -> str:
    return briefing.compose_brief()


TOOLS = [
    Tool(
        name="daily_brief",
        description=(
            "Prepara la rassegna: agenda di oggi, promemoria aperti, email non "
            "lette e azioni in attesa. Usalo quando l'utente chiede un riepilogo "
            "della giornata o 'come sono messo'."
        ),
        parameters=obj({}),
        run=_daily_brief,
    ),
]
