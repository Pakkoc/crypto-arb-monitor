"""AssetStatusService — polls deposit/withdrawal status from exchanges.

Polls every 60 seconds from public APIs (no auth needed):
- Bithumb: GET /public/assetsstatus/ALL
- Gate.io: GET /api/v4/wallet/currency_chains

Auth-required exchanges (Upbit, Binance, Bybit) are skipped when no API keys.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 60


@dataclass
class NetworkInfo:
    """Network/chain info for an asset on an exchange."""
    network: str
    deposit_enabled: bool
    withdraw_enabled: bool
    min_withdraw: str | None = None
    withdraw_fee: str | None = None
    confirmation_count: int | None = None


@dataclass
class AssetStatus:
    """Deposit/withdrawal status for a single asset on one exchange."""
    exchange: str
    symbol: str
    deposit_enabled: bool
    withdraw_enabled: bool
    networks: list[NetworkInfo] = field(default_factory=list)
    updated_at_ms: int = 0


class AssetStatusService:
    """Periodically polls exchange APIs for deposit/withdrawal status."""

    def __init__(self) -> None:
        self._statuses: dict[str, AssetStatus] = {}  # key: "exchange:symbol"
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=15.0)
        self._task = asyncio.create_task(self._poll_loop(), name="asset-status-poller")
        logger.info("AssetStatusService started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("AssetStatusService stopped")

    def get_all(self) -> list[AssetStatus]:
        return list(self._statuses.values())

    def get_by_symbol(self, symbol: str) -> list[AssetStatus]:
        return [s for s in self._statuses.values() if s.symbol == symbol]

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AssetStatusService poll error")
            await asyncio.sleep(_POLL_INTERVAL_S)

    async def _poll_all(self) -> None:
        tasks = [self._poll_bithumb(), self._poll_gate()]
        # Auth-required exchanges — skip if no keys
        if settings.upbit_access_key and settings.upbit_secret_key:
            tasks.append(self._poll_upbit())
        if settings.binance_api_key and settings.binance_api_secret:
            tasks.append(self._poll_binance())
        if settings.bybit_api_key and settings.bybit_api_secret:
            tasks.append(self._poll_bybit())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Exchange poll failed: %s", r)

    async def _poll_bithumb(self) -> None:
        """Bithumb public asset status — no auth needed."""
        assert self._client is not None
        resp = await self._client.get("https://api.bithumb.com/public/assetsstatus/ALL")
        data = resp.json()
        if data.get("status") != "0000":
            logger.warning("[bithumb] Asset status API error: %s", data.get("message"))
            return
        now_ms = int(time.time() * 1000)
        items = data.get("data", {})
        for sym, info in items.items():
            symbol = sym.upper()
            deposit = bool(info.get("deposit_status", 0))
            withdraw = bool(info.get("withdrawal_status", 0))
            # Bithumb public API doesn't provide per-network info,
            # but we can create a single "mainnet" entry from the overall status
            networks = [NetworkInfo(
                network=symbol,
                deposit_enabled=deposit,
                withdraw_enabled=withdraw,
            )]
            key = f"bithumb:{symbol}"
            self._statuses[key] = AssetStatus(
                exchange="bithumb",
                symbol=symbol,
                deposit_enabled=deposit,
                withdraw_enabled=withdraw,
                networks=networks,
                updated_at_ms=now_ms,
            )

    async def _poll_gate(self) -> None:
        """Gate.io public currency info + chain details — no auth needed.

        Uses /api/v4/spot/currencies which includes per-chain info in `chains` array.
        """
        assert self._client is not None
        resp = await self._client.get("https://api.gateio.ws/api/v4/spot/currencies")
        items = resp.json()
        if not isinstance(items, list):
            logger.warning("[gate] Unexpected currency response type")
            return
        now_ms = int(time.time() * 1000)
        for item in items:
            symbol = item.get("currency", "").upper()
            if not symbol:
                continue
            deposit = not item.get("deposit_disabled", True)
            withdraw = not item.get("withdraw_disabled", True)
            # Extract per-chain network info from the `chains` array
            networks: list[NetworkInfo] = []
            for ch in item.get("chains", []):
                networks.append(NetworkInfo(
                    network=ch.get("name", symbol),
                    deposit_enabled=not ch.get("deposit_disabled", True),
                    withdraw_enabled=not ch.get("withdraw_disabled", True),
                ))
            key = f"gate:{symbol}"
            self._statuses[key] = AssetStatus(
                exchange="gate",
                symbol=symbol,
                deposit_enabled=deposit,
                withdraw_enabled=withdraw,
                networks=networks,
                updated_at_ms=now_ms,
            )

    async def _poll_upbit(self) -> None:
        """Upbit wallet status — requires JWT auth."""
        # TODO: Implement when API keys are available
        pass

    async def _poll_binance(self) -> None:
        """Binance capital config — requires HMAC auth."""
        # TODO: Implement when API keys are available
        pass

    async def _poll_bybit(self) -> None:
        """Bybit asset info — requires HMAC auth."""
        # TODO: Implement when API keys are available
        pass
