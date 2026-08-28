"""Raccoglie tutti gli strumenti in un unico registro."""

from __future__ import annotations

from .base import Registry
from . import (
    approvals,
    briefing,
    calendar,
    clock,
    email,
    memory,
    messages,
    notes,
    reminders,
    vision,
)


def build_registry() -> Registry:
    reg = Registry()
    modules = (notes, reminders, memory, calendar, email, messages, approvals, briefing, vision, clock)
    for module in modules:
        for tool in module.TOOLS:
            reg.register(tool)
    return reg
