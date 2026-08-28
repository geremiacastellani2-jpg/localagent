"""Raccoglie tutti gli strumenti in un unico registro."""

from __future__ import annotations

from .base import Registry
from . import clock, memory, notes, reminders, vision


def build_registry() -> Registry:
    reg = Registry()
    for module in (notes, reminders, memory, vision, clock):
        for tool in module.TOOLS:
            reg.register(tool)
    return reg
