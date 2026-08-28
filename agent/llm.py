"""Router dei modelli: un solo client OpenAI-compatibile, due destinazioni.

    resolve("chat")            -> (client, model) per la conversazione
    resolve("chat", vision=True) -> (client, model) per un modello multimodale

Locale = Ollama, cloud = OpenRouter. Cambiare destinazione è cambiare base_url.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from .config import Settings, settings


@lru_cache(maxsize=4)
def _client(base_url: str, api_key: str) -> OpenAI:
    # api_key non può essere vuota per il client; Ollama ignora il valore.
    return OpenAI(base_url=base_url, api_key=api_key or "not-needed")


class Router:
    def __init__(self, cfg: Settings = settings) -> None:
        self.cfg = cfg

    def resolve(self, task: str = "chat", vision: bool = False) -> tuple[OpenAI, str]:
        tier = self.cfg.vision_tier if vision else self.cfg.default_tier
        tier = self.cfg.resolve_tier(tier)

        if tier == "cloud":
            if not self.cfg.has_cloud():
                raise RuntimeError(
                    "Tier 'cloud' richiesto ma OPENROUTER_API_KEY non è impostata. "
                    "Aggiungila al file .env oppure usa DEFAULT_TIER=local."
                )
            client = _client(self.cfg.openrouter_base_url, self.cfg.openrouter_api_key)
            model = self.cfg.cloud_vision_model if vision else self.cfg.cloud_model
        else:  # local
            client = _client(self.cfg.ollama_base_url, "ollama")
            model = self.cfg.local_vision_model if vision else self.cfg.local_model

        return client, model


router = Router()
