"""Astrazione minima per gli strumenti e registro condiviso.

Ogni strumento espone uno schema JSON (function-calling OpenAI-compatibile) e una
funzione `run(args, context) -> str`. Il `context` porta dati runtime (es. la
sessione corrente) senza passarli attraverso il modello.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable

RunFn = Callable[[dict, dict], str]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema dell'oggetto argomenti
    run: RunFn

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def run(self, name: str, arguments: str | dict, context: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"[errore] strumento sconosciuto: {name}"
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        except json.JSONDecodeError:
            return f"[errore] argomenti non validi per {name}: {arguments!r}"
        try:
            result = tool.run(args, context)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        except Exception:  # gli errori di uno strumento non devono abbattere il loop
            return f"[errore in {name}] {traceback.format_exc(limit=2)}"


def obj(properties: dict, required: list[str] | None = None) -> dict:
    """Helper per costruire uno schema oggetto."""
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
