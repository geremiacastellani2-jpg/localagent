"""Router dei modelli: un solo client OpenAI-compatibile, due destinazioni.

Locale = Ollama (sempre gratuito), cloud = OpenRouter.

Modalità "solo gratuiti" (FREE_ONLY, predefinita): sul cloud si usano SOLO modelli
a costo zero, scelti dinamicamente dal catalogo di OpenRouter (prezzo 0, output
testo, `tools` se possibile, `image` per la vista). I modelli gratuiti sono
rate-limited (429): per questo esiste una ROSA di candidati con rotazione
automatica e un periodo di riposo per chi ha risposto 429; esaurita la rosa si
passa al locale.

Semantica di "auto" (ibrido):
  - chat   → LOCALE se Ollama è raggiungibile (privato, gratuito); cloud altrimenti.
  - vision → CLOUD se c'è la chiave (qualità); locale altrimenti.
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


# ---------------------------------------------------------------------------
# Ollama raggiungibile?
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Catalogo OpenRouter e rosa dei modelli gratuiti
# ---------------------------------------------------------------------------
_MODELS_CACHE: tuple[float, list[dict]] | None = None
_MODELS_TTL = 3600.0
# ripiego statico se il catalogo non è raggiungibile
_STATIC_FREE_CHAT = ["openrouter/free", "google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free"]
_STATIC_FREE_VISION = ["google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free", "openrouter/free"]
# modelli non conversazionali da escludere (classificatori, audio, embedding…)
_EXCLUDE = ("safety", "guard", "moderation", "lyria", "embed", "tts", "whisper", "rerank", "-code")
# famiglie note: piccolo bonus di affidabilità
_FAMILY_BONUS = ("gemma", "llama", "qwen", "mistral", "deepseek", "gpt-oss", "minimax", "glm", "nemotron")


def openrouter_models() -> list[dict]:
    """Catalogo pubblico di OpenRouter (nessuna chiave richiesta), in cache 1h."""
    global _MODELS_CACHE
    now = time.time()
    if _MODELS_CACHE and (now - _MODELS_CACHE[0]) < _MODELS_TTL:
        return _MODELS_CACHE[1]
    try:
        r = httpx.get(f"{settings.openrouter_base_url}/models", timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        _MODELS_CACHE = (now, data)
        return data
    except Exception:
        return _MODELS_CACHE[1] if _MODELS_CACHE else []


def _is_free(m: dict) -> bool:
    if str(m.get("id", "")).endswith(":free"):
        return True
    p = m.get("pricing") or {}
    return str(p.get("prompt")) == "0" and str(p.get("completion")) == "0"


def _outputs_text(m: dict) -> bool:
    outs = (m.get("architecture") or {}).get("output_modalities")
    return (not outs) or ("text" in outs)


def _sees_images(m: dict) -> bool:
    return "image" in ((m.get("architecture") or {}).get("input_modalities") or [])


def free_pool(vision: bool = False) -> list[str]:
    """Rosa ordinata di modelli gratuiti (id OpenRouter), i migliori per primi."""
    cands = [
        m for m in openrouter_models()
        if _is_free(m) and _outputs_text(m) and not any(x in m["id"] for x in _EXCLUDE)
        and (not vision or _sees_images(m))
    ]

    def score(m: dict) -> float:
        mid = m["id"]
        s = 0.0
        if "tools" in (m.get("supported_parameters") or []):
            s += 2
        if mid == "openrouter/free":  # router automatico: ottimo per la chat
            s += 3 if not vision else 0.5
        if any(f in mid for f in _FAMILY_BONUS):
            s += 1
        s += min(int(m.get("context_length") or 0), 1_000_000) / 1_000_000
        return s

    ids = [m["id"] for m in sorted(cands, key=score, reverse=True)][:8]
    if not ids:
        ids = list(_STATIC_FREE_VISION if vision else _STATIC_FREE_CHAT)
    pinned = settings.cloud_vision_model if vision else settings.cloud_model
    if pinned and pinned != "auto" and pinned.endswith(":free"):
        ids = [pinned] + [i for i in ids if i != pinned]
    return ids


def cloud_candidates(vision: bool = False) -> list[str]:
    """Modelli cloud da provare, in ordine."""
    configured = settings.cloud_vision_model if vision else settings.cloud_model
    if settings.free_only or not configured or configured == "auto":
        return free_pool(vision)
    return [configured]


_COOLDOWN: dict[str, float] = {}  # model -> fino a quando è in riposo


def mark_rate_limited(model: str, seconds: float = 90.0) -> None:
    _COOLDOWN[model] = time.time() + seconds


def available_candidates(vision: bool = False) -> list[str]:
    """Candidati non in riposo (se sono tutti in riposo, li ritorna comunque)."""
    now = time.time()
    cands = cloud_candidates(vision)
    fresh = [c for c in cands if _COOLDOWN.get(c, 0) <= now]
    return fresh or cands


def cooled_down() -> list[str]:
    now = time.time()
    return [m for m, until in _COOLDOWN.items() if until > now]


# ---------------------------------------------------------------------------
# Tier
# ---------------------------------------------------------------------------
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


def _pair(tier: str, vision: bool, model: str | None = None) -> tuple[OpenAI, str]:
    if tier == "cloud":
        if not settings.has_cloud():
            raise RuntimeError(
                "Tier 'cloud' richiesto ma OPENROUTER_API_KEY non è impostata. "
                "Aggiungila al file .env oppure usa il tier locale."
            )
        client = _client(settings.openrouter_base_url, settings.openrouter_api_key)
        model = model or available_candidates(vision)[0]
    else:
        client = _client(settings.ollama_base_url, "ollama")
        model = model or (settings.local_vision_model if vision else settings.local_model)
    return client, model


class Router:
    def __init__(self, cfg: Settings = settings) -> None:
        self.cfg = cfg

    def resolve(
        self, task: str = "chat", vision: bool = False, override: str | None = None,
        model: str | None = None,
    ) -> tuple[OpenAI, str, str]:
        tier = resolve_vision_tier(override) if vision else resolve_chat_tier(override)
        client, chosen = _pair(tier, vision, model)
        return client, chosen, tier


router = Router()


def is_rate_limit_error(exc: Exception) -> bool:
    low = str(exc).lower()
    return (
        "429" in low or "rate limit" in low or "rate-limit" in low
        or "ratelimit" in low or "too many requests" in low
    )


# ---------------------------------------------------------------------------
# Vista (VLM)
# ---------------------------------------------------------------------------
def _strip_data_url(data_url: str) -> str:
    return data_url.split(",", 1)[1] if "," in data_url else data_url


def _vision_once(tier: str, data_url: str, prompt: str, max_tokens: int, model: str | None = None) -> str:
    if tier == "cloud":
        client, chosen = _pair("cloud", True, model)
        resp = client.chat.completions.create(
            model=chosen,
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
    """Manda un'immagine a un modello multimodale, ruotando sui candidati gratuiti
    del cloud (429 → prossimo) e ripiegando sull'altro tier. Gli errori finiscono
    nel messaggio, così il problema è diagnosticabile dalla chat."""
    preferred = resolve_vision_tier()
    order = [preferred]
    other = "local" if preferred == "cloud" else "cloud"
    if (other == "cloud" and settings.has_cloud()) or (other == "local" and ollama_reachable()):
        order.append(other)

    errors: list[str] = []
    for tier in order:
        if tier == "cloud":
            for cand in available_candidates(True)[:4]:
                try:
                    return _vision_once("cloud", data_url, prompt, max_tokens, model=cand)
                except Exception as exc:  # noqa: BLE001
                    if is_rate_limit_error(exc):
                        mark_rate_limited(cand)
                    errors.append(f"cloud/{cand}: {str(exc)[:160]}")
            continue
        try:
            return _vision_once("local", data_url, prompt, max_tokens)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "404" in msg or "not found" in msg.lower():
                msg += f" — probabilmente manca il modello: ollama pull {settings.local_vision_model}"
            errors.append(f"local: {msg[:200]}")
    raise RuntimeError("; ".join(errors))
