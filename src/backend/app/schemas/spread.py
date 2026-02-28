"""Pydantic schemas for spread-related API responses and internal dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel


# ── Internal dataclass ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class SpreadResult:
    """Computed spread between two exchanges for a single symbol.

    Created by SpreadCalculator; consumed by AlertEngine, WS broadcaster,
    and the DatabaseWriter.
    """

    exchange_a: str
    exchange_b: str
    symbol: str
    spread_pct: Decimal
    spread_type: str          # "kimchi_premium" | "same_currency"
    timestamp_ms: int
    is_stale: bool
    stale_reason: str | None
    price_a: Decimal
    price_b: Decimal
    fx_rate: Decimal | None   # None for same-currency spreads
    fx_source: str | None     # "upbit" | "exchangerate-api"


# ── Pydantic response schemas ──────────────────────────────────────────────────

class SpreadEntry(BaseModel):
    exchange_a: str
    exchange_b: str
    symbol: str
    spread_pct: str
    spread_type: str
    is_stale: bool
    stale_reason: str | None = None
    price_a: str
    price_a_currency: str
    price_b: str
    price_b_currency: str
    fx_rate: str | None = None
    fx_source: str | None = None
    timestamp_ms: int


class SpreadMatrixSummary(BaseModel):
    symbol: str
    max_spread: dict
    min_spread: dict
    stale_pairs: int
    total_pairs: int


class SpreadsResponse(BaseModel):
    spreads: list[SpreadEntry]
    matrix_summary: SpreadMatrixSummary | None = None


class SpreadHistoryEntry(BaseModel):
    exchange_a: str
    exchange_b: str
    symbol: str
    spread_pct: str
    spread_type: str
    is_stale: bool
    fx_rate: str | None = None
    fx_source: str | None = None
    timestamp_ms: int
    created_at: str
