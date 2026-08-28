"""Vista — l'agente guarda attraverso la camera e ragiona su cosa vede.

Il frame arriva dalla UI web (il browser lo cattura con getUserMedia e lo invia a
ogni messaggio); in assenza di UI si prova la camera lato server. L'immagine viene
mandata a un modello multimodale (VLM) via lo stesso router locale/cloud.
"""

from __future__ import annotations

from ..llm import router
from ..perception.camera import capture_frame_data_url
from ..state import get_frame
from .base import Tool, obj

_DEFAULT_PROMPT = (
    "Descrivi la scena in italiano ed elenca gli oggetti principali che vedi. "
    "Sii concreto e conciso; se c'è del testo leggibile, riportalo."
)


def _look(args: dict, ctx: dict) -> str:
    question = (args.get("question") or "").strip() or _DEFAULT_PROMPT

    session = ctx.get("session", "default")
    frame = get_frame(session) or capture_frame_data_url()
    if not frame:
        return (
            "[nessuna immagine] La camera non è attiva. Attiva la camera nella chat "
            "(pulsante 📷) oppure collega una webcam."
        )

    try:
        client, model = router.resolve("vision", vision=True)
    except Exception as exc:  # noqa: BLE001
        return f"[errore vista] modello non disponibile: {exc}"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": frame}},
                    ],
                }
            ],
            max_tokens=500,
        )
        return resp.choices[0].message.content or "[la vista non ha restituito testo]"
    except Exception as exc:  # noqa: BLE001
        return f"[errore vista] chiamata al modello fallita: {exc}"


TOOLS = [
    Tool(
        name="look",
        description=(
            "Guarda attraverso la camera e descrivi cosa vedi / quali oggetti sono presenti. "
            "Usa questo strumento ogni volta che l'utente chiede cosa vedi, di identificare "
            "un oggetto, di leggere qualcosa inquadrato o di descrivere l'ambiente."
        ),
        parameters=obj(
            {
                "question": {
                    "type": "string",
                    "description": "Cosa guardare in particolare (facoltativo; default: descrivi la scena e gli oggetti).",
                }
            }
        ),
        run=_look,
    ),
]
