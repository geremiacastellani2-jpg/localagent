"""Server locale: serve la chat web e l'endpoint /chat.

Gira solo sulla tua macchina (default 127.0.0.1). La UI web è l'interfaccia
principale: ci parli da lì e, se attivi la camera, ogni messaggio porta con sé
il frame corrente così l'agente può "vedere".
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from collections import Counter

from . import notifications, presence
from .config import settings
from .core import Agent
from .state import frame_age, get_faces, get_objects, set_faces, set_frame

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Maggiordomo Locale", version="0.1.0")
agent = Agent()


@app.on_event("startup")
def _startup() -> None:
    # avvia il bridge Matrix e lo scheduler proattivo (no-op se non configurati)
    from .matrix_client import bridge
    from .scheduler import scheduler

    bridge.start()
    scheduler.start()


class ChatIn(BaseModel):
    session: str = "default"
    message: str
    frame: str | None = None  # data URL JPEG dalla webcam (facoltativo)
    objects: list[str] | None = None  # oggetti live rilevati nel browser
    tier: str | None = None  # override per-messaggio: "local" | "cloud"


class ChatOut(BaseModel):
    reply: str
    tier: str = ""
    model: str = ""


class FrameIn(BaseModel):
    session: str = "default"
    frame: str | None = None
    objects: list[str] | None = None
    faces: list[str] | None = None  # nomi volti riconosciuti nel browser


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
        # compatibilità con la UI precedente
        "tier": chat_tier,
        "model": chat_model,
        "chat": {"tier": chat_tier, "model": chat_model},
        "vision": {"tier": vision_tier, "model": vision_model},
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

    # Ollama: raggiungibile? quali modelli sono scaricati?
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

    # OpenRouter: la chiave funziona davvero?
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

    out["calendario_caldav"] = "configurato" if settings.caldav_configured() else "non configurato"
    out["email"] = "configurata" if settings.email_configured() else "non configurata"
    out["matrix"] = matrix_status() if not bridge.available() else "configurato"
    out["nota"] = (
        "Camera, riconoscimento oggetti/volti e microfono girano NEL BROWSER: "
        "controllali dalla pagina della chat (permessi browser + macOS), non da qui."
    )
    return out


@app.post("/frame")
def frame(body: FrameIn) -> dict:
    """Feed live: la UI invia in continuo frame, oggetti e volti riconosciuti."""
    set_frame(body.session, body.frame, body.objects)
    if body.faces is not None:
        set_faces(body.session, body.faces)
        for name in presence.update(body.faces):
            notifications.push(f"👤 Ho riconosciuto {name} davanti alla camera.", "presence")
    return {"ok": True}


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

    Dà al modello, senza bisogno di tool-calling: data/ora correnti, stato della
    camera (oggetti e persone in vista), agenda di oggi e contatori utili.
    """
    from datetime import datetime

    from . import calendar_store as cal
    from .db import connect

    now = datetime.now()
    lines = [
        f"- Data e ora correnti: {_GIORNI[now.weekday()]} {now.day} {_MESI[now.month - 1]} "
        f"{now.year}, {now:%H:%M}"
    ]

    # camera / vista live
    age = frame_age(session)
    if age is None or age > 20:
        lines.append("- Camera: spenta (nessuna vista disponibile)")
    else:
        parts: list[str] = []
        objs = get_objects(session)
        if objs:
            counted = Counter(objs)
            parts.append(
                "oggetti in vista: "
                + ", ".join(f"{k}×{v}" if v > 1 else k for k, v in counted.items())
            )
        faces = get_faces(session)
        if faces:
            parts.append("persone riconosciute: " + ", ".join(sorted(set(faces))))
        stato = "; ".join(parts) if parts else "nessun oggetto riconosciuto al momento"
        lines.append(f"- Camera: ATTIVA — {stato}")

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
    # aggiorna il frame live per questa sessione, così `look`/`current_view` lo usano
    if body.frame is not None or body.objects is not None:
        set_frame(body.session, body.frame, body.objects)
    override = body.tier if body.tier in ("local", "cloud") else None
    try:
        reply = agent.chat(
            body.session, body.message, tier=override, context_block=build_context(body.session)
        )
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
