"""All StrEnum types shared across the application.

These enums are the single source of truth for valid string values used in
the database, API responses, and internal logic.
"""
from __future__ import annotations

from enum import StrEnum


class ExchangeId(StrEnum):
    """Canonical exchange identifiers. Used as DB primary keys and API values."""

    BITHUMB = "bithumb"
    UPBIT = "upbit"
    BINANCE = "binance"
    BYBIT = "bybit"
    GATE = "gate"


class Currency(StrEnum):
    """Quote currencies used by exchanges."""

    KRW = "KRW"
    USDT = "USDT"


class ConnectorState(StrEnum):
    """WebSocket connector lifecycle states (6-state FSM per DD-3)."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SUBSCRIBING = "SUBSCRIBING"
    ACTIVE = "ACTIVE"
    WAIT_RETRY = "WAIT_RETRY"


class SpreadType(StrEnum):
    """Types of spread calculations."""

    KIMCHI_PREMIUM = "kimchi_premium"
    SAME_CURRENCY = "same_currency"


class AlertDirection(StrEnum):
    """Alert trigger direction."""

    ABOVE = "above"
    BELOW = "below"
    BOTH = "both"


class AlertSeverity(StrEnum):
    """Alert severity tiers based on spread magnitude.

    Thresholds:
      INFO     >= 1.0%
      WARNING  >= 2.0%
      CRITICAL >= 3.0%
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FxRateSource(StrEnum):
    """FX rate data sources."""

    UPBIT = "upbit"
    EXCHANGERATE_API = "exchangerate-api"


class FallbackMode(StrEnum):
    """Connector fallback modes when WebSocket is unavailable."""

    NONE = "none"
    REST_POLLING = "REST_POLLING"


class WsEventType(StrEnum):
    """WebSocket event type identifiers (server-to-client and client-to-server)."""

    WELCOME = "welcome"
    SNAPSHOT = "snapshot"
    PRICE_UPDATE = "price_update"
    SPREAD_UPDATE = "spread_update"
    ALERT_TRIGGERED = "alert_triggered"
    EXCHANGE_STATUS = "exchange_status"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    SUBSCRIBE = "subscribe"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBE = "unsubscribe"
    UNSUBSCRIBED = "unsubscribed"
    PONG = "pong"


class WsChannel(StrEnum):
    """WebSocket subscription channels."""

    PRICES = "prices"
    SPREADS = "spreads"
    ALERTS = "alerts"
    EXCHANGE_STATUS = "exchange_status"


# ── Exchange relationship constants ────────────────────────────────────────────

EXCHANGE_CURRENCY: dict[str, str] = {
    "bithumb": "KRW",
    "upbit": "KRW",
    "binance": "USDT",
    "bybit": "USDT",
    "gate": "USDT",
}

KIMCHI_PREMIUM_PAIRS: list[tuple[str, str]] = [
    ("bithumb", "binance"),
    ("bithumb", "bybit"),
    ("bithumb", "gate"),
    ("upbit", "binance"),
    ("upbit", "bybit"),
    ("upbit", "gate"),
]

SAME_CURRENCY_PAIRS: list[tuple[str, str]] = [
    ("bithumb", "upbit"),
    ("binance", "bybit"),
    ("binance", "gate"),
    ("bybit", "gate"),
]

ALL_EXCHANGE_PAIRS: list[tuple[str, str]] = KIMCHI_PREMIUM_PAIRS + SAME_CURRENCY_PAIRS

DEFAULT_SYMBOLS: list[str] = ["BTC", "ETH", "XRP", "SOL", "DOGE"]

ALERT_SEVERITY_THRESHOLDS: dict[str, float] = {
    "critical": 3.0,
    "warning": 2.0,
    "info": 1.0,
}

# Staleness thresholds
PRICE_STALE_THRESHOLD_MS: int = 5_000   # 5 seconds
FX_RATE_STALE_THRESHOLD_MS: int = 60_000  # 60 seconds

# Database write interval
DB_WRITE_INTERVAL_SECONDS: float = 10.0

# Data retention
RETENTION_DAYS: int = 30
