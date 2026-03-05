"""Bithumb WebSocket connector.

WebSocket endpoint: wss://ws-api.bithumb.com/websocket/v1
Market code format: KRW-BTC (hyphen-separated, currency first, uppercase)

Bithumb v1 WebSocket uses the same protocol as Upbit:
  - Subscription as JSON array: [ticket, {type, codes}, format]
  - Ticker messages with type='ticker', code='KRW-BTC', trade_price, etc.
"""
from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal

from app.connectors.base import BaseConnector
from app.schemas.price import TickerUpdate

logger = logging.getLogger(__name__)

_EXCHANGE_ID = "bithumb"
_WS_URL = "wss://ws-api.bithumb.com/websocket/v1"


class BithumbConnector(BaseConnector):
    """WebSocket connector for Bithumb (KRW market).

    Uses the current /v1/ WebSocket API with KRW-BTC market code format.
    Subscribes to both ticker and orderbook for bid/ask prices.
    """

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(_EXCHANGE_ID, symbols)
        self._subscribe_as_single_array = True
        self._best_bid: dict[str, Decimal] = {}
        self._best_ask: dict[str, Decimal] = {}

    @property
    def ws_url(self) -> str:
        return _WS_URL

    def build_subscribe_message(self) -> list[dict]:
        """Build Bithumb v1 ticker subscription messages.

        Bithumb v1 format is identical to Upbit:
        [{"ticket": "..."}, {"type": "ticker", "codes": ["KRW-BTC"], "isOnlyRealtime": true}, {"format": "DEFAULT"}]
        """
        codes = [f"KRW-{sym}" for sym in self.symbols]
        return [
            {"ticket": f"arb-monitor-bithumb-{uuid.uuid4().hex[:8]}"},
            {
                "type": "ticker",
                "codes": codes,
                "isOnlyRealtime": True,
            },
            {
                "type": "orderbook",
                "codes": codes,
                "isOnlyRealtime": True,
            },
            {"format": "DEFAULT"},
        ]

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Bithumb v1 ticker/orderbook message to canonical TickerUpdate.

        Returns None for non-ticker messages (ACKs, status, errors).
        Orderbook messages update the cached best bid/ask which are
        injected into subsequent ticker updates.
        """
        msg_type = raw.get("type")

        # Handle orderbook messages — cache best bid/ask
        if msg_type == "orderbook":
            code: str = raw.get("code", "")
            if code.startswith("KRW-"):
                symbol = code[4:].upper()
                units = raw.get("orderbook_units", [])
                if units:
                    best = units[0]
                    if best.get("bid_price"):
                        self._best_bid[symbol] = Decimal(str(best["bid_price"]))
                    if best.get("ask_price"):
                        self._best_ask[symbol] = Decimal(str(best["ask_price"]))
            return None

        if msg_type != "ticker":
            return None

        code = raw.get("code", "")
        if not code.startswith("KRW-"):
            return None

        symbol = code[4:].upper()  # KRW-BTC → BTC
        if symbol not in self.symbols:
            return None

        try:
            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=Decimal(str(raw.get("trade_price", "0"))),
                currency="KRW",
                volume_24h=Decimal(str(raw.get("acc_trade_volume_24h", "0"))),
                timestamp_ms=int(raw.get("timestamp", time.time() * 1000)),
                received_at_ms=int(time.time() * 1000),
                bid_price=self._best_bid.get(symbol),
                ask_price=self._best_ask.get(symbol),
            )
        except Exception:
            logger.exception("[bithumb] Failed to normalize message")
            return None
