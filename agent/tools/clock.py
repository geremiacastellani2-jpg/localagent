"""Strumento base: data e ora correnti."""

from __future__ import annotations

from datetime import datetime

from .base import Tool, obj


def _now(_args: dict, _ctx: dict) -> str:
    now = datetime.now().astimezone()
    return now.strftime("%A %d %B %Y, %H:%M:%S %Z")


TOOLS = [
    Tool(
        name="get_current_time",
        description="Restituisce la data e l'ora locali correnti.",
        parameters=obj({}),
        run=_now,
    ),
]
