"""Server locale: serve la chat web e gli endpoint dell'agente.

Gira solo sulla tua macchina (default 127.0.0.1). La UI web è l'interfaccia
principale: ci parli da lì e, con la camera attiva, manda in continuo frame,
rilevazioni (con posizione) e volti: è la "vista live" che finisce nello Stato
attuale del modello, nello strumento current_view e nell'endpoint /vision.
"""

from __future__ import annotations

from pathlib import Path

import mimetypes

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import notifications, presence, state, vision_info
from .config import settings
from .core import Agent

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Maggiordomo Locale", version="0.1.0")
agent = Agent()

# librerie/modelli di visione scaricati da scripts/fetch_vendor.sh (opzionali:
# se mancano, la pagina ripiega sulla CDN). MIME espliciti per wasm/mjs.
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/octet-stream", ".tflite")
app.mount("/vendor", StaticFiles(directory=str(WEB_DIR / "vendor"), check_dir=False), name="vendor")


@app.on_event("startup")
def _startup() -> None:
    # bridge Matrix, scheduler proattivo e descrittore live (no-op se disattivi)
    from .matrix_client import bridge
    from .scheduler import scheduler
    from .vision_live import live_describer

    bridge.start()
    scheduler.start()
    live_describer.start()


class Detection(BaseModel):
    label: str
    score: float = 0.0
    box: list[float] = []  # [x, y, w, h] normalizzato 0..1 sul frame


class ChatIn(BaseModel):
    session: str = "default"
    message: str
    frame: str | None = None  # data URL JPEG dalla webcam (facoltativo)
    objects: list[str] | None = None  # etichette live rilevate nel browser
    detections: list[Detection] | None = None  # rilevazioni con posizione
    faces: list[str] | None = None  # volti riconosciuti nel browser
    image: str | None = None  # foto ALLEGATA dall'utente al messaggio (data URL)
    tier: str | None = None  # override per-messaggio: "local" | "cloud"


class ChatOut(BaseModel):
    reply: str
    tier: str = ""
    model: str = ""


class FrameIn(BaseModel):
    session: str = "default"
    frame: str | None = None
    objects: list[str] | None = None
    detections: list[Detection] | None = None
    faces: list[str] | None = None


def _apply_frame(
    session: str,
    frame: str | None,
    objects: list[str] | None,
    detections: list[Detection] | None,
    faces: list[str] | None,
) -> None:
    dets = [d.model_dump() for d in detections] if detections is not None else None
    if frame is not None or objects is not None or dets is not None:
        state.set_frame(session, frame, objects, dets)
    if faces is not None:
        state.set_faces(session, faces)
        for name in presence.update(faces):
            notifications.push(f"👤 Ho riconosciuto {name} davanti alla camera.", "presence")
            state.add_event(session, f"riconosciuto {name}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    from .llm import ollama_reachable, resolve_chat_tier, resolve_vision_tier

    chat_tier = resolve_chat_tier()
    vision_tier = resolve_vision_tier()
    chat_model = settings.cloud_model if chat_tier == "cloud" else settings.local_model
    vision_model = settings.cloud_vision_model if vision_tier == "cloud" else settings.local_vision_model
    return {
        "ok": True,
        "tier": chat_tier,  # compatibilità con la UI precedente
        "model": chat_model,
        "chat": {"tier": chat_tier, "model": chat_model},
        "vision": {"tier": vision_tier, "model": vision_model},
        "live_describe_seconds": settings.live_describe_seconds if settings.live_describe_enabled else 0,
        "cloud_configured": settings.has_cloud(),
        "ollama_reachable": ollama_reachable(),
    }


@app.get("/diag")
def diag() -> dict:
    """Diagnostica completa: cosa è configurato, cosa risponde, cosa manca."""
    import httpx

    from .llm import ollama_reachable
    from .matrix_client import bridge, status as matrix_status

    out: dict = {"ok": True}

    ollama = {"reachable": ollama_reachable(), "models": [], "missing": []}
    if ollama["reachable"]:
        try:
            r = httpx.get(f"{settings.ollama_native_base()}/api/tags", timeout=3)
            ollama["models"] = [m.get("name", "") for m in r.json().get("models", [])]
        except Exception as exc:  # noqa: BLE001
            ollama["error"] = str(exc)
    have = {m.split(":")[0] for m in ollama["models"]}
    for wanted in (settings.local_model, settings.local_vision_model, settings.embed_model):
        if wanted.split(":")[0] not in have:
            ollama["missing"].append(f"ollama pull {wanted}")
    out["ollama"] = ollama

    if settings.has_cloud():
        try:
            r = httpx.get(
                f"{settings.openrouter_base_url}/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                timeout=6,
            )
            out["openrouter"] = "ok" if r.status_code == 200 else f"errore http {r.status_code} (chiave non valida?)"
        except Exception as exc:  # noqa: BLE001
            out["openrouter"] = f"errore di rete: {exc}"
    else:
        out["openrouter"] = "non configurato (OPENROUTER_API_KEY vuota)"

    out["vista_live"] = (
        f"descrizione scena ogni {settings.live_describe_seconds}s"
        if settings.live_describe_enabled and settings.live_describe_seconds > 0
        else "descrizione automatica disattivata"
    )
    out["calendario_caldav"] = "configurato" if settings.caldav_configured() else "non configurato"
    out["email"] = "configurata" if settings.email_configured() else "non configurata"
    out["matrix"] = matrix_status() if not bridge.available() else "configurato"
    out["nota"] = (
        "Camera, riconoscimento oggetti/volti e microfono girano NEL BROWSER: "
        "controllali dalla pagina della chat (permessi browser + macOS), non da qui. "
        "Cosa vede la camera adesso: /vision"
    )
    return out


@app.post("/frame")
def frame(body: FrameIn) -> dict:
    """Feed live: la UI invia in continuo frame, rilevazioni e volti."""
    _apply_frame(body.session, body.frame, body.objects, body.detections, body.faces)
    scene = state.get_scene(body.session)
    return {
        "ok": True,
        "scene": scene[0] if scene else None,
        "scene_age": round(scene[1]) if scene else None,
        "scene_error": state.get_scene_error(body.session),
    }


@app.get("/vision")
def vision(session: str = "default") -> dict:
    """Tutto ciò che la camera sa adesso, in JSON (per la UI e per altri agenti)."""
    return vision_info.json_report(session)


@app.get("/notifications")
def get_notifications(cursor: int = 0) -> dict:
    """La UI fa polling qui per mostrare le notifiche proattive."""
    items = notifications.since(cursor)
    return {"items": items, "cursor": items[-1]["id"] if items else cursor}


_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
         "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def build_context(session: str) -> str:
    """Sezione "Stato attuale" rigenerata a ogni turno per il system prompt.

    Dà al modello, senza bisogno di tool-calling: data/ora, tutta la vista live
    (oggetti con posizione, persone, scena descritta, eventi), agenda e contatori.
    """
    from datetime import datetime

    from . import calendar_store as cal
    from .db import connect

    now = datetime.now()
    lines = [
        f"- Data e ora correnti: {_GIORNI[now.weekday()]} {now.day} {_MESI[now.month - 1]} "
        f"{now.year}, {now:%H:%M}"
    ]
    lines += vision_info.report_lines(session)

    # agenda e contatori (best-effort: mai bloccare la chat per un errore qui)
    try:
        s, e = cal.day_bounds(now.strftime("%Y-%m-%d"))
        events = cal.list_events(s, e)
        if events:
            shown = "; ".join(cal.format_event(ev) for ev in events[:3])
            extra = f" (+{len(events) - 3} altri)" if len(events) > 3 else ""
            lines.append(f"- Agenda di oggi: {shown}{extra}")
        else:
            lines.append("- Agenda di oggi: nessun evento")
        conn = connect()
        try:
            rem = conn.execute("SELECT COUNT(*) AS c FROM reminders WHERE done = 0").fetchone()["c"]
            pend = conn.execute(
                "SELECT COUNT(*) AS c FROM pending_actions WHERE status = 'pending'"
            ).fetchone()["c"]
        finally:
            conn.close()
        lines.append(f"- Promemoria aperti: {rem} · Azioni in attesa di conferma: {pend}")
    except Exception:
        pass

    return "\n".join(lines)


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    # aggiorna la vista live per questa sessione (frame, rilevazioni, volti)
    _apply_frame(body.session, body.frame, body.objects, body.detections, body.faces)

    context = build_context(body.session)

    # foto allegata: diventa la vista corrente (per `look`) e viene descritta
    # subito, così anche i modelli senza tool-calling la "vedono"
    if body.image:
        state.set_frame(body.session, body.image)
        try:
            from .llm import vision_describe

            desc = vision_describe(
                body.image,
                "Descrivi questa immagine in italiano: scena, oggetti, persone, eventuale testo leggibile.",
            )
            context += f"\n- FOTO ALLEGATA dall'utente a questo messaggio — contenuto: {desc}"
        except Exception as exc:  # noqa: BLE001
            context += f"\n- FOTO ALLEGATA dall'utente, ma l'analisi non è riuscita: {exc}"

    override = body.tier if body.tier in ("local", "cloud") else None
    try:
        reply = agent.chat(body.session, body.message, tier=override, context_block=context)
    except Exception as exc:  # noqa: BLE001 — l'errore del modello deve arrivare leggibile in chat
        reply = (
            f"[errore modello] {exc}\n"
            "Controlla http://127.0.0.1:8765/diag per vedere cosa manca "
            "(Ollama attivo? modelli scaricati? chiave OpenRouter valida?)."
        )
    return ChatOut(reply=reply, tier=agent.last_tier, model=agent.last_model)


@app.post("/reset")
def reset(session: str = "default") -> dict:
    agent.reset(session)
    return {"ok": True}
