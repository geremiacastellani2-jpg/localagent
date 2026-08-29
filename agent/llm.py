"""Router dei modelli: un solo client OpenAI-compatibile, due destinazioni.

Locale = Ollama, cloud = OpenRouter. Cambiare destinazione è cambiare base_url.

Semantica di "auto" (ibrido, come da blueprint):
  - chat   → LOCALE se Ollama è raggiungibile (privato, gratuito); cloud altrimenti.
  - vision → CLOUD se c'è la chiave (compito difficile); locale altrimenti.
L'utente può forzare per-richiesta ("local"/"cloud") dal selettore nella chat.
"""

from __future__ import annotations

import time
from functools import lru_cache

import httpx
from openai import OpenAI

from .config import Settings, settings


@lru_cache(maxsize=4)
def _client(base_url: str, api_key: str) -> OpenAI:
    # api_key non può essere vuota per il client; Ollama ignora il valore.
    return OpenAI(base_url=base_url, api_key=api_key or "not-needed")


_OLLAMA_OK: tuple[float, bool] | None = None  # (timestamp, raggiungibile)


def ollama_reachable(ttl: float = 30.0) -> bool:
    """True se Ollama risponde; il risultato è tenuto in cache per `ttl` secondi."""
    global _OLLAMA_OK
    now = time.time()
    if _OLLAMA_OK and (now - _OLLAMA_OK[0]) < ttl:
        return _OLLAMA_OK[1]
    try:
        r = httpx.get(f"{settings.ollama_native_base()}/api/tags", timeout=1.5)
        ok = r.status_code == 200
    except Exception:
        ok = False
    _OLLAMA_OK = (now, ok)
    return ok


def resolve_chat_tier(override: str | None = None) -> str:
    tier = override or settings.default_tier
    if tier == "auto":
        if ollama_reachable():
            return "local"
        return "cloud" if settings.has_cloud() else "local"
    return tier


def resolve_vision_tier(override: str | None = None) -> str:
    tier = override or settings.vision_tier
    if tier == "auto":
        return "cloud" if settings.has_cloud() else "local"
    return tier


def _pair(tier: str, vision: bool) -> tuple[OpenAI, str]:
    if tier == "cloud":
        if not settings.has_cloud():
            raise RuntimeError(
                "Tier 'cloud' richiesto ma OPENROUTER_API_KEY non è impostata. "
                "Aggiungila al file .env oppure usa il tier locale."
            )
        client = _client(settings.openrouter_base_url, settings.openrouter_api_key)
        model = settings.cloud_vision_model if vision else settings.cloud_model
    else:
        client = _client(settings.ollama_base_url, "ollama")
        model = settings.local_vision_model if vision else settings.local_model
    return client, model


class Router:
    def __init__(self, cfg: Settings = settings) -> None:
        self.cfg = cfg

    def resolve(
        self, task: str = "chat", vision: bool = False, override: str | None = None
    ) -> tuple[OpenAI, str, str]:
        tier = resolve_vision_tier(override) if vision else resolve_chat_tier(override)
        client, model = _pair(tier, vision)
        return client, model, tier


router = Router()


def _strip_data_url(data_url: str) -> str:
    return data_url.split(",", 1)[1] if "," in data_url else data_url


def _vision_once(tier: str, data_url: str, prompt: str, max_tokens: int) -> str:
    if tier == "cloud":
        if not settings.has_cloud():
            raise RuntimeError("chiave OpenRouter non impostata")
        client = _client(settings.openrouter_base_url, settings.openrouter_api_key)
        resp = client.chat.completions.create(
            model=settings.cloud_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    # locale — API nativa di Ollama (supporto immagini affidabile)
    host = settings.ollama_native_base()
    r = httpx.post(
        f"{host}/api/chat",
        json={
            "model": settings.local_vision_model,
            "messages": [{"role": "user", "content": prompt, "images": [_strip_data_url(data_url)]}],
            "stream": False,
        },
        timeout=120,
    )
    r.raise_for_status()
    return (r.json().get("message") or {}).get("content", "") or ""


def vision_describe(data_url: str, prompt: str, max_tokens: int = 500) -> str:
    """Manda un'immagine a un modello multimodale, col fallback sull'altro tier.

    Prova prima il tier preferito (VISION_TIER); se fallisce e l'altro tier è
    disponibile, riprova lì. Gli errori di entrambi finiscono nel messaggio,
    così il problema è diagnosticabile dalla chat.
    """
    preferred = resolve_vision_tier()
    order = [preferred]
    other = "local" if preferred == "cloud" else "cloud"
    if (other == "cloud" and settings.has_cloud()) or (other == "local" and ollama_reachable()):
        order.append(other)

    errors: list[str] = []
    for tier in order:
        try:
            return _vision_once(tier, data_url, prompt, max_tokens)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if tier == "local" and ("404" in msg or "not found" in msg.lower()):
                msg += f" — probabilmente manca il modello: ollama pull {settings.local_vision_model}"
            errors.append(f"{tier}: {msg}")
    raise RuntimeError("; ".join(errors))
