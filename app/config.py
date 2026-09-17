"""Application configuration loaded from environment variables / .env file.

We intentionally do NOT use `python-dotenv` directly: `pydantic-settings`
already knows how to read a `.env` file via `SettingsConfigDict(env_file=...)`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application settings.

    All values are sourced from environment variables (and, for local
    development, from a `.env` file in the project root).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    bot_username: str = Field(default="", alias="BOT_USERNAME")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    render_external_url: str = Field(default="", alias="RENDER_EXTERNAL_URL")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    port: int = Field(default=10000, alias="PORT")

    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")

    database_url: str = Field(..., alias="DATABASE_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Pagination / rate limiting knobs, tuned centrally instead of magic numbers.
    participants_page_size: int = Field(default=10, alias="PARTICIPANTS_PAGE_SIZE")
    broadcast_messages_per_second: float = Field(default=20.0, alias="BROADCAST_RATE_PER_SEC")
    antispam_max_events: int = Field(default=5, alias="ANTISPAM_MAX_EVENTS")
    antispam_window_seconds: float = Field(default=10.0, alias="ANTISPAM_WINDOW_SECONDS")

    @field_validator("bot_token")
    @classmethod
    def _bot_token_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("BOT_TOKEN must not be empty")
        return value.strip()

    @property
    def admin_ids(self) -> set[int]:
        """Parse the comma-separated ADMIN_IDS env var into a set of ints."""
        result: set[int] = set()
        for chunk in self.admin_ids_raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                result.add(int(chunk))
            except ValueError:
                # Never crash the whole app because of one malformed ID;
                # this gets logged by the caller at startup instead.
                continue
        return result

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]
