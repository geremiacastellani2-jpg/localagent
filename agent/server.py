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

from . import notifications, presence
from .config import settings
from .core import Agent
from .state import set_faces, set_frame

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


class ChatOut(BaseModel):
    reply: str


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
    tier = settings.resolve_tier(settings.default_tier)
    return {
        "ok": True,
        "tier": tier,
        "model": settings.cloud_model if tier == "cloud" else settings.local_model,
        "cloud_configured": settings.has_cloud(),
    }


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


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    # aggiorna il frame live per questa sessione, così `look`/`current_view` lo usano
    if body.frame is not None or body.objects is not None:
        set_frame(body.session, body.frame, body.objects)
    reply = agent.chat(body.session, body.message)
    return ChatOut(reply=reply)


@app.post("/reset")
def reset(session: str = "default") -> dict:
    agent.reset(session)
    return {"ok": True}
