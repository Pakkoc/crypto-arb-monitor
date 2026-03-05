"""Application configuration via pydantic-settings.

All settings are read from environment variables or a .env file.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Values are resolved in this order:
    1. Environment variables
    2. .env file (if present)
    3. Field defaults
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ─────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/arb_monitor.db"

    # ── Telegram ───────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""

    # ── Exchange API Keys ──────────────────────────────────────────────────────
    bithumb_api_key: str = ""
    bithumb_api_secret: str = ""

    upbit_access_key: str = ""
    upbit_secret_key: str = ""

    binance_api_key: str = ""
    binance_api_secret: str = ""

    bybit_api_key: str = ""
    bybit_api_secret: str = ""

    gate_api_key: str = ""
    gate_api_secret: str = ""

    # ── FX Rate Fallback ───────────────────────────────────────────────────────
    exchangerate_api_key: str = ""

    # ── Alert Thresholds (percent) ─────────────────────────────────────────────
    info_threshold_pct: float = 1.0
    warning_threshold_pct: float = 2.0
    critical_threshold_pct: float = 3.0

    # ── Staleness ─────────────────────────────────────────────────────────────
    staleness_threshold_seconds: int = 5


# Singleton — import this everywhere
settings = Settings()
