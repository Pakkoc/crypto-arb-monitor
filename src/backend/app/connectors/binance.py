"""Binance WebSocket connector.

WebSocket endpoint: wss://stream.binance.com:9443/stream?streams=...
Uses combined stream with miniTicker for last trade price.

Binance combined stream wraps data: {"stream": "btcusdt@miniTicker", "data": {...}}
miniTicker fields (single-character abbreviations):
  s: symbol (BTCUSDT), c: close/last price, o: open price,
  h: high price, l: low price, v: base volume, q: quote volume,
  E: event time (ms)
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from app.connectors.base import BaseConnector
from app.schemas.price import TickerUpdate

logger = logging.getLogger(__name__)

_EXCHANGE_ID = "binance"
_WS_BASE = "wss://stream.binance.com:9443"


class BinanceConnector(BaseConnector):
    """WebSocket connector for Binance (USDT spot market).

    Uses the combined stream endpoint with miniTicker for real-time
    last trade prices. No explicit subscription message is needed
    when using combined stream URLs — the streams are specified in the URL.
    """

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(_EXCHANGE_ID, symbols)

    @property
    def ws_url(self) -> str:
        """Build combined stream URL with miniTicker streams for all symbols.

        Example: wss://stream.binance.com:9443/stream?streams=btcusdt@miniTicker/ethusdt@miniTicker
        """
        streams = "/".join(f"{sym.lower()}usdt@miniTicker" for sym in self.symbols)
        return f"{_WS_BASE}/stream?streams={streams}"

    def build_subscribe_message(self) -> dict:
        """No explicit subscription needed for combined stream URLs.

        The streams are specified in the URL itself. Return empty dict
        which the base class will skip sending.
        """
        return {}

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Binance miniTicker message to canonical TickerUpdate.

        Combined stream wrapper: {"stream": "btcusdt@miniTicker", "data": {...}}
        miniTicker data fields:
            E: event time (ms)
            s: symbol (e.g., 'BTCUSDT')
            c: close price (= last trade price)
            o: open price
            h: high price
            l: low price
            v: total traded base asset volume
            q: total traded quote asset volume

        Uses close price (c) as the canonical price — this is the last
        trade price, consistent with all other exchange connectors.
        """
        # Combined stream wraps data in {'stream': ..., 'data': {...}}
        data = raw.get("data", raw)
        symbol_raw: str = data.get("s", "")
        if not symbol_raw.endswith("USDT"):
            return None
        symbol = symbol_raw[:-4].upper()  # BTCUSDT → BTC
        if symbol not in self.symbols:
            return None

        try:
            price = Decimal(str(data.get("c", "0")))
            if price == 0:
                return None
            event_time = int(data.get("E", time.time() * 1000))
            volume = Decimal(str(data.get("v", "0")))
            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=price,
                currency="USDT",
                volume_24h=volume,
                timestamp_ms=event_time,
                received_at_ms=int(time.time() * 1000),
                bid_price=None,
                ask_price=None,
            )
        except Exception:
            logger.exception("[binance] Failed to normalize message")
            return None
