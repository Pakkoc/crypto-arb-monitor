"""PriceStore — in-memory latest price cache with periodic DB snapshots.

Holds the most recent TickerUpdate per (exchange, symbol) key.
Consumes from ExchangeManager's tick queue; read by SpreadCalculator and the API.

Also tracks the current KRW/USD FX rate sourced from Upbit's KRW-USDT
ticker, and periodically writes price snapshots to SQLite (every 10s).

Architecture reference: DD-2 (in-memory price store), DD-8 (SQLite persistence).
"""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Callable, Coroutine, Any

from app.schemas.price import TickerUpdate
from app.utils.enums import (
    DB_WRITE_INTERVAL_SECONDS,
    PRICE_STALE_THRESHOLD_MS,
    FX_RATE_STALE_THRESHOLD_MS,
)

logger = logging.getLogger(__name__)


class PriceStore:
    """Thread-safe (asyncio single-thread) in-memory cache of latest prices.

    Key: (exchange_id, symbol) tuple
    Value: TickerUpdate dataclass

    Also tracks the current KRW/USD FX rate sourced from Upbit's KRW-USDT
    ticker or the ExchangeRate-API fallback.
    """

    def __init__(self) -> None:
        # (exchange_id, symbol) → TickerUpdate
        self._prices: dict[tuple[str, str], TickerUpdate] = {}

        # FX rate state
        self._fx_rate: Decimal | None = None
        self._fx_source: str | None = None
        self._fx_timestamp_ms: int | None = None

        # Callbacks invoked on each price update (registered by SpreadCalculator)
        self._on_update_callbacks: list[Callable[[TickerUpdate], Coroutine[Any, Any, None]]] = []

        # Consumer task
        self._consumer_task: asyncio.Task | None = None
        # DB snapshot task
        self._snapshot_task: asyncio.Task | None = None

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    def start_consumer(self, tick_queue: asyncio.Queue[TickerUpdate]) -> asyncio.Task:
        """Start the async consumer loop that drains the tick queue."""
        self._consumer_task = asyncio.create_task(
            self._consume_loop(tick_queue), name="price-store-consumer"
        )
        return self._consumer_task

    def start_db_snapshots(self) -> asyncio.Task:
        """Start the periodic DB snapshot writer."""
        self._snapshot_task = asyncio.create_task(
            self._snapshot_loop(), name="price-store-snapshots"
        )
        return self._snapshot_task

    async def stop(self) -> None:
        """Cancel consumer and snapshot tasks."""
        for task in (self._consumer_task, self._snapshot_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def on_update(self, callback: Callable[[TickerUpdate], Coroutine[Any, Any, None]]) -> None:
        """Register a callback invoked on each price update."""
        self._on_update_callbacks.append(callback)

    # ── Consumer loop ───────────────────────────────────────────────────────────

    async def _consume_loop(self, queue: asyncio.Queue[TickerUpdate]) -> None:
        """Continuously drain the tick queue and update the cache.

        Drains ALL available ticks first (non-blocking batch), then runs
        callbacks once for the latest tick per (exchange, symbol).
        This prevents the queue from backing up while callbacks execute,
        which would cause exchange WebSocket keepalive ping timeouts.
        """
        logger.info("PriceStore: consumer loop started")
        while True:
            try:
                # Wait for at least one tick
                tick = await queue.get()
                batch: list[TickerUpdate] = [tick]
                queue.task_done()

                # Drain all immediately available ticks (non-blocking)
                while not queue.empty():
                    try:
                        t = queue.get_nowait()
                        batch.append(t)
                        queue.task_done()
                    except asyncio.QueueEmpty:
                        break

                # Update cache for all ticks (instant, no I/O)
                latest: dict[tuple[str, str], TickerUpdate] = {}
                for t in batch:
                    self.update(t)
                    latest[(t.exchange, t.symbol)] = t

                # Run callbacks only for the latest tick per key
                for t in latest.values():
                    for cb in self._on_update_callbacks:
                        try:
                            await cb(t)
                        except Exception:
                            logger.exception("PriceStore: callback error")

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("PriceStore: consumer error")

    # ── DB snapshot loop ────────────────────────────────────────────────────────

    async def _snapshot_loop(self) -> None:
        """Periodically write current prices and FX rate to the database."""
        logger.info("PriceStore: DB snapshot loop started (interval=%ss)",
                     DB_WRITE_INTERVAL_SECONDS)
        while True:
            try:
                await asyncio.sleep(DB_WRITE_INTERVAL_SECONDS)
                await self._write_snapshots()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("PriceStore: snapshot write failed")

    async def _write_snapshots(self) -> None:
        """Write all current prices to the database as PriceSnapshot rows."""
        from app.database import async_session_factory  # noqa: PLC0415
        if async_session_factory is None:
            return

        prices = dict(self._prices)  # snapshot of current state
        if not prices:
            return

        from app.models.price import PriceSnapshot  # noqa: PLC0415
        from app.models.user import FxRateHistory  # noqa: PLC0415

        try:
            async with async_session_factory() as session:
                async with session.begin():
                    records = [
                        PriceSnapshot(
                            exchange_id=tick.exchange,
                            symbol=tick.symbol,
                            price=str(tick.price),
                            currency=tick.currency,
                            bid_price=str(tick.bid_price) if tick.bid_price is not None else None,
                            ask_price=str(tick.ask_price) if tick.ask_price is not None else None,
                            volume_24h=str(tick.volume_24h),
                            exchange_timestamp_ms=tick.timestamp_ms,
                            received_at_ms=tick.received_at_ms,
                        )
                        for tick in prices.values()
                    ]

                    # Also write FX rate if available
                    if self._fx_rate is not None and self._fx_timestamp_ms is not None:
                        records.append(FxRateHistory(
                            rate=str(self._fx_rate),
                            source=self._fx_source or "unknown",
                            timestamp_ms=self._fx_timestamp_ms,
                        ))

                    session.add_all(records)

            logger.debug("PriceStore: wrote %d price snapshots to DB", len(prices))
        except Exception:
            logger.exception("PriceStore: DB write error")

    # ── Write ──────────────────────────────────────────────────────────────────

    def update(self, tick: TickerUpdate) -> None:
        """Store a new price tick. Upbit USDT ticks update the FX rate."""
        # Upbit KRW-USDT ticker → update FX rate
        if tick.exchange == "upbit" and tick.symbol == "USDT":
            self._fx_rate = tick.price
            self._fx_source = "upbit"
            self._fx_timestamp_ms = tick.timestamp_ms
            return  # Not a tracked asset price; don't store in prices dict

        self._prices[(tick.exchange, tick.symbol)] = tick

    def update_fx_fallback(self, rate: Decimal, source: str) -> None:
        """Update FX rate from the ExchangeRate-API fallback."""
        self._fx_rate = rate
        self._fx_source = source
        self._fx_timestamp_ms = int(time.time() * 1000)

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(self, exchange: str, symbol: str) -> TickerUpdate | None:
        """Return the latest tick for (exchange, symbol), or None if not seen yet."""
        return self._prices.get((exchange, symbol))

    def get_all(self) -> dict[tuple[str, str], TickerUpdate]:
        """Return a copy of the full price cache."""
        return dict(self._prices)

    def get_by_symbol(self, symbol: str) -> dict[str, TickerUpdate]:
        """Return latest prices for a symbol across all exchanges."""
        return {
            exchange: tick
            for (exchange, sym), tick in self._prices.items()
            if sym == symbol
        }

    def get_by_exchange(self, exchange: str) -> dict[str, TickerUpdate]:
        """Return latest prices for an exchange across all symbols."""
        return {
            sym: tick
            for (ex, sym), tick in self._prices.items()
            if ex == exchange
        }

    @property
    def fx_rate(self) -> Decimal | None:
        return self._fx_rate

    @property
    def fx_source(self) -> str | None:
        return self._fx_source

    @property
    def fx_timestamp_ms(self) -> int | None:
        return self._fx_timestamp_ms

    @property
    def is_fx_stale(self) -> bool:
        if self._fx_timestamp_ms is None:
            return True
        return (int(time.time() * 1000) - self._fx_timestamp_ms) > FX_RATE_STALE_THRESHOLD_MS

    def is_stale(self, exchange: str, symbol: str) -> bool:
        """Return True if the price for (exchange, symbol) is older than the threshold."""
        tick = self._prices.get((exchange, symbol))
        if tick is None:
            return True
        return (int(time.time() * 1000) - tick.timestamp_ms) > PRICE_STALE_THRESHOLD_MS

    def get_fx_info(self) -> dict:
        """Return FX rate info as a dict suitable for API responses."""
        return {
            "rate": str(self._fx_rate) if self._fx_rate else "0",
            "source": self._fx_source or "none",
            "is_stale": self.is_fx_stale,
            "last_update_ms": self._fx_timestamp_ms or 0,
        }
