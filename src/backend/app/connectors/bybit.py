"""Bybit V5 WebSocket connector.

WebSocket endpoint: wss://stream.bybit.com/v5/public/spot
Subscription: {"op": "subscribe", "args": ["tickers.BTCUSDT"]}

Bybit V5 ticker messages contain:
  topic: 'tickers.BTCUSDT'
  type: 'snapshot' (first message) or 'delta' (subsequent updates)
  data: {symbol, lastPrice, bid1Price, bid1Size, ask1Price, ask1Size, volume24h, ...}
  ts: timestamp in ms

Bybit provides the highest-frequency spot ticker at ~50ms intervals.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from app.connectors.base import BaseConnector
from app.schemas.price import TickerUpdate

logger = logging.getLogger(__name__)

_EXCHANGE_ID = "bybit"
_WS_URL = "wss://stream.bybit.com/v5/public/spot"


class BybitConnector(BaseConnector):
    """WebSocket connector for Bybit V5 (USDT spot market).

    Subscribes to the tickers topic for each tracked symbol.
    Handles both 'snapshot' and 'delta' message types.
    """

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(_EXCHANGE_ID, symbols)
        # Cache bid/ask across delta messages (delta may only contain lastPrice)
        self._best_bid: dict[str, Decimal] = {}
        self._best_ask: dict[str, Decimal] = {}

    @property
    def ws_url(self) -> str:
        return _WS_URL

    def build_subscribe_message(self) -> list[dict]:
        """Build Bybit V5 subscription messages.

        Subscribes to:
        - tickers.{SYMBOL}USDT for price data
        - orderbook.1.{SYMBOL}USDT for best bid/ask
        """
        ticker_topics = [f"tickers.{sym}USDT" for sym in self.symbols]
        ob_topics = [f"orderbook.1.{sym}USDT" for sym in self.symbols]
        return [
            {"op": "subscribe", "args": ticker_topics},
            {"op": "subscribe", "args": ob_topics},
        ]

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Bybit V5 ticker message to canonical TickerUpdate.

        Bybit ticker fields:
            topic: 'tickers.BTCUSDT'
            type: 'snapshot' or 'delta'
            data:
                symbol: 'BTCUSDT'
                lastPrice: '65000.50'
                bid1Price: '64999.90'
                bid1Size: '1.5'
                ask1Price: '65000.20'
                ask1Size: '0.8'
                volume24h: '45678.1234'
                turnover24h: '2958000000'
                highPrice24h: '66000.00'
                lowPrice24h: '64000.00'
            ts: 1709107200000

        Subscription confirmations have 'op': 'subscribe' and are ignored.
        Returns None for non-ticker messages.
        """
        # Skip subscription confirmations and pong responses
        if raw.get("op") in ("subscribe", "pong"):
            return None

        topic: str = raw.get("topic", "")

        # Handle orderbook.1 messages for bid/ask caching
        if topic.startswith("orderbook.1."):
            data = raw.get("data", {})
            sym_raw = topic.replace("orderbook.1.", "")
            if sym_raw.endswith("USDT"):
                sym = sym_raw[:-4].upper()
                bids = data.get("b", [])
                asks = data.get("a", [])
                if bids:
                    self._best_bid[sym] = Decimal(str(bids[0][0]))
                if asks:
                    self._best_ask[sym] = Decimal(str(asks[0][0]))
            return None  # Don't emit TickerUpdate from orderbook

        if not topic.startswith("tickers."):
            return None

        data = raw.get("data", {})
        symbol_raw: str = data.get("symbol", topic.replace("tickers.", ""))
        if not symbol_raw.endswith("USDT"):
            return None

        symbol = symbol_raw[:-4].upper()  # BTCUSDT → BTC
        if symbol not in self.symbols:
            return None

        try:
            last_price = data.get("lastPrice", "0")
            if not last_price or last_price == "0":
                return None

            # Update cached bid/ask when present in message
            if data.get("bid1Price"):
                self._best_bid[symbol] = Decimal(str(data["bid1Price"]))
            if data.get("ask1Price"):
                self._best_ask[symbol] = Decimal(str(data["ask1Price"]))
            bid = self._best_bid.get(symbol)
            ask = self._best_ask.get(symbol)

            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=Decimal(str(last_price)),
                currency="USDT",
                volume_24h=Decimal(str(data.get("volume24h", "0"))),
                timestamp_ms=int(raw.get("ts", time.time() * 1000)),
                received_at_ms=int(time.time() * 1000),
                bid_price=bid,
                ask_price=ask,
            )
        except Exception:
            logger.exception("[bybit] Failed to normalize message")
            return None
