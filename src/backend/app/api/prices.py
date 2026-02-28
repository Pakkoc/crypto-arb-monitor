"""Price endpoints.

- GET /api/v1/prices          — Latest prices across all exchanges
- GET /api/v1/prices/{symbol} — Latest prices for one symbol
- GET /api/v1/prices/history  — Historical price snapshots
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from app.utils.enums import DEFAULT_SYMBOLS, EXCHANGE_CURRENCY, PRICE_STALE_THRESHOLD_MS

router = APIRouter()


def _tick_to_entry(tick, now_ms: int) -> dict:
    """Convert a TickerUpdate dataclass to an API response entry."""
    is_stale = (now_ms - tick.timestamp_ms) > PRICE_STALE_THRESHOLD_MS
    return {
        "exchange": tick.exchange,
        "symbol": tick.symbol,
        "price": str(tick.price),
        "currency": tick.currency,
        "bid_price": str(tick.bid_price) if tick.bid_price is not None else None,
        "ask_price": str(tick.ask_price) if tick.ask_price is not None else None,
        "volume_24h": str(tick.volume_24h),
        "timestamp_ms": tick.timestamp_ms,
        "received_at_ms": tick.received_at_ms,
        "is_stale": is_stale,
    }


@router.get("/prices")
async def get_prices(
    request: Request,
    symbols: str | None = Query(default=None, description="Comma-separated symbol filter"),
    exchanges: str | None = Query(default=None, description="Comma-separated exchange filter"),
) -> dict:
    """Return latest prices across all exchanges for all (or filtered) symbols.

    Response shape matches api-design.md §1.6.
    """
    now_ms = int(time.time() * 1000)
    fx_info = {"rate": "0", "source": "none", "is_stale": True, "last_update_ms": 0}

    if not hasattr(request.app.state, "price_store"):
        return {
            "status": "ok",
            "data": {"prices": [], "fx_rate": fx_info},
            "timestamp_ms": now_ms,
        }

    ps = request.app.state.price_store
    fx_info = ps.get_fx_info()

    # Parse filters
    symbol_filter = set(s.strip().upper() for s in symbols.split(",")) if symbols else None
    exchange_filter = set(e.strip().lower() for e in exchanges.split(",")) if exchanges else None

    # Collect prices
    all_prices = ps.get_all()
    entries = []
    for (ex_id, sym), tick in all_prices.items():
        if symbol_filter and sym not in symbol_filter:
            continue
        if exchange_filter and ex_id not in exchange_filter:
            continue
        entries.append(_tick_to_entry(tick, now_ms))

    # Sort by exchange, then symbol
    entries.sort(key=lambda e: (e["exchange"], e["symbol"]))

    return {
        "status": "ok",
        "data": {"prices": entries, "fx_rate": fx_info},
        "timestamp_ms": now_ms,
    }


@router.get("/prices/history")
async def get_price_history(
    request: Request,
    symbol: str = Query(..., description="Symbol to query"),
    exchange: str | None = Query(default=None),
    start_time: int | None = Query(default=None),
    end_time: int | None = Query(default=None),
    interval: str = Query(default="10s"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return historical price snapshots with time-range filtering.

    Response shape matches api-design.md §1.6.
    Queries SQLite price_snapshots table.
    """
    now_ms = int(time.time() * 1000)

    from app.database import async_session_factory  # noqa: PLC0415
    if async_session_factory is None:
        return {
            "status": "ok",
            "data": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False},
            "timestamp_ms": now_ms,
        }

    # Default time range: last 24 hours
    if end_time is None:
        end_time_epoch = int(time.time())
    else:
        end_time_epoch = end_time // 1000 if end_time > 1e12 else end_time

    if start_time is None:
        start_time_epoch = end_time_epoch - 86400
    else:
        start_time_epoch = start_time // 1000 if start_time > 1e12 else start_time

    try:
        from sqlalchemy import func, select, and_  # noqa: PLC0415
        from app.models.price import PriceSnapshot  # noqa: PLC0415

        async with async_session_factory() as session:
            # Build base query
            conditions = [
                PriceSnapshot.symbol == symbol.upper(),
                PriceSnapshot.created_at >= start_time_epoch,
                PriceSnapshot.created_at <= end_time_epoch,
            ]
            if exchange:
                exchange_list = [e.strip().lower() for e in exchange.split(",")]
                conditions.append(PriceSnapshot.exchange_id.in_(exchange_list))

            # Count total
            count_stmt = select(func.count()).select_from(PriceSnapshot).where(and_(*conditions))
            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            # Fetch data with pagination
            data_stmt = (
                select(PriceSnapshot)
                .where(and_(*conditions))
                .order_by(PriceSnapshot.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(data_stmt)
            rows = result.scalars().all()

            data = [
                {
                    "exchange": row.exchange_id,
                    "symbol": row.symbol,
                    "price": row.price,
                    "currency": row.currency,
                    "volume_24h": row.volume_24h,
                    "timestamp_ms": row.exchange_timestamp_ms,
                    "created_at": datetime.fromtimestamp(row.created_at, tz=timezone.utc).isoformat(),
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
    except Exception as exc:
        return {
            "status": "ok",
            "data": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False},
            "timestamp_ms": now_ms,
        }


@router.get("/prices/{symbol}")
async def get_prices_by_symbol(
    request: Request,
    symbol: str,
    exchanges: str | None = Query(default=None),
) -> dict:
    """Return latest prices for a specific symbol across all exchanges.

    Response shape matches api-design.md §1.6.
    """
    symbol = symbol.upper()
    now_ms = int(time.time() * 1000)
    fx_info = {"rate": "0", "source": "none", "is_stale": True, "last_update_ms": 0}

    if symbol not in DEFAULT_SYMBOLS:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Symbol {symbol!r} is not tracked"},
        )

    if not hasattr(request.app.state, "price_store"):
        return {
            "status": "ok",
            "data": {"prices": [], "fx_rate": fx_info},
            "timestamp_ms": now_ms,
        }

    ps = request.app.state.price_store
    fx_info = ps.get_fx_info()

    exchange_filter = set(e.strip().lower() for e in exchanges.split(",")) if exchanges else None

    by_symbol = ps.get_by_symbol(symbol)
    entries = []
    for ex_id, tick in by_symbol.items():
        if exchange_filter and ex_id not in exchange_filter:
            continue
        entries.append(_tick_to_entry(tick, now_ms))

    entries.sort(key=lambda e: e["exchange"])

    return {
        "status": "ok",
        "data": {"prices": entries, "fx_rate": fx_info},
        "timestamp_ms": now_ms,
    }
