"""Pydantic schemas for alert configuration and history."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AlertConfigCreate(BaseModel):
    """Request body for POST /api/v1/alerts."""

    chat_id: int = Field(default=0, ge=0)  # 0 = use default from TELEGRAM_BOT_TOKEN owner
    symbol: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        pattern=r"^[A-Z0-9]+$",
    )
    exchange_a: str | None = None
    exchange_b: str | None = None
    threshold_pct: float = Field(ge=0.1, le=50.0)
    direction: str = Field(pattern=r"^(above|below|both)$")
    cooldown_minutes: int = Field(default=5, ge=1, le=60)
    enabled: bool = True

    @field_validator("exchange_a", "exchange_b")
    @classmethod
    def validate_exchange(cls, v: str | None) -> str | None:
        if v is not None:
            valid = {"bithumb", "upbit", "binance", "bybit", "gate"}
            if v not in valid:
                raise ValueError(f"Invalid exchange: {v!r}. Must be one of {sorted(valid)}")
        return v


class AlertConfigUpdate(BaseModel):
    """Request body for PUT /api/v1/alerts/{id}. All fields optional."""

    symbol: str | None = Field(
        default=None,
        min_length=2,
        max_length=10,
        pattern=r"^[A-Z0-9]+$",
    )
    exchange_a: str | None = None
    exchange_b: str | None = None
    threshold_pct: float | None = Field(default=None, ge=0.1, le=50.0)
    direction: str | None = Field(default=None, pattern=r"^(above|below|both)$")
    cooldown_minutes: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None

    @field_validator("exchange_a", "exchange_b")
    @classmethod
    def validate_exchange(cls, v: str | None) -> str | None:
        if v is not None:
            valid = {"bithumb", "upbit", "binance", "bybit", "gate"}
            if v not in valid:
                raise ValueError(f"Invalid exchange: {v!r}.")
        return v


class AlertConfigResponse(BaseModel):
    id: int
    chat_id: int
    symbol: str | None
    exchange_a: str | None
    exchange_b: str | None
    threshold_pct: str
    direction: str
    cooldown_minutes: int
    enabled: bool
    created_at: str
    updated_at: str
    last_triggered_at: str | None
    trigger_count: int


class AlertHistoryEntry(BaseModel):
    id: int
    alert_config_id: int
    exchange_a: str
    exchange_b: str
    symbol: str
    spread_pct: str
    spread_type: str
    threshold_pct: str
    direction: str
    price_a: str
    price_b: str
    fx_rate: str | None
    fx_source: str | None
    message_text: str
    telegram_delivered: bool
    telegram_message_id: int | None
    created_at: str
