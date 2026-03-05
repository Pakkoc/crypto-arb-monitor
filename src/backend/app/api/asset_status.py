"""Asset status API — deposit/withdrawal status per exchange."""
from __future__ import annotations

import time
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/asset-status")
async def get_asset_status(
    request: Request,
    symbol: str | None = None,
):
    """Get deposit/withdrawal status for all exchanges.

    Optional query param `symbol` to filter by a specific coin (e.g., BTC).
    """
    service = getattr(request.app.state, "asset_status_service", None)
    if service is None:
        return {
            "status": "ok",
            "data": [],
            "timestamp_ms": int(time.time() * 1000),
        }

    if symbol:
        statuses = service.get_by_symbol(symbol.upper())
    else:
        statuses = service.get_all()

    data = [
        {
            "exchange": s.exchange,
            "symbol": s.symbol,
            "deposit_enabled": s.deposit_enabled,
            "withdraw_enabled": s.withdraw_enabled,
            "networks": [
                {
                    "network": n.network,
                    "deposit_enabled": n.deposit_enabled,
                    "withdraw_enabled": n.withdraw_enabled,
                    "min_withdraw": n.min_withdraw,
                    "withdraw_fee": n.withdraw_fee,
                    "confirmation_count": n.confirmation_count,
                }
                for n in s.networks
            ],
            "updated_at_ms": s.updated_at_ms,
        }
        for s in statuses
    ]

    return {
        "status": "ok",
        "data": data,
        "timestamp_ms": int(time.time() * 1000),
    }
