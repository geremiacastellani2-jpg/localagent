"""Vista — l'agente guarda attraverso la camera, dal vivo.

  - `current_view`  → tutto ciò che la camera sa ADESSO: oggetti con posizione,
    persone riconosciute, descrizione della scena (aggiornata in background),
    eventi recenti. Immediato, senza chiamare modelli.
  - `look`          → descrizione fresca e dettagliata del frame corrente
    tramite un modello multimodale (VLM), con una domanda specifica.
  - `who_is_here`   → chi è riconosciuto davanti alla camera.

Il frame è quello live: la UI lo aggiorna in continuo finché la camera è attiva.
"""

from __future__ import annotations

from .. import presence
from ..llm import vision_describe
from ..perception.camera import capture_frame_data_url
from ..state import get_frame
from ..vision_info import report_text
from .base import Tool, obj

_DEFAULT_PROMPT = (
    "Descrivi la scena in italiano ed elenca gli oggetti principali che vedi, con la "
    "loro posizione. Sii concreto e conciso; se c'è del testo leggibile, riportalo."
)


def _current_view(_args: dict, ctx: dict) -> str:
    return report_text(ctx.get("session", "default"))


def _who_is_here(_args: dict, _ctx: dict) -> str:
    people = presence.present(within=15)
    if not people:
        return "Non riconosco nessuno davanti alla camera in questo momento."
    return "Riconosco: " + ", ".join(people) + "."


def _look(args: dict, ctx: dict) -> str:
    question = (args.get("question") or "").strip() or _DEFAULT_PROMPT
    session = ctx.get("session", "default")
    frame = get_frame(session) or capture_frame_data_url()
    if not frame:
        return (
            "[nessuna immagine] La camera non è attiva. Attivala nella chat (📷) "
            "oppure collega una webcam."
        )
    try:
        return vision_describe(frame, question) or "[la vista non ha restituito testo]"
    except Exception as exc:  # noqa: BLE001
        return f"[errore vista] chiamata al modello fallita: {exc}"


TOOLS = [
    Tool(
        name="current_view",
        description=(
            "Tutto ciò che la camera sa adesso: oggetti in vista con posizione, persone "
            "riconosciute, descrizione recente della scena ed eventi. Immediato."
        ),
        parameters=obj({}),
        run=_current_view,
    ),
    Tool(
        name="who_is_here",
        description="Dice quali persone note sono riconosciute dalla camera adesso.",
        parameters=obj({}),
        run=_who_is_here,
    ),
    Tool(
        name="look",
        description=(
            "Guarda dal vivo attraverso la camera e rispondi a una domanda precisa "
            "sull'immagine: descrivere in dettaglio, identificare un oggetto, leggere "
            "del testo. Più lento di current_view ma più preciso."
        ),
        parameters=obj(
            {"question": {"type": "string", "description": "Cosa guardare (facoltativo)."}}
        ),
        run=_look,
    ),
]
