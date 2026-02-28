"""GET /api/v1/exchanges — Exchange connection status."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/exchanges")
async def get_exchanges(request: Request) -> dict:
    """Return current connection status for all 5 exchanges.

    Response shape matches api-design.md §1.5.
    Reads live connector state from ExchangeManager.
    """
    now_ms = int(time.time() * 1000)

    if not hasattr(request.app.state, "exchange_manager"):
        return {"status": "ok", "data": [], "timestamp_ms": now_ms}

    em = request.app.state.exchange_manager
    states = em.get_connector_states()

    data = []
    for ex_id, info in states.items():
        entry = {
            "id": info.get("id", ex_id),
            "name": info.get("name", ex_id),
            "currency": info.get("currency", "UNKNOWN"),
            "state": info.get("state", "DISCONNECTED"),
            "ws_url": info.get("ws_url", ""),
            "last_message_ms": info.get("last_message_ms"),
            "latency_ms": info.get("latency_ms"),
            "reconnect_count": info.get("reconnect_count", 0),
            "connected_since_ms": info.get("connected_since_ms"),
            "is_stale": info.get("is_stale", True),
            "stale_threshold_ms": info.get("stale_threshold_ms", 5000),
            "supported_symbols": info.get("supported_symbols", []),
        }
        # Add fallback_mode for Coinone
        if "fallback_mode" in info:
            entry["fallback_mode"] = info["fallback_mode"]
        data.append(entry)

    return {"status": "ok", "data": data, "timestamp_ms": now_ms}
