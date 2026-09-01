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
    # modello di embedding locale per la memoria semantica (Fase 3)
    embed_model: str = field(default_factory=lambda: os.getenv("EMBED_MODEL", "nomic-embed-text"))

    # --- Routing ---
    # tier di default per la chat: "cloud", "local" oppure "auto"
    default_tier: str = field(default_factory=lambda: os.getenv("DEFAULT_TIER", "auto"))
    # tier per la vista (VLM); "auto" preferisce il cloud se c'è la chiave
    vision_tier: str = field(default_factory=lambda: os.getenv("VISION_TIER", "auto"))

    # --- Calendario: CalDAV (iCloud / Google / Fastmail / Radicale…) ---
    caldav_url: str = field(default_factory=lambda: os.getenv("CALDAV_URL", ""))
    caldav_username: str = field(default_factory=lambda: os.getenv("CALDAV_USERNAME", ""))
    caldav_password: str = field(default_factory=lambda: os.getenv("CALDAV_PASSWORD", ""))
    # nome del calendario da usare (vuoto = il primo/predefinito)
    caldav_calendar: str = field(default_factory=lambda: os.getenv("CALDAV_CALENDAR", ""))

    # --- Email (IMAP/SMTP) — Fase 4 ---
    email_address: str = field(default_factory=lambda: os.getenv("EMAIL_ADDRESS", ""))
    email_password: str = field(default_factory=lambda: os.getenv("EMAIL_PASSWORD", ""))
    imap_host: str = field(default_factory=lambda: os.getenv("IMAP_HOST", "imap.gmail.com"))
    imap_port: int = field(default_factory=lambda: int(os.getenv("IMAP_PORT", "993")))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))

    # --- Messaggi: Matrix (bridge WhatsApp/SMS/iMessage) — Fase 5 ---
    matrix_homeserver: str = field(default_factory=lambda: os.getenv("MATRIX_HOMESERVER", ""))
    matrix_user: str = field(default_factory=lambda: os.getenv("MATRIX_USER", ""))
    matrix_token: str = field(default_factory=lambda: os.getenv("MATRIX_TOKEN", ""))
    matrix_password: str = field(default_factory=lambda: os.getenv("MATRIX_PASSWORD", ""))
    matrix_device_id: str = field(default_factory=lambda: os.getenv("MATRIX_DEVICE_ID", "MAGGIORDOMO"))

    # --- Vista live: descrizione continua della scena col VLM ---
    live_describe_enabled: bool = field(default_factory=lambda: _bool("LIVE_DESCRIBE_ENABLED", True))
    # ogni quanti secondi ridescrivere la scena (0 = disattivo); prima se la scena cambia
    live_describe_seconds: int = field(default_factory=lambda: int(os.getenv("LIVE_DESCRIBE_SECONDS", "20")))

    # --- Proattività (Fase 6) ---
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    scheduler_interval_seconds: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60")))
    brief_hour: int = field(default_factory=lambda: int(os.getenv("BRIEF_HOUR", "8")))
    # secondi di assenza oltre i quali un volto che riappare conta come "arrivo"
    presence_arrival_gap_seconds: int = field(default_factory=lambda: int(os.getenv("PRESENCE_ARRIVAL_GAP", "120")))

    # --- Storage ---
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DB_PATH", str(DATA_DIR / "maggiordomo.db"))))

    # --- Server ---
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8765")))

    def has_cloud(self) -> bool:
        return bool(self.openrouter_api_key)

    def caldav_configured(self) -> bool:
        return bool(self.caldav_url and self.caldav_username and self.caldav_password)

    def email_configured(self) -> bool:
        return bool(self.email_address and self.email_password and self.imap_host and self.smtp_host)

    def matrix_configured(self) -> bool:
        return bool(self.matrix_homeserver and self.matrix_user and (self.matrix_token or self.matrix_password))

    def ollama_native_base(self) -> str:
        """L'URL base dell'API nativa di Ollama (senza il suffisso /v1)."""
        host = self.ollama_base_url.rstrip("/")
        if host.endswith("/v1"):
            host = host[:-3].rstrip("/")
        return host


settings = Settings()
