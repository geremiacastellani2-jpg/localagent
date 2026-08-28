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

from .config import settings
from .core import Agent
from .state import set_frame

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Maggiordomo Locale", version="0.1.0")
agent = Agent()


class ChatIn(BaseModel):
    session: str = "default"
    message: str
    frame: str | None = None  # data URL JPEG dalla webcam (facoltativo)


class ChatOut(BaseModel):
    reply: str


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


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    # memorizza l'ultimo frame per questa sessione, così lo strumento `look` lo usa
    set_frame(body.session, body.frame)
    reply = agent.chat(body.session, body.message)
    return ChatOut(reply=reply)


@app.post("/reset")
def reset(session: str = "default") -> dict:
    agent.reset(session)
    return {"ok": True}
