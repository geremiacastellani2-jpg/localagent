"""Vista — l'agente guarda attraverso la camera, dal vivo.

Due livelli, come una vista reale:
  - `current_view`  → cosa c'è ADESSO (oggetti rilevati in tempo reale nel
    browser), risposta immediata senza chiamare un modello pesante.
  - `look`          → descrizione ricca del frame corrente tramite un modello
    multimodale (VLM), locale o cloud.

Il frame è quello "live": la UI lo aggiorna in continuo finché la camera è attiva,
quindi `look` guarda sempre il momento presente, non una vecchia foto.
"""

from __future__ import annotations

from ..llm import vision_describe
from ..perception.camera import capture_frame_data_url
from ..state import frame_age, get_frame, get_objects
from .base import Tool, obj

_DEFAULT_PROMPT = (
    "Descrivi la scena in italiano ed elenca gli oggetti principali che vedi. "
    "Sii concreto e conciso; se c'è del testo leggibile, riportalo."
)


def _current_view(_args: dict, ctx: dict) -> str:
    session = ctx.get("session", "default")
    objects = get_objects(session)
    age = frame_age(session)
    if age is None:
        return "La camera non è attiva: non sto vedendo niente in questo momento."
    freshness = "in tempo reale" if age < 5 else f"ultimo aggiornamento {int(age)}s fa"
    if not objects:
        return f"Camera attiva ({freshness}), ma nessun oggetto riconosciuto al momento."
    # conta i duplicati (es. "person x2")
    counts: dict[str, int] = {}
    for o in objects:
        counts[o] = counts.get(o, 0) + 1
    listed = ", ".join(f"{k}×{v}" if v > 1 else k for k, v in counts.items())
    return f"In vista adesso ({freshness}): {listed}. Usa `look` per una descrizione dettagliata."


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
            "Cosa è visibile ADESSO dalla camera, in tempo reale (elenco oggetti). "
            "Veloce, senza descrizione: usalo per sapere cosa c'è in questo momento."
        ),
        parameters=obj({}),
        run=_current_view,
    ),
    Tool(
        name="look",
        description=(
            "Guarda dal vivo attraverso la camera e descrivi in dettaglio cosa vedi, "
            "identifica un oggetto o leggi del testo inquadrato. Usa questo quando "
            "serve una descrizione, non solo l'elenco degli oggetti."
        ),
        parameters=obj(
            {
                "question": {
                    "type": "string",
                    "description": "Cosa guardare in particolare (facoltativo).",
                }
            }
        ),
        run=_look,
    ),
]
