"""GET /api/v1/health — Server health check with exchange and DB summary."""
from __future__ import annotations

import os
import platform
import time

from fastapi import APIRouter, Request

from app.utils.enums import DEFAULT_SYMBOLS

router = APIRouter()

# Capture server start time at module load
_SERVER_STARTED_AT_MS: int = int(time.time() * 1000)
_SERVER_STARTED_AT_ISO: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@router.get("/health")
async def get_health(request: Request) -> dict:
    """Return server health, exchange connection summary, DB stats, and FX rate info.

    Response shape matches api-design.md §1.4.
    """
    now_ms = int(time.time() * 1000)
    uptime_seconds = int((now_ms - _SERVER_STARTED_AT_MS) / 1000)

    # Exchange status from ExchangeManager
    exchange_summary: dict[str, str] = {}
    connected_count = 0
    disconnected_count = 5
    if hasattr(request.app.state, "exchange_manager"):
        em = request.app.state.exchange_manager
        states = em.get_connector_states()
        exchange_summary = {ex_id: info["state"] for ex_id, info in states.items()}
        connected_count = em.get_connected_count()
        disconnected_count = em.get_disconnected_count()

    # FX rate from PriceStore
    fx_info = {"rate": "0", "source": "none", "is_stale": True, "last_update_ms": 0}
    if hasattr(request.app.state, "price_store"):
        fx_info = request.app.state.price_store.get_fx_info()

    # Database stats
    db_status = "ok"
    db_size_mb = 0.0
    wal_size_mb = 0.0
    try:
        from app.config import settings  # noqa: PLC0415
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        db_path = os.path.abspath(db_path)
        if os.path.exists(db_path):
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 1)
        wal_path = db_path + "-wal"
        if os.path.exists(wal_path):
            wal_size_mb = round(os.path.getsize(wal_path) / (1024 * 1024), 1)
    except Exception:
        db_status = "error"

    # Active alerts count
    active_alerts = 0
    try:
        from app.database import async_session_factory  # noqa: PLC0415
        if async_session_factory is not None:
            from sqlalchemy import func, select  # noqa: PLC0415
            from app.models.alert import AlertConfig  # noqa: PLC0415
            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count()).select_from(AlertConfig).where(AlertConfig.enabled == 1)
                )
                active_alerts = result.scalar() or 0
    except Exception:
        pass

    # Dashboard clients count
    dashboard_clients = 0
    if hasattr(request.app.state, "ws_manager"):
        dashboard_clients = request.app.state.ws_manager.count()

    return {
        "status": "ok",
        "data": {
            "server": {
                "uptime_seconds": uptime_seconds,
                "version": "1.0.0",
                "python_version": platform.python_version(),
                "started_at": _SERVER_STARTED_AT_ISO,
            },
            "exchanges": {
                "total": 5,
                "connected": connected_count,
                "disconnected": disconnected_count,
                "summary": exchange_summary,
            },
            "database": {
                "status": db_status,
                "size_mb": db_size_mb,
                "wal_size_mb": wal_size_mb,
            },
            "fx_rate": fx_info,
            "tracked_symbols": list(DEFAULT_SYMBOLS),
            "active_alerts": active_alerts,
            "dashboard_clients": dashboard_clients,
        },
        "timestamp_ms": now_ms,
    }
