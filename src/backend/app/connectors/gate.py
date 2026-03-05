"""Gate.io V4 WebSocket connector.

WebSocket endpoint: wss://api.gateio.ws/ws/v4/
Subscription: {"time": <epoch>, "channel": "spot.tickers", "event": "subscribe", "payload": ["BTC_USDT", ...]}

Gate.io V4 ticker messages contain:
  channel: 'spot.tickers'
  event: 'update'
  result: {currency_pair, last, highest_bid, lowest_ask, base_volume, ...}
  time: epoch seconds
  time_ms: epoch ms

Gate.io uses application-level ping/pong:
  Client sends: {"time": <epoch>, "channel": "spot.ping"}
  Server replies: {"time": ..., "channel": "spot.pong"}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal

from app.connectors.base import BaseConnector
from app.schemas.price import TickerUpdate

logger = logging.getLogger(__name__)

_EXCHANGE_ID = "gate"
_WS_URL = "wss://api.gateio.ws/ws/v4/"
_PING_INTERVAL_S = 15


class GateConnector(BaseConnector):
    """WebSocket connector for Gate.io V4 (USDT spot market).

    Subscribes to spot.tickers for each tracked symbol.
    Overrides _run_loop to handle Gate.io's application-level ping/pong.
    """

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(_EXCHANGE_ID, symbols)

    @property
    def ws_url(self) -> str:
        return _WS_URL

    def build_subscribe_message(self) -> dict:
        """Build Gate.io V4 ticker subscription message."""
        payload = [f"{sym}_USDT" for sym in self.symbols]
        return {
            "time": int(time.time()),
            "channel": "spot.tickers",
            "event": "subscribe",
            "payload": payload,
        }

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Gate.io V4 ticker message to canonical TickerUpdate.

        Gate.io ticker fields:
            channel: 'spot.tickers'
            event: 'update'
            result:
                currency_pair: 'BTC_USDT'
                last: '65000.50'
                highest_bid: '64999.90'
                lowest_ask: '65000.20'
                base_volume: '45678.1234'
                quote_volume: '2958000000'
                high_24h: '66000.00'
                low_24h: '64000.00'
            time: 1709107200
            time_ms: 1709107200123

        Subscription ACKs have event='subscribe', pong has channel='spot.pong'.
        Returns None for non-ticker messages.
        """
        channel = raw.get("channel", "")
        event = raw.get("event", "")

        # Skip non-update messages (subscribe ACK, pong, etc.)
        if event != "update" or channel != "spot.tickers":
            return None

        result = raw.get("result")
        if not result:
            return None

        pair: str = result.get("currency_pair", "")
        if not pair.endswith("_USDT"):
            return None

        symbol = pair.replace("_USDT", "").upper()
        if symbol not in self.symbols:
            return None

        try:
            last_price = result.get("last", "0")
            if not last_price or last_price == "0":
                return None

            bid: Decimal | None = None
            ask: Decimal | None = None
            if result.get("highest_bid"):
                bid = Decimal(str(result["highest_bid"]))
            if result.get("lowest_ask"):
                ask = Decimal(str(result["lowest_ask"]))

            ts_ms = raw.get("time_ms") or int(raw.get("time", time.time()) * 1000)

            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=Decimal(str(last_price)),
                currency="USDT",
                volume_24h=Decimal(str(result.get("base_volume", "0"))),
                timestamp_ms=int(ts_ms),
                received_at_ms=int(time.time() * 1000),
                bid_price=bid,
                ask_price=ask,
            )
        except Exception:
            logger.exception("[gate] Failed to normalize message")
            return None

    async def _run_loop(self) -> None:
        """Main loop with Gate.io application-level ping/pong.

        Gate.io doesn't use standard WebSocket ping frames reliably,
        so we send periodic application-level pings.
        """
        import websockets
        from app.utils.enums import ConnectorState

        while True:
            try:
                self._transition(ConnectorState.CONNECTING)
                t0 = time.monotonic()

                async with websockets.connect(
                    self.ws_url,
                    ping_interval=None,  # Disable library-level ping
                    ping_timeout=None,
                    close_timeout=10,
                ) as ws:
                    self._transition(ConnectorState.CONNECTED)
                    self._connected_since_ms = int(time.time() * 1000)
                    self._latency_ms = int((time.monotonic() - t0) * 1000)

                    # Send subscription
                    self._transition(ConnectorState.SUBSCRIBING)
                    sub_msg = self.build_subscribe_message()
                    await ws.send(json.dumps(sub_msg))

                    self._transition(ConnectorState.ACTIVE)
                    self._reconnect_count = 0

                    async def _ping_loop() -> None:
                        while True:
                            await asyncio.sleep(_PING_INTERVAL_S)
                            ping_msg = {
                                "time": int(time.time()),
                                "channel": "spot.ping",
                            }
                            await ws.send(json.dumps(ping_msg))

                    ping_task = asyncio.create_task(_ping_loop(), name="gate-ping")
                    try:
                        async for raw_data in ws:
                            self._last_message_ms = int(time.time() * 1000)
                            try:
                                if isinstance(raw_data, bytes):
                                    raw_data = raw_data.decode("utf-8")
                                raw = json.loads(raw_data)
                                tick = self.normalize(raw)
                                if tick is not None and self._on_tick is not None:
                                    await self._on_tick.put(tick)
                            except Exception:
                                logger.exception("[%s] Failed to process message", self.exchange_id)
                    finally:
                        ping_task.cancel()
                        try:
                            await ping_task
                        except asyncio.CancelledError:
                            pass

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                delay = self._backoff_delay()
                self._reconnect_count += 1
                self._transition(
                    ConnectorState.WAIT_RETRY,
                    reason=f"{type(exc).__name__}: {exc} — retry in {delay:.1f}s",
                )
                await asyncio.sleep(delay)
