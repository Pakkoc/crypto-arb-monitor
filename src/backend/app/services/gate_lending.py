"""GateLendingService — polls Gate.io margin lending availability.

Two data sources:
1. Public (no auth): GET /api/v4/margin/uni/currency_pairs
   → Returns which currencies support margin lending + min borrow amounts
2. Authenticated (optional): GET /api/v4/margin/uni/borrowable
   → Returns actual borrowable amounts + interest rates

When no API keys are configured, only public data is used.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 60
_PAIRS_URL = "https://api.gateio.ws/api/v4/margin/uni/currency_pairs"
_BORROWABLE_URL = "https://api.gateio.ws/api/v4/margin/uni/borrowable"

# Only track lending info for symbols we care about
_TRACKED_SYMBOLS = {"BTC", "ETH", "XRP", "SOL", "DOGE", "USDT"}


@dataclass
class LendingInfo:
    """Lending availability for one currency on Gate.io."""
    currency: str
    amount: str          # borrowable amount (from authenticated API, "0" if no keys)
    min_amount: str      # min borrow amount (from public API)
    rate: str            # interest rate (from authenticated API, "0" if no keys)
    rate_day: str        # daily rate (from authenticated API, "0" if no keys)
    leverage: str = "0"  # max leverage (from public API)
    borrowable: bool = True  # whether this currency supports margin borrowing
    updated_at_ms: int = 0


class GateLendingService:
    """Periodically polls Gate.io margin lending availability."""

    def __init__(self) -> None:
        self._data: dict[str, LendingInfo] = {}
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._task = asyncio.create_task(self._poll_loop(), name="gate-lending-poller")
        logger.info("GateLendingService started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("GateLendingService stopped")

    def get_all(self) -> list[LendingInfo]:
        return list(self._data.values())

    def get_by_currency(self, currency: str) -> LendingInfo | None:
        return self._data.get(currency.upper())

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("GateLendingService poll error")
            await asyncio.sleep(_POLL_INTERVAL_S)

    async def _poll(self) -> None:
        assert self._client is not None
        now_ms = int(time.time() * 1000)

        # 1) Always fetch public currency pairs (no auth needed)
        resp = await self._client.get(_PAIRS_URL)
        items = resp.json()
        if not isinstance(items, list):
            logger.warning("[gate-lending] Unexpected currency_pairs response")
            return

        for item in items:
            pair = item.get("currency_pair", "")
            if "_USDT" not in pair:
                continue
            base = pair.replace("_USDT", "").upper()
            if base not in _TRACKED_SYMBOLS:
                continue
            self._data[base] = LendingInfo(
                currency=base,
                amount="0",
                min_amount=str(item.get("base_min_borrow_amount", "0")),
                rate="0",
                rate_day="0",
                leverage=str(item.get("leverage", "0")),
                borrowable=True,
                updated_at_ms=now_ms,
            )

        # 2) If API keys available, enrich with actual borrowable amounts + rates
        if settings.gate_api_key and settings.gate_api_secret:
            await self._poll_borrowable(now_ms)

    async def _poll_borrowable(self, now_ms: int) -> None:
        """Fetch actual borrowable amounts (requires authentication)."""
        assert self._client is not None
        headers = self._sign_request("GET", _BORROWABLE_URL)
        resp = await self._client.get(_BORROWABLE_URL, headers=headers)
        items = resp.json()
        if not isinstance(items, list):
            logger.warning("[gate-lending] Unexpected borrowable response: %s", items)
            return
        for item in items:
            currency = item.get("currency", "").upper()
            if currency not in _TRACKED_SYMBOLS:
                continue
            if currency in self._data:
                info = self._data[currency]
                info.amount = str(item.get("amount", "0"))
                info.rate = str(item.get("rate", "0"))
                info.rate_day = str(item.get("rate_day", "0"))
                info.updated_at_ms = now_ms

    def _sign_request(self, method: str, url: str, query: str = "", body: str = "") -> dict[str, str]:
        """Generate Gate.io v4 HMAC signature headers."""
        t = str(int(time.time()))
        hashed_body = hashlib.sha512(body.encode()).hexdigest()
        path = url.replace("https://api.gateio.ws", "")
        s = f"{method}\n{path}\n{query}\n{hashed_body}\n{t}"
        sign = hmac.new(
            settings.gate_api_secret.encode(), s.encode(), hashlib.sha512
        ).hexdigest()
        return {
            "KEY": settings.gate_api_key,
            "Timestamp": t,
            "SIGN": sign,
            "Content-Type": "application/json",
        }
