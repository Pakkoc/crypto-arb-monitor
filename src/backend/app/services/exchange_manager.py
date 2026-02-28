"""ExchangeManager — orchestrates all 5 exchange connectors.

Responsibilities:
- Instantiate and start all 5 connectors as asyncio Tasks
- Provide the shared asyncio.Queue for TickerUpdate routing
- Expose connector state for the health endpoint
- Provide connector-level metadata (ws_url, currency, name)
"""
from __future__ import annotations

import asyncio
import logging

from app.connectors.base import BaseConnector
from app.connectors.bithumb import BithumbConnector
from app.connectors.upbit import UpbitConnector
from app.connectors.coinone import CoinoneConnector
from app.connectors.binance import BinanceConnector
from app.connectors.bybit import BybitConnector
from app.schemas.price import TickerUpdate
from app.utils.enums import (
    ConnectorState,
    DEFAULT_SYMBOLS,
    EXCHANGE_CURRENCY,
    FallbackMode,
    PRICE_STALE_THRESHOLD_MS,
)

logger = logging.getLogger(__name__)

# Display name mapping
_EXCHANGE_NAMES: dict[str, str] = {
    "bithumb": "Bithumb",
    "upbit": "Upbit",
    "coinone": "Coinone",
    "binance": "Binance",
    "bybit": "Bybit",
}


class ExchangeManager:
    """Manages the lifecycle of all exchange WebSocket connectors.

    Architecture reference: DD-1 (single-process event-driven).
    All connectors run as asyncio Tasks within the same event loop.
    """

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols: list[str] = symbols or list(DEFAULT_SYMBOLS)
        self._tick_queue: asyncio.Queue[TickerUpdate] = asyncio.Queue(maxsize=10_000)
        self._connectors: dict[str, BaseConnector] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Instantiate all connectors and start their tasks."""
        self._connectors = {
            "bithumb": BithumbConnector(self.symbols),
            "upbit": UpbitConnector(self.symbols),
            "coinone": CoinoneConnector(self.symbols),
            "binance": BinanceConnector(self.symbols),
            "bybit": BybitConnector(self.symbols),
        }
        for connector in self._connectors.values():
            connector.attach_queue(self._tick_queue)
            connector.start()

        logger.info("ExchangeManager: started %d connectors for symbols %s",
                     len(self._connectors), self.symbols)

    async def stop(self) -> None:
        """Stop all connectors gracefully."""
        for connector in self._connectors.values():
            await connector.stop()
        logger.info("ExchangeManager: all connectors stopped")

    # ── State inspection ───────────────────────────────────────────────────────

    def get_connector(self, exchange_id: str) -> BaseConnector | None:
        """Return a specific connector by exchange ID."""
        return self._connectors.get(exchange_id)

    def get_connector_states(self) -> dict[str, dict]:
        """Return a status snapshot for each connector (used by health endpoint)."""
        result: dict[str, dict] = {}
        for ex_id, c in self._connectors.items():
            info: dict = {
                "id": ex_id,
                "name": _EXCHANGE_NAMES.get(ex_id, ex_id),
                "currency": EXCHANGE_CURRENCY.get(ex_id, "UNKNOWN"),
                "state": c.state.value,
                "ws_url": c.ws_url,
                "last_message_ms": c.last_message_ms,
                "latency_ms": c.latency_ms,
                "reconnect_count": c.reconnect_count,
                "connected_since_ms": c.connected_since_ms,
                "is_stale": c.is_stale,
                "stale_threshold_ms": PRICE_STALE_THRESHOLD_MS,
                "supported_symbols": list(self.symbols),
            }
            # Add Coinone-specific fallback info
            if hasattr(c, "fallback_mode") and c.fallback_mode != FallbackMode.NONE:
                info["fallback_mode"] = c.fallback_mode.value
            result[ex_id] = info
        return result

    def get_connected_count(self) -> int:
        """Return the number of connectors in ACTIVE state."""
        return sum(
            1 for c in self._connectors.values()
            if c.state == ConnectorState.ACTIVE
        )

    def get_disconnected_count(self) -> int:
        """Return the number of connectors NOT in ACTIVE state."""
        return sum(
            1 for c in self._connectors.values()
            if c.state != ConnectorState.ACTIVE
        )

    @property
    def tick_queue(self) -> asyncio.Queue[TickerUpdate]:
        """The shared queue from which PriceStore consumes ticks."""
        return self._tick_queue

    @property
    def connectors(self) -> dict[str, BaseConnector]:
        """Direct access to connectors dict (read-only use)."""
        return self._connectors
