"""Coinone WebSocket connector with REST polling fallback.

WebSocket endpoint: wss://stream.coinone.co.kr
REST fallback: GET https://api.coinone.co.kr/public/v2/ticker_new/KRW/{symbol}

Coinone WebSocket uses individual subscription messages per symbol.
All numeric fields in Coinone responses are strings. The WebSocket
response uses response_type='DATA' with channel='TICKER'.

If WebSocket connection fails repeatedly, falls back to REST polling
every 10 seconds per FallbackMode.REST_POLLING.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal

import aiohttp

from app.connectors.base import BaseConnector
from app.schemas.price import TickerUpdate
from app.utils.enums import ConnectorState, FallbackMode

logger = logging.getLogger(__name__)

_EXCHANGE_ID = "coinone"
_WS_URL = "wss://stream.coinone.co.kr"
_REST_BASE = "https://api.coinone.co.kr/public/v2/ticker_new/KRW"
_REST_POLL_INTERVAL_S = 10.0
_WS_FAIL_THRESHOLD = 3  # Switch to REST after this many consecutive WS failures


class CoinoneConnector(BaseConnector):
    """WebSocket connector for Coinone (KRW market) with REST polling fallback.

    When the WebSocket connection fails repeatedly (>=3 consecutive failures),
    the connector automatically switches to REST API polling mode. It continues
    attempting WebSocket reconnection in the background and switches back
    once the WebSocket is available again.
    """

    def __init__(self, symbols: list[str]) -> None:
        super().__init__(_EXCHANGE_ID, symbols)
        self.fallback_mode: FallbackMode = FallbackMode.NONE
        self._consecutive_ws_failures: int = 0
        self._rest_task: asyncio.Task | None = None

    @property
    def ws_url(self) -> str:
        return _WS_URL

    def build_subscribe_message(self) -> list[dict]:
        """Build Coinone ticker subscription messages.

        Coinone requires one subscription message per symbol.
        """
        return [
            {
                "request_type": "SUBSCRIBE",
                "channel": "TICKER",
                "topic": {
                    "quote_currency": "KRW",
                    "target_currency": sym,
                },
            }
            for sym in self.symbols
        ]

    def normalize(self, raw: dict) -> TickerUpdate | None:
        """Parse Coinone ticker message to canonical TickerUpdate.

        Coinone WebSocket ticker response format:
          response_type: 'DATA'
          channel: 'TICKER'
          data.target_currency: 'BTC'
          data.last: '88000000.0' (string)
          data.target_volume: '123.456' (string)
          data.timestamp: 1709107200000
          data.best_asks: [{"price": "...", "qty": "..."}]
          data.best_bids: [{"price": "...", "qty": "..."}]

        Also accepts response_type='TICKER' for the initial snapshot.
        Returns None for non-ticker messages (PONG, subscription ACKs).
        """
        resp_type = raw.get("response_type", "")
        channel = raw.get("channel", "")

        # Accept both DATA+TICKER and TICKER response types
        if resp_type == "DATA" and channel == "TICKER":
            data = raw.get("data", {})
        elif resp_type == "TICKER":
            data = raw.get("data", {})
        else:
            return None

        symbol: str = data.get("target_currency", "").upper()
        if symbol not in self.symbols:
            return None

        try:
            # Extract best bid/ask from arrays if present
            bid_price: Decimal | None = None
            ask_price: Decimal | None = None
            best_bids = data.get("best_bids", [])
            best_asks = data.get("best_asks", [])
            if best_bids and isinstance(best_bids, list) and len(best_bids) > 0:
                bid_price = Decimal(str(best_bids[0].get("price", "0")))
            if best_asks and isinstance(best_asks, list) and len(best_asks) > 0:
                ask_price = Decimal(str(best_asks[0].get("price", "0")))

            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=Decimal(str(data.get("last", "0"))),
                currency="KRW",
                volume_24h=Decimal(str(data.get("target_volume", "0"))),
                timestamp_ms=int(data.get("timestamp", time.time() * 1000)),
                received_at_ms=int(time.time() * 1000),
                bid_price=bid_price,
                ask_price=ask_price,
            )
        except Exception:
            logger.exception("[coinone] Failed to normalize message")
            return None

    def _normalize_rest(self, ticker: dict) -> TickerUpdate | None:
        """Normalize a Coinone REST API ticker response to TickerUpdate."""
        symbol: str = ticker.get("target_currency", "").upper()
        if symbol not in self.symbols:
            return None

        try:
            bid_price: Decimal | None = None
            ask_price: Decimal | None = None
            best_bids = ticker.get("best_bids", [])
            best_asks = ticker.get("best_asks", [])
            if best_bids and len(best_bids) > 0:
                bid_price = Decimal(str(best_bids[0].get("price", "0")))
            if best_asks and len(best_asks) > 0:
                ask_price = Decimal(str(best_asks[0].get("price", "0")))

            return TickerUpdate(
                exchange=_EXCHANGE_ID,
                symbol=symbol,
                price=Decimal(str(ticker.get("last", "0"))),
                currency="KRW",
                volume_24h=Decimal(str(ticker.get("target_volume", "0"))),
                timestamp_ms=int(ticker.get("timestamp", time.time() * 1000)),
                received_at_ms=int(time.time() * 1000),
                bid_price=bid_price,
                ask_price=ask_price,
            )
        except Exception:
            logger.exception("[coinone] Failed to normalize REST response")
            return None

    async def _rest_poll_loop(self) -> None:
        """Poll Coinone REST API for all tracked symbols periodically."""
        logger.info("[coinone] Starting REST polling fallback (interval=%ss)", _REST_POLL_INTERVAL_S)
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # Fetch all tickers in one call
                    url = f"{_REST_BASE}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("result") == "success":
                                self._last_message_ms = int(time.time() * 1000)
                                for ticker in data.get("tickers", []):
                                    tick = self._normalize_rest(ticker)
                                    if tick is not None and self._on_tick is not None:
                                        await self._on_tick.put(tick)
                        else:
                            logger.warning("[coinone] REST poll returned status %d", resp.status)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("[coinone] REST poll failed")

                await asyncio.sleep(_REST_POLL_INTERVAL_S)

    def start(self) -> asyncio.Task:
        """Override start to also handle REST fallback mode."""
        self._task = asyncio.create_task(
            self._run_with_fallback(), name=f"connector-{self.exchange_id}"
        )
        return self._task

    async def _run_with_fallback(self) -> None:
        """Wrapper around the WS loop that activates REST fallback on repeated failures."""
        import websockets

        while True:
            try:
                self._transition(ConnectorState.CONNECTING)
                t0 = time.monotonic()

                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._transition(ConnectorState.CONNECTED)
                    self._connected_since_ms = int(time.time() * 1000)
                    self._latency_ms = int((time.monotonic() - t0) * 1000)
                    self._consecutive_ws_failures = 0

                    # If REST fallback was running, stop it
                    if self._rest_task and not self._rest_task.done():
                        self._rest_task.cancel()
                        try:
                            await self._rest_task
                        except asyncio.CancelledError:
                            pass
                        self._rest_task = None
                    self.fallback_mode = FallbackMode.NONE

                    # Send subscriptions
                    self._transition(ConnectorState.SUBSCRIBING)
                    for msg in self.build_subscribe_message():
                        await ws.send(json.dumps(msg))

                    self._transition(ConnectorState.ACTIVE)
                    self._reconnect_count = 0

                    async for raw_data in ws:
                        self._last_message_ms = int(time.time() * 1000)
                        try:
                            if isinstance(raw_data, bytes):
                                raw_data = raw_data.decode("utf-8")
                            raw = json.loads(raw_data)

                            # Handle PONG/heartbeat
                            if raw.get("response_type") == "PONG":
                                continue

                            tick = self.normalize(raw)
                            if tick is not None and self._on_tick is not None:
                                await self._on_tick.put(tick)
                        except Exception:
                            logger.exception("[coinone] Failed to process WS message")

            except asyncio.CancelledError:
                # Clean up REST task if running
                if self._rest_task and not self._rest_task.done():
                    self._rest_task.cancel()
                    try:
                        await self._rest_task
                    except asyncio.CancelledError:
                        pass
                raise

            except Exception as exc:
                self._consecutive_ws_failures += 1
                delay = self._backoff_delay()
                self._reconnect_count += 1
                self._transition(
                    ConnectorState.WAIT_RETRY,
                    reason=f"{type(exc).__name__}: {exc} — retry in {delay:.1f}s",
                )

                # Start REST fallback if threshold exceeded
                if (
                    self._consecutive_ws_failures >= _WS_FAIL_THRESHOLD
                    and self.fallback_mode != FallbackMode.REST_POLLING
                ):
                    self.fallback_mode = FallbackMode.REST_POLLING
                    logger.warning(
                        "[coinone] %d consecutive WS failures — activating REST polling fallback",
                        self._consecutive_ws_failures,
                    )
                    if self._rest_task is None or self._rest_task.done():
                        self._rest_task = asyncio.create_task(
                            self._rest_poll_loop(), name="coinone-rest-fallback"
                        )

                await asyncio.sleep(delay)
