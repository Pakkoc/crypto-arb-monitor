"""SpreadCalculator — computes spreads across all exchange pairs.

For each price tick, recomputes spreads for all pairs that involve the
updated exchange. Produces SpreadResult objects consumed by AlertEngine
and the WS broadcaster.

Spread formula (kimchi premium):
    spread_pct = (price_KRW / (price_USDT * fx_rate) - 1) * 100

Spread formula (same currency):
    spread_pct = (price_a / price_b - 1) * 100

Architecture reference: DD-2 (spread calculation engine).
"""
from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Coroutine, Any

from app.schemas.price import TickerUpdate
from app.schemas.spread import SpreadResult
from app.services.price_store import PriceStore
from app.utils.enums import (
    ALL_EXCHANGE_PAIRS,
    DEFAULT_SYMBOLS,
    EXCHANGE_CURRENCY,
    KIMCHI_PREMIUM_PAIRS,
    PRICE_STALE_THRESHOLD_MS,
)

logger = logging.getLogger(__name__)

_QUANTIZE = Decimal("0.01")


class SpreadCalculator:
    """Computes spreads between exchange pairs whenever a new price tick arrives.

    Registers itself as a callback on PriceStore so spreads are recomputed
    in real-time on each tick. Also provides compute_all() for snapshot endpoints.
    """

    def __init__(self, price_store: PriceStore) -> None:
        self._price_store = price_store
        self._latest_spreads: dict[tuple[str, str, str], SpreadResult] = {}
        self._on_spread_callbacks: list[
            Callable[[list[SpreadResult]], Coroutine[Any, Any, None]]
        ] = []

    def register(self) -> None:
        """Register this calculator as a callback on the price store."""
        self._price_store.on_update(self._on_tick)

    def on_spread(
        self,
        callback: Callable[[list[SpreadResult]], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a callback invoked when spreads are computed."""
        self._on_spread_callbacks.append(callback)

    async def _on_tick(self, tick: TickerUpdate) -> None:
        """Callback: recompute spreads for all pairs involving the updated exchange."""
        results = self.compute_affected_spreads(tick)
        if results:
            # Update cache
            for r in results:
                self._latest_spreads[(r.exchange_a, r.exchange_b, r.symbol)] = r
            # Fire callbacks sequentially — they share WS clients,
            # concurrent sends to the same connection cause protocol errors.
            for cb in self._on_spread_callbacks:
                try:
                    await cb(results)
                except Exception:
                    logger.exception("SpreadCalculator: callback error")

    def compute_affected_spreads(self, tick: TickerUpdate) -> list[SpreadResult]:
        """Recompute all spreads involving the exchange in the incoming tick.

        Returns a list of SpreadResult objects (one per affected pair per symbol).
        """
        results: list[SpreadResult] = []
        affected_pairs = [
            (a, b) for (a, b) in ALL_EXCHANGE_PAIRS
            if a == tick.exchange or b == tick.exchange
        ]
        for exchange_a, exchange_b in affected_pairs:
            spread = self._compute_pair(exchange_a, exchange_b, tick.symbol)
            if spread is not None:
                results.append(spread)
        return results

    def compute_all(self, symbol: str) -> list[SpreadResult]:
        """Recompute all 10 pair spreads for a given symbol. Used by the snapshot endpoint."""
        results: list[SpreadResult] = []
        for exchange_a, exchange_b in ALL_EXCHANGE_PAIRS:
            spread = self._compute_pair(exchange_a, exchange_b, symbol)
            if spread is not None:
                results.append(spread)
        return results

    def compute_all_symbols(self, symbols: list[str] | None = None) -> list[SpreadResult]:
        """Compute spreads for all symbols across all pairs."""
        target_symbols = symbols or list(DEFAULT_SYMBOLS)
        results: list[SpreadResult] = []
        for symbol in target_symbols:
            results.extend(self.compute_all(symbol))
        return results

    def get_latest(self) -> dict[tuple[str, str, str], SpreadResult]:
        """Return the latest cached spread results."""
        return dict(self._latest_spreads)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _compute_pair(
        self, exchange_a: str, exchange_b: str, symbol: str
    ) -> SpreadResult | None:
        """Compute the spread for a single (exchange_a, exchange_b, symbol) triple."""
        tick_a = self._price_store.get(exchange_a, symbol)
        tick_b = self._price_store.get(exchange_b, symbol)
        if tick_a is None or tick_b is None:
            return None  # Not enough data yet

        is_kimchi = (exchange_a, exchange_b) in KIMCHI_PREMIUM_PAIRS
        spread_type = "kimchi_premium" if is_kimchi else "same_currency"

        now_ms = int(time.time() * 1000)
        stale_a = (now_ms - tick_a.timestamp_ms) > PRICE_STALE_THRESHOLD_MS
        stale_b = (now_ms - tick_b.timestamp_ms) > PRICE_STALE_THRESHOLD_MS
        is_stale = stale_a or stale_b
        stale_reason: str | None = None
        if stale_a and stale_b:
            stale_reason = f"both {exchange_a} and {exchange_b} prices are stale"
        elif stale_a:
            stale_reason = f"{exchange_a} price is stale"
        elif stale_b:
            stale_reason = f"{exchange_b} price is stale"

        fx_rate: Decimal | None = None
        fx_source: str | None = None
        try:
            if is_kimchi:
                # KRW exchange (a) vs USDT exchange (b)
                fx_rate = self._price_store.fx_rate
                fx_source = self._price_store.fx_source
                if fx_rate is None or fx_rate == 0:
                    return None  # Cannot compute without FX rate
                # Check FX staleness
                if self._price_store.is_fx_stale:
                    is_stale = True
                    if stale_reason:
                        stale_reason += " and FX rate is stale"
                    else:
                        stale_reason = "FX rate is stale"
                # Convert KRW price to USDT equivalent, then compare
                price_a_usdt = tick_a.price / fx_rate
                if tick_b.price == 0:
                    return None
                spread_pct = (price_a_usdt / tick_b.price - 1) * 100
            else:
                # Same currency comparison
                if tick_b.price == 0:
                    return None
                spread_pct = (tick_a.price / tick_b.price - 1) * 100
        except (ZeroDivisionError, Exception):
            logger.exception(
                "Failed to compute spread for %s-%s %s", exchange_a, exchange_b, symbol
            )
            return None

        return SpreadResult(
            exchange_a=exchange_a,
            exchange_b=exchange_b,
            symbol=symbol,
            spread_pct=spread_pct.quantize(_QUANTIZE, rounding=ROUND_HALF_UP),
            spread_type=spread_type,
            timestamp_ms=now_ms,
            is_stale=is_stale,
            stale_reason=stale_reason,
            price_a=tick_a.price,
            price_b=tick_b.price,
            fx_rate=fx_rate,
            fx_source=fx_source,
        )
