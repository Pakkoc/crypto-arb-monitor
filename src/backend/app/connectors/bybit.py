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

    @property
    def ws_url(self) -> str:
        return _WS_URL

    def build_subscribe_message(self) -> dict:
        """Build Bybit V5 ticker subscription message.

        Subscribes to tickers.{SYMBOL}USDT for each tracked symbol.
        """
        topics = [f"tickers.{sym}USDT" for sym in self.symbols]
        return {"op": "subscribe", "args": topics}

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

            bid: Decimal | None = None
            ask: Decimal | None = None
            if data.get("bid1Price"):
                bid = Decimal(str(data["bid1Price"]))
            if data.get("ask1Price"):
                ask = Decimal(str(data["ask1Price"]))

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
