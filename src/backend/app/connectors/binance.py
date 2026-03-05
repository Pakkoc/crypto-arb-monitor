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
    last trade prices and bookTicker for best bid/ask.
    No explicit subscription message is needed — streams are in the URL.
    """

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(_EXCHANGE_ID, symbols)
        self._best_bid: dict[str, Decimal] = {}
        self._best_ask: dict[str, Decimal] = {}

    @property
    def ws_url(self) -> str:
        """Build combined stream URL with miniTicker streams for all symbols.

        Example: wss://stream.binance.com:9443/stream?streams=btcusdt@miniTicker/ethusdt@miniTicker
        """
        ticker_streams = [f"{sym.lower()}usdt@miniTicker" for sym in self.symbols]
        book_streams = [f"{sym.lower()}usdt@bookTicker" for sym in self.symbols]
        streams = "/".join(ticker_streams + book_streams)
        return f"{_WS_BASE}/stream?streams={streams}"

    def build_subscribe_message(self) -> dict:
        """No explicit subscription needed for combined stream URLs.

        The streams are specified in the URL itself. Return empty dict
        which the base class will skip sending.
        """
        return {}

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Binance miniTicker/bookTicker message to canonical TickerUpdate.

        Combined stream wrapper: {"stream": "btcusdt@miniTicker", "data": {...}}

        miniTicker data: E, s, c (close/last), v (volume), etc.
        bookTicker data: s, b (best bid), B (bid qty), a (best ask), A (ask qty)

        bookTicker messages update cached bid/ask; miniTicker emits TickerUpdate.
        """
        stream: str = raw.get("stream", "")
        data = raw.get("data", raw)
        symbol_raw: str = data.get("s", "")
        if not symbol_raw.endswith("USDT"):
            return None
        symbol = symbol_raw[:-4].upper()  # BTCUSDT → BTC
        if symbol not in self.symbols:
            return None

        # Handle bookTicker — cache best bid/ask
        if "@bookTicker" in stream:
            try:
                if data.get("b"):
                    self._best_bid[symbol] = Decimal(str(data["b"]))
                if data.get("a"):
                    self._best_ask[symbol] = Decimal(str(data["a"]))
            except Exception:
                logger.exception("[binance] Failed to parse bookTicker")
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
                bid_price=self._best_bid.get(symbol),
                ask_price=self._best_ask.get(symbol),
            )
        except Exception:
            logger.exception("[binance] Failed to normalize message")
            return None
