"""Impostazioni caricate dall'ambiente (.env) e routing dei modelli.

Il principio: locale e cloud parlano la stessa API OpenAI-compatibile, quindi
scegliere dove mandare un compito è solo scegliere un (base_url, api_key, model).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv è opzionale
    pass


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on", "si", "sì"}


@dataclass
class Settings:
    # --- Cloud: OpenRouter (OpenAI-compatibile) ---
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    cloud_model: str = field(default_factory=lambda: os.getenv("CLOUD_MODEL", "anthropic/claude-3.5-sonnet"))
    cloud_vision_model: str = field(
        default_factory=lambda: os.getenv("CLOUD_VISION_MODEL", "anthropic/claude-3.5-sonnet")
    )

    # --- Locale: Ollama (OpenAI-compatibile) ---
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    local_model: str = field(default_factory=lambda: os.getenv("LOCAL_MODEL", "qwen2.5"))
    local_vision_model: str = field(default_factory=lambda: os.getenv("LOCAL_VISION_MODEL", "llama3.2-vision"))

    # --- Routing ---
    # tier di default per la chat: "cloud", "local" oppure "auto"
    default_tier: str = field(default_factory=lambda: os.getenv("DEFAULT_TIER", "auto"))
    # tier per la vista (VLM); "auto" preferisce il cloud se c'è la chiave
    vision_tier: str = field(default_factory=lambda: os.getenv("VISION_TIER", "auto"))

    # --- Storage ---
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DB_PATH", str(DATA_DIR / "maggiordomo.db"))))

    # --- Server ---
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8765")))

    def resolve_tier(self, tier: str) -> str:
        """Trasforma 'auto' in 'cloud' o 'local' in base a cosa è configurato."""
        if tier == "auto":
            return "cloud" if self.openrouter_api_key else "local"
        return tier

    def has_cloud(self) -> bool:
        return bool(self.openrouter_api_key)


settings = Settings()
