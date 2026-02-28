"""Pydantic schemas for price-related API responses and internal dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel


# ── Internal hot-path dataclass (not a Pydantic model for performance) ─────────

@dataclass(frozen=True, slots=True)
class TickerUpdate:
    """Normalized price update from any exchange connector.

    Created by each connector's normalize() method; consumed by PriceStore.
    Uses a dataclass (not Pydantic) to minimise allocation on the hot path.
    """

    exchange: str
    symbol: str
    price: Decimal
    currency: str
    volume_24h: Decimal
    timestamp_ms: int
    received_at_ms: int
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None


# ── Pydantic response schemas ──────────────────────────────────────────────────

class FxRateInfo(BaseModel):
    rate: str
    source: str
    is_stale: bool
    last_update_ms: int


class PriceEntry(BaseModel):
    exchange: str
    symbol: str
    price: str          # Decimal-as-string for precision
    currency: str
    bid_price: str | None = None
    ask_price: str | None = None
    volume_24h: str
    timestamp_ms: int
    received_at_ms: int
    is_stale: bool


class PricesResponse(BaseModel):
    prices: list[PriceEntry]
    fx_rate: FxRateInfo


class PriceHistoryEntry(BaseModel):
    exchange: str
    symbol: str
    price: str
    currency: str
    volume_24h: str
    timestamp_ms: int
    created_at: str
