"""Gate.io lending API — margin lending availability."""
from __future__ import annotations

import time
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/gate-lending")
async def get_gate_lending(
    request: Request,
    currency: str | None = None,
):
    """Get Gate.io margin lending availability.

    Optional query param `currency` to filter by coin (e.g., BTC).
    """
    service = getattr(request.app.state, "gate_lending_service", None)
    if service is None:
        return {
            "status": "ok",
            "data": [],
            "timestamp_ms": int(time.time() * 1000),
        }

    if currency:
        item = service.get_by_currency(currency.upper())
        items = [item] if item else []
    else:
        items = service.get_all()

    data = [
        {
            "currency": i.currency,
            "amount": i.amount,
            "min_amount": i.min_amount,
            "rate": i.rate,
            "rate_day": i.rate_day,
            "leverage": i.leverage,
            "borrowable": i.borrowable,
        }
        for i in items
    ]

    return {
        "status": "ok",
        "data": data,
        "timestamp_ms": int(time.time() * 1000),
    }
