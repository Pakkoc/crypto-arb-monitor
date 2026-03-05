"""Upbit WebSocket connector.

WebSocket endpoint: wss://api.upbit.com/websocket/v1
Market code format: KRW-BTC (hyphen-separated, currency first, uppercase)

Upbit accepts a JSON array subscription: [ticket, {type, codes}, format]
Uses SIMPLE format for bandwidth efficiency. Also subscribes to KRW-USDT
for the FX rate needed by kimchi premium calculation.
"""
from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal

from app.connectors.base import BaseConnector
from app.schemas.price import TickerUpdate

logger = logging.getLogger(__name__)

_EXCHANGE_ID = "upbit"
_WS_URL = "wss://api.upbit.com/websocket/v1"


class UpbitConnector(BaseConnector):
    """WebSocket connector for Upbit (KRW market).

    Also subscribes to KRW-USDT for FX rate updates used in kimchi premium
    calculation (DD-4).
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
        """Build Upbit ticker subscription messages.

        Upbit expects the message to be a JSON array:
        [ticket, {type, codes, isOnlyRealtime}, format]

        SIMPLE format uses abbreviated keys (ty, cd, tp, tv, tms, etc.)
        for lower bandwidth. Also includes KRW-USDT for FX rate extraction.
        """
        codes = [f"KRW-{sym}" for sym in self.symbols]
        # Also include KRW-USDT for FX rate
        if "KRW-USDT" not in codes:
            codes.append("KRW-USDT")
        return [
            {"ticket": f"arb-monitor-upbit-{uuid.uuid4().hex[:8]}"},
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
            {"format": "SIMPLE"},
        ]

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Upbit SIMPLE format ticker/orderbook message to canonical TickerUpdate.

        Upbit SIMPLE format keys for ticker (ty='ticker'):
            cd: code, tp: trade_price, tms: timestamp, atv24h: volume_24h

        Upbit SIMPLE format keys for orderbook (ty='orderbook'):
            cd: code, obu: orderbook_units
            obu[0].bp: best bid price, obu[0].ap: best ask price

        Orderbook messages update cached bid/ask, ticker messages emit TickerUpdate.
        """
        msg_type = raw.get("ty")

        # Handle orderbook messages — cache best bid/ask
        if msg_type == "orderbook":
            code: str = raw.get("cd", "")
            if code.startswith("KRW-"):
                symbol = code[4:].upper()
                units = raw.get("obu", [])
                if units:
                    best = units[0]
                    if best.get("bp"):
                        self._best_bid[symbol] = Decimal(str(best["bp"]))
                    if best.get("ap"):
                        self._best_ask[symbol] = Decimal(str(best["ap"]))
            return None

        if msg_type != "ticker":
            return None

        code = raw.get("cd", "")
        if not code.startswith("KRW-"):
            return None

        symbol = code[4:].upper()  # KRW-BTC → BTC
        if symbol not in self.symbols and symbol != "USDT":
            return None

        try:
            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=Decimal(str(raw.get("tp", "0"))),
                currency="KRW",
                volume_24h=Decimal(str(raw.get("atv24h", "0"))),
                timestamp_ms=int(raw.get("tms", time.time() * 1000)),
                received_at_ms=int(time.time() * 1000),
                bid_price=self._best_bid.get(symbol),
                ask_price=self._best_ask.get(symbol),
            )
        except Exception:
            logger.exception("[upbit] Failed to normalize message")
            return None
