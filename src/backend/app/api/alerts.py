"""Alert CRUD endpoints + alert history + symbols + FX rate + preferences.

Endpoints:
- GET    /api/v1/alerts            — List alert configs
- POST   /api/v1/alerts            — Create alert config
- GET    /api/v1/alerts/history    — Alert trigger history
- GET    /api/v1/alerts/{id}       — Get single alert config
- PUT    /api/v1/alerts/{id}       — Update alert config
- DELETE /api/v1/alerts/{id}       — Delete alert config
- GET    /api/v1/symbols           — List tracked symbols
- PUT    /api/v1/symbols           — Update tracked symbol list
- GET    /api/v1/fx-rate           — Current KRW/USD rate
- GET    /api/v1/preferences       — Get user preferences
- PUT    /api/v1/preferences       — Update user preferences
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, func, select, update, delete

from app import database
from app.models.alert import AlertConfig, AlertHistory
from app.models.user import TrackedSymbol, UserPreference
from app.schemas.alert import AlertConfigCreate, AlertConfigUpdate
from app.utils.enums import DEFAULT_SYMBOLS, FX_RATE_STALE_THRESHOLD_MS

router = APIRouter()


def _epoch_to_iso(epoch: int | None) -> str | None:
    """Convert a Unix epoch timestamp to ISO 8601 string."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _config_to_dict(row: AlertConfig) -> dict:
    """Convert an AlertConfig ORM object to an API response dict."""
    return {
        "id": row.id,
        "chat_id": row.chat_id,
        "symbol": row.symbol,
        "exchange_a": row.exchange_a,
        "exchange_b": row.exchange_b,
        "threshold_pct": row.threshold_pct,
        "direction": row.direction,
        "cooldown_minutes": row.cooldown_minutes,
        "enabled": bool(row.enabled),
        "created_at": _epoch_to_iso(row.created_at),
        "updated_at": _epoch_to_iso(row.updated_at),
        "last_triggered_at": _epoch_to_iso(row.last_triggered_at),
        "trigger_count": row.trigger_count,
    }


# ── Alert Configuration CRUD ───────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    request: Request,
    enabled: bool | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all alert configurations with optional filters."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        return {
            "status": "ok",
            "data": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False},
            "timestamp_ms": now_ms,
        }

    async with database.async_session_factory() as session:
        conditions = []
        if enabled is not None:
            conditions.append(AlertConfig.enabled == (1 if enabled else 0))
        if symbol:
            conditions.append(AlertConfig.symbol == symbol.upper())

        # Count total
        count_stmt = select(func.count()).select_from(AlertConfig)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Fetch data
        data_stmt = select(AlertConfig).order_by(AlertConfig.id)
        if conditions:
            data_stmt = data_stmt.where(and_(*conditions))
        data_stmt = data_stmt.limit(limit).offset(offset)
        result = await session.execute(data_stmt)
        rows = result.scalars().all()

    return {
        "status": "ok",
        "data": [_config_to_dict(row) for row in rows],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        },
        "timestamp_ms": now_ms,
    }


@router.post("/alerts", status_code=201)
async def create_alert(request: Request, body: AlertConfigCreate) -> dict:
    """Create a new alert configuration."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    now_epoch = int(time.time())
    async with database.async_session_factory() as session:
        async with session.begin():
            config = AlertConfig(
                chat_id=body.chat_id,
                symbol=body.symbol.upper() if body.symbol else None,
                exchange_a=body.exchange_a,
                exchange_b=body.exchange_b,
                threshold_pct=f"{body.threshold_pct:.2f}",
                direction=body.direction,
                cooldown_minutes=body.cooldown_minutes,
                enabled=1 if body.enabled else 0,
                trigger_count=0,
                created_at=now_epoch,
                updated_at=now_epoch,
            )
            session.add(config)
            await session.flush()
            result = _config_to_dict(config)

    # Invalidate alert engine cache if available
    if hasattr(request.app.state, "alert_engine"):
        request.app.state.alert_engine.invalidate_config_cache()

    return {"status": "ok", "data": result, "timestamp_ms": now_ms}


@router.get("/alerts/history")
async def get_alert_history(
    alert_config_id: int | None = Query(default=None),
    symbol: str | None = Query(default=None),
    delivered: bool | None = Query(default=None),
    start_time: int | None = Query(default=None),
    end_time: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return alert trigger history log."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        return {
            "status": "ok",
            "data": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False},
            "timestamp_ms": now_ms,
        }

    # Default time range: last 24 hours
    if end_time is None:
        end_epoch = int(time.time())
    else:
        end_epoch = end_time // 1000 if end_time > 1e12 else end_time
    if start_time is None:
        start_epoch = end_epoch - 86400
    else:
        start_epoch = start_time // 1000 if start_time > 1e12 else start_time

    async with database.async_session_factory() as session:
        conditions = [
            AlertHistory.created_at >= start_epoch,
            AlertHistory.created_at <= end_epoch,
        ]
        if alert_config_id is not None:
            conditions.append(AlertHistory.alert_config_id == alert_config_id)
        if symbol:
            conditions.append(AlertHistory.symbol == symbol.upper())
        if delivered is not None:
            conditions.append(AlertHistory.telegram_delivered == (1 if delivered else 0))

        count_stmt = select(func.count()).select_from(AlertHistory).where(and_(*conditions))
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        data_stmt = (
            select(AlertHistory)
            .where(and_(*conditions))
            .order_by(AlertHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(data_stmt)
        rows = result.scalars().all()

    data = [
        {
            "id": row.id,
            "alert_config_id": row.alert_config_id,
            "exchange_a": row.exchange_a,
            "exchange_b": row.exchange_b,
            "symbol": row.symbol,
            "spread_pct": row.spread_pct,
            "spread_type": row.spread_type,
            "threshold_pct": row.threshold_pct,
            "direction": row.direction,
            "price_a": row.price_a,
            "price_b": row.price_b,
            "fx_rate": row.fx_rate,
            "fx_source": row.fx_source,
            "message_text": row.message_text,
            "telegram_delivered": bool(row.telegram_delivered),
            "telegram_message_id": row.telegram_message_id,
            "created_at": _epoch_to_iso(row.created_at),
        }
        for row in rows
    ]

    return {
        "status": "ok",
        "data": data,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        },
        "timestamp_ms": now_ms,
    }


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int) -> dict:
    """Get a single alert configuration by ID."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    async with database.async_session_factory() as session:
        result = await session.execute(
            select(AlertConfig).where(AlertConfig.id == alert_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": f"Alert {alert_id} not found"},
            )

    return {"status": "ok", "data": _config_to_dict(row), "timestamp_ms": now_ms}


@router.put("/alerts/{alert_id}")
async def update_alert(request: Request, alert_id: int, body: AlertConfigUpdate) -> dict:
    """Update an existing alert configuration (partial update)."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    async with database.async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(AlertConfig).where(AlertConfig.id == alert_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "NOT_FOUND", "message": f"Alert {alert_id} not found"},
                )

            # Apply updates
            update_data = body.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if value is None and field in ("symbol", "exchange_a", "exchange_b"):
                    setattr(row, field, None)
                elif field == "threshold_pct" and value is not None:
                    row.threshold_pct = f"{value:.2f}"
                elif field == "enabled" and value is not None:
                    row.enabled = 1 if value else 0
                elif field == "symbol" and value is not None:
                    row.symbol = value.upper()
                elif value is not None:
                    setattr(row, field, value)

            row.updated_at = int(time.time())
            await session.flush()
            result_dict = _config_to_dict(row)

    if hasattr(request.app.state, "alert_engine"):
        request.app.state.alert_engine.invalidate_config_cache()

    return {"status": "ok", "data": result_dict, "timestamp_ms": now_ms}


@router.delete("/alerts/{alert_id}")
async def delete_alert(request: Request, alert_id: int) -> dict:
    """Delete an alert configuration."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    async with database.async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(AlertConfig).where(AlertConfig.id == alert_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "NOT_FOUND", "message": f"Alert {alert_id} not found"},
                )
            await session.delete(row)

    if hasattr(request.app.state, "alert_engine"):
        request.app.state.alert_engine.invalidate_config_cache()

    return {
        "status": "ok",
        "data": {"deleted_id": alert_id, "message": "Alert configuration deleted"},
        "timestamp_ms": now_ms,
    }


# ── Tracked Symbols ────────────────────────────────────────────────────────────

@router.get("/symbols")
async def list_symbols(request: Request) -> dict:
    """List all tracked symbols and their exchange coverage."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        return {"status": "ok", "data": [], "timestamp_ms": now_ms}

    async with database.async_session_factory() as session:
        result = await session.execute(
            select(TrackedSymbol).order_by(TrackedSymbol.symbol)
        )
        rows = result.scalars().all()

    # Build exchange coverage (all exchanges support all symbols by default)
    all_exchanges = ["bithumb", "upbit", "binance", "bybit", "gate"]
    data = [
        {
            "symbol": row.symbol,
            "enabled": bool(row.enabled),
            "exchange_coverage": {ex: True for ex in all_exchanges},
            "created_at": _epoch_to_iso(row.created_at),
        }
        for row in rows
    ]

    return {"status": "ok", "data": data, "timestamp_ms": now_ms}


@router.put("/symbols")
async def update_symbols(request: Request, body: dict) -> dict:
    """Replace the tracked symbols list."""
    now_ms = int(time.time() * 1000)
    symbols = body.get("symbols", [])

    if not symbols or len(symbols) > 20:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "1 to 20 symbols required"},
        )

    if database.async_session_factory is None:
        raise HTTPException(status_code=503, detail="Database not available")

    now_epoch = int(time.time())
    async with database.async_session_factory() as session:
        async with session.begin():
            # Get current symbols
            result = await session.execute(select(TrackedSymbol))
            current = {row.symbol for row in result.scalars().all()}
            new_set = {s.upper() for s in symbols}

            added = new_set - current
            removed = current - new_set

            # Add new symbols
            for sym in added:
                session.add(TrackedSymbol(
                    symbol=sym, enabled=1, created_at=now_epoch, updated_at=now_epoch
                ))

            # Disable removed symbols
            if removed:
                await session.execute(
                    update(TrackedSymbol)
                    .where(TrackedSymbol.symbol.in_(removed))
                    .values(enabled=0, updated_at=now_epoch)
                )

    return {
        "status": "ok",
        "data": {
            "symbols": sorted(new_set),
            "added": sorted(added),
            "removed": sorted(removed),
            "message": "Tracked symbols updated. Exchange subscriptions will refresh within 5 seconds.",
        },
        "timestamp_ms": now_ms,
    }


# ── FX Rate ────────────────────────────────────────────────────────────────────

@router.get("/fx-rate")
async def get_fx_rate(request: Request) -> dict:
    """Return current KRW/USD exchange rate and source information."""
    now_ms = int(time.time() * 1000)

    if not hasattr(request.app.state, "price_store"):
        return {
            "status": "ok",
            "data": {
                "rate": "0", "source": "none", "is_stale": True,
                "last_update_ms": 0, "staleness_threshold_ms": FX_RATE_STALE_THRESHOLD_MS,
                "age_ms": 0, "fallback_available": False,
                "fallback_rate": None, "fallback_source": None, "fallback_last_update_ms": None,
            },
            "timestamp_ms": now_ms,
        }

    ps = request.app.state.price_store
    fx_ts = ps.fx_timestamp_ms or 0
    age_ms = now_ms - fx_ts if fx_ts else 0

    return {
        "status": "ok",
        "data": {
            "rate": str(ps.fx_rate) if ps.fx_rate else "0",
            "source": ps.fx_source or "none",
            "is_stale": ps.is_fx_stale,
            "last_update_ms": fx_ts,
            "staleness_threshold_ms": FX_RATE_STALE_THRESHOLD_MS,
            "age_ms": age_ms,
            "fallback_available": False,
            "fallback_rate": None,
            "fallback_source": None,
            "fallback_last_update_ms": None,
        },
        "timestamp_ms": now_ms,
    }


# ── User Preferences ───────────────────────────────────────────────────────────

_DEFAULT_PREFERENCES = {
    "dashboard": {
        "default_symbol": "BTC",
        "visible_exchanges": ["bithumb", "upbit", "binance", "bybit", "gate"],
        "spread_matrix_mode": "percentage",
        "chart_interval": "5m",
        "theme": "dark",
    },
    "notifications": {
        "telegram_enabled": True,
        "telegram_chat_id": None,
        "sound_enabled": True,
    },
    "timezone": "Asia/Seoul",
    "locale": "ko-KR",
}


@router.get("/preferences")
async def get_preferences() -> dict:
    """Get current dashboard user preferences (single-user system)."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        return {"status": "ok", "data": _DEFAULT_PREFERENCES, "timestamp_ms": now_ms}

    try:
        async with database.async_session_factory() as session:
            result = await session.execute(
                select(UserPreference).where(UserPreference.id == 1)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                prefs = json.loads(row.preferences_json)
                return {"status": "ok", "data": prefs, "timestamp_ms": now_ms}
    except Exception:
        pass

    return {"status": "ok", "data": _DEFAULT_PREFERENCES, "timestamp_ms": now_ms}


@router.put("/preferences")
async def update_preferences(request: Request, body: dict) -> dict:
    """Update user preferences (partial update via deep merge)."""
    now_ms = int(time.time() * 1000)

    if database.async_session_factory is None:
        return {"status": "ok", "data": _DEFAULT_PREFERENCES, "timestamp_ms": now_ms}

    try:
        import copy
        now_epoch = int(time.time())
        result_data: dict | None = None

        async with database.async_session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(UserPreference).where(UserPreference.id == 1)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    # Deep merge body into defaults (not shallow)
                    merged = copy.deepcopy(_DEFAULT_PREFERENCES)
                    _deep_merge(merged, body)
                    session.add(UserPreference(
                        id=1,
                        preferences_json=json.dumps(merged),
                        updated_at=now_epoch,
                    ))
                    result_data = merged
                else:
                    # Merge into existing
                    current = json.loads(row.preferences_json)
                    _deep_merge(current, body)
                    row.preferences_json = json.dumps(current)
                    row.updated_at = now_epoch
                    result_data = current
            # session.begin() __aexit__ commits here before return

        # Invalidate AlertEngine config cache so telegram_enabled/chat_id changes take effect
        if hasattr(request.app.state, "alert_engine"):
            request.app.state.alert_engine.invalidate_config_cache()

        return {"status": "ok", "data": result_data, "timestamp_ms": now_ms}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("[preferences] Failed to update: %s", exc)
        return {"status": "ok", "data": _DEFAULT_PREFERENCES, "timestamp_ms": now_ms}


def _deep_merge(base: dict, overlay: dict) -> None:
    """Recursively merge overlay into base dict."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
