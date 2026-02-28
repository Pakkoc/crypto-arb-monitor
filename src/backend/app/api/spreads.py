"""Spread endpoints.

- GET /api/v1/spreads         — Current spread matrix
- GET /api/v1/spreads/history — Historical spread data
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from app.utils.enums import DEFAULT_SYMBOLS, EXCHANGE_CURRENCY

router = APIRouter()


def _spread_to_entry(spread) -> dict:
    """Convert a SpreadResult dataclass to an API response entry."""
    return {
        "exchange_a": spread.exchange_a,
        "exchange_b": spread.exchange_b,
        "symbol": spread.symbol,
        "spread_pct": str(spread.spread_pct),
        "spread_type": spread.spread_type,
        "is_stale": spread.is_stale,
        "stale_reason": spread.stale_reason,
        "price_a": str(spread.price_a),
        "price_a_currency": EXCHANGE_CURRENCY.get(spread.exchange_a, "UNKNOWN"),
        "price_b": str(spread.price_b),
        "price_b_currency": EXCHANGE_CURRENCY.get(spread.exchange_b, "UNKNOWN"),
        "fx_rate": str(spread.fx_rate) if spread.fx_rate is not None else None,
        "fx_source": spread.fx_source,
        "timestamp_ms": spread.timestamp_ms,
    }


@router.get("/spreads")
async def get_spreads(
    request: Request,
    symbols: str | None = Query(default=None),
    spread_type: str | None = Query(default=None),
    include_stale: bool = Query(default=True),
) -> dict:
    """Return current spread matrix for all tracked symbols and exchange pairs.

    Response shape matches api-design.md §1.7.
    """
    now_ms = int(time.time() * 1000)

    if not hasattr(request.app.state, "spread_calculator"):
        return {
            "status": "ok",
            "data": {"spreads": [], "matrix_summary": None},
            "timestamp_ms": now_ms,
        }

    sc = request.app.state.spread_calculator

    # Determine which symbols to compute
    symbol_list = (
        [s.strip().upper() for s in symbols.split(",")]
        if symbols
        else list(DEFAULT_SYMBOLS)
    )

    all_spreads = sc.compute_all_symbols(symbol_list)

    # Apply filters
    entries = []
    for spread in all_spreads:
        if spread_type and spread.spread_type != spread_type:
            continue
        if not include_stale and spread.is_stale:
            continue
        entries.append(_spread_to_entry(spread))

    # Build matrix summary for first symbol
    matrix_summary = None
    if entries:
        primary_symbol = symbol_list[0] if symbol_list else "BTC"
        symbol_entries = [e for e in entries if e["symbol"] == primary_symbol]
        if symbol_entries:
            spreads_float = [(e, float(e["spread_pct"])) for e in symbol_entries]
            max_entry = max(spreads_float, key=lambda x: x[1])
            min_entry = min(spreads_float, key=lambda x: x[1])
            stale_count = sum(1 for e in symbol_entries if e["is_stale"])
            matrix_summary = {
                "symbol": primary_symbol,
                "max_spread": {
                    "pair": f"{max_entry[0]['exchange_a']}-{max_entry[0]['exchange_b']}",
                    "spread_pct": max_entry[0]["spread_pct"],
                    "type": max_entry[0]["spread_type"],
                },
                "min_spread": {
                    "pair": f"{min_entry[0]['exchange_a']}-{min_entry[0]['exchange_b']}",
                    "spread_pct": min_entry[0]["spread_pct"],
                    "type": min_entry[0]["spread_type"],
                },
                "stale_pairs": stale_count,
                "total_pairs": len(symbol_entries),
            }

    return {
        "status": "ok",
        "data": {"spreads": entries, "matrix_summary": matrix_summary},
        "timestamp_ms": now_ms,
    }


@router.get("/spreads/history")
async def get_spread_history(
    request: Request,
    symbol: str = Query(...),
    exchange_a: str | None = Query(default=None),
    exchange_b: str | None = Query(default=None),
    spread_type: str | None = Query(default=None),
    start_time: int | None = Query(default=None),
    end_time: int | None = Query(default=None),
    interval: str = Query(default="10s"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Return historical spread data with time-range filtering.

    Response shape matches api-design.md §1.7.
    Queries SQLite spread_records table.
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
        from app.models.spread import SpreadRecord  # noqa: PLC0415

        async with async_session_factory() as session:
            conditions = [
                SpreadRecord.symbol == symbol.upper(),
                SpreadRecord.created_at >= start_time_epoch,
                SpreadRecord.created_at <= end_time_epoch,
            ]
            if exchange_a:
                conditions.append(SpreadRecord.exchange_a == exchange_a.lower())
            if exchange_b:
                conditions.append(SpreadRecord.exchange_b == exchange_b.lower())
            if spread_type:
                conditions.append(SpreadRecord.spread_type == spread_type)

            # Count total
            count_stmt = select(func.count()).select_from(SpreadRecord).where(and_(*conditions))
            total_result = await session.execute(count_stmt)
            total = total_result.scalar() or 0

            # Fetch data
            data_stmt = (
                select(SpreadRecord)
                .where(and_(*conditions))
                .order_by(SpreadRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(data_stmt)
            rows = result.scalars().all()

            data = [
                {
                    "exchange_a": row.exchange_a,
                    "exchange_b": row.exchange_b,
                    "symbol": row.symbol,
                    "spread_pct": row.spread_pct,
                    "spread_type": row.spread_type,
                    "is_stale": bool(row.is_stale),
                    "fx_rate": row.fx_rate,
                    "fx_source": row.fx_source,
                    "timestamp_ms": row.timestamp_ms,
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
    except Exception:
        return {
            "status": "ok",
            "data": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False},
            "timestamp_ms": now_ms,
        }
