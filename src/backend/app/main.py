"""FastAPI application entry point.

Startup sequence (lifespan):
1. Initialize database (engine + session factory + create tables)
2. Seed tracked symbols and exchange reference data
3. Start ExchangeManager (5 WebSocket connectors as asyncio Tasks)
4. Start PriceStore consumer loop + periodic DB snapshots
5. Start SpreadCalculator (registers on PriceStore)
6. Start AlertEngine (registers on SpreadCalculator)
7. Start Telegram bot (if token configured)
8. Start WebSocket broadcaster (registers on PriceStore + SpreadCalculator)

Shutdown sequence (lifespan exit):
1. Stop PriceStore (consumer + snapshot tasks)
2. Stop ExchangeManager (cancel all connector tasks)
3. Stop Telegram bot
4. Dispose DB engine

Runnable with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    (from src/backend/ directory)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import close_engine, create_all_tables, init_db
from app.ws.handler import manager as ws_manager, ws_router

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


async def _seed_reference_data() -> None:
    """Seed the exchanges and tracked_symbols tables if empty."""
    from app.database import async_session_factory  # noqa: PLC0415
    if async_session_factory is None:
        return

    from sqlalchemy import select  # noqa: PLC0415
    from app.models.exchange import Exchange  # noqa: PLC0415
    from app.models.user import TrackedSymbol  # noqa: PLC0415
    from app.utils.enums import DEFAULT_SYMBOLS  # noqa: PLC0415

    try:
        async with async_session_factory() as session:
            async with session.begin():
                # Seed exchanges
                existing = await session.execute(select(Exchange))
                if not existing.scalars().first():
                    exchanges = [
                        Exchange(id="bithumb", name="Bithumb", currency="KRW",
                                 ws_url="wss://ws-api.bithumb.com/websocket/v1",
                                 rest_url="https://api.bithumb.com"),
                        Exchange(id="upbit", name="Upbit", currency="KRW",
                                 ws_url="wss://api.upbit.com/websocket/v1",
                                 rest_url="https://api.upbit.com"),
                        Exchange(id="binance", name="Binance", currency="USDT",
                                 ws_url="wss://stream.binance.com:9443/ws",
                                 rest_url="https://api.binance.com"),
                        Exchange(id="bybit", name="Bybit", currency="USDT",
                                 ws_url="wss://stream.bybit.com/v5/public/spot",
                                 rest_url="https://bybit-exchange.github.io"),
                        Exchange(id="gate", name="Gate.io", currency="USDT",
                                 ws_url="wss://api.gateio.ws/ws/v4/",
                                 rest_url="https://api.gateio.ws"),
                    ]
                    session.add_all(exchanges)
                    logger.info("Seeded %d exchanges", len(exchanges))

                # Seed tracked symbols
                existing_syms = await session.execute(select(TrackedSymbol))
                if not existing_syms.scalars().first():
                    import time  # noqa: PLC0415
                    now_epoch = int(time.time())
                    symbols = [
                        TrackedSymbol(symbol=sym, enabled=1, created_at=now_epoch, updated_at=now_epoch)
                        for sym in DEFAULT_SYMBOLS
                    ]
                    session.add_all(symbols)
                    logger.info("Seeded %d tracked symbols", len(symbols))
    except Exception:
        logger.exception("Failed to seed reference data")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """Application lifespan — startup and shutdown logic."""
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("Starting Crypto Arbitrage Monitor v1.0.0")

    # Ensure data directory exists
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    db_dir = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(db_dir, exist_ok=True)

    # 1. Initialize database
    init_db()
    await create_all_tables()
    logger.info("Database initialised: %s", settings.database_url)

    # 2. Seed reference data
    await _seed_reference_data()

    # 3. Start ExchangeManager
    from app.services.exchange_manager import ExchangeManager  # noqa: PLC0415
    exchange_manager = ExchangeManager()
    await exchange_manager.start()
    app.state.exchange_manager = exchange_manager

    # 4. Start PriceStore
    from app.services.price_store import PriceStore  # noqa: PLC0415
    price_store = PriceStore()
    price_store.start_consumer(exchange_manager.tick_queue)
    price_store.start_db_snapshots()
    app.state.price_store = price_store

    # 5. Start SpreadCalculator
    from app.services.spread_calculator import SpreadCalculator  # noqa: PLC0415
    spread_calculator = SpreadCalculator(price_store)
    spread_calculator.register()
    app.state.spread_calculator = spread_calculator

    # 6. Start AlertEngine
    from app.services.alert_engine import AlertEngine  # noqa: PLC0415
    alert_engine = AlertEngine()
    app.state.alert_engine = alert_engine

    # Wire spread → alert engine evaluation
    spread_calculator.on_spread(alert_engine.evaluate_many)

    # 7. Start Telegram bot (optional)
    from app.services.telegram_bot import TelegramBot  # noqa: PLC0415
    telegram_bot = TelegramBot(token=settings.telegram_bot_token)
    telegram_bot.set_exchange_manager(exchange_manager)
    await telegram_bot.start()
    app.state.telegram_bot = telegram_bot
    alert_engine.set_telegram_bot(telegram_bot)

    # 8. Wire WebSocket broadcaster
    app.state.ws_manager = ws_manager
    alert_engine.set_ws_manager(ws_manager)

    # Register WS broadcast callbacks on PriceStore and SpreadCalculator
    async def _on_price_for_ws(tick) -> None:
        if ws_manager.count() > 0:
            await ws_manager.broadcast_price_update(tick)

    async def _on_spread_for_ws(spreads) -> None:
        if ws_manager.count() > 0:
            await ws_manager.broadcast_spread_update(spreads)

    price_store.on_update(_on_price_for_ws)
    spread_calculator.on_spread(_on_spread_for_ws)

    # Also write spread records to DB periodically
    import asyncio  # noqa: PLC0415
    spread_db_task = asyncio.create_task(
        _spread_db_writer(spread_calculator, price_store), name="spread-db-writer"
    )

    # 9. Start AssetStatusService
    from app.services.asset_status import AssetStatusService  # noqa: PLC0415
    asset_status_service = AssetStatusService()
    await asset_status_service.start()
    app.state.asset_status_service = asset_status_service

    # 10. Start GateLendingService
    from app.services.gate_lending import GateLendingService  # noqa: PLC0415
    gate_lending_service = GateLendingService()
    await gate_lending_service.start()
    app.state.gate_lending_service = gate_lending_service

    logger.info("Startup complete — serving on %s:%d", settings.host, settings.port)

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("Shutting down…")
    spread_db_task.cancel()
    try:
        await spread_db_task
    except Exception:
        pass
    await gate_lending_service.stop()
    await asset_status_service.stop()
    await price_store.stop()
    await exchange_manager.stop()
    await telegram_bot.stop()
    await close_engine()
    logger.info("Shutdown complete")


async def _spread_db_writer(spread_calculator, price_store) -> None:
    """Periodically write computed spreads to the database.

    Win 4: Use cached spreads from get_latest() instead of recomputing all.
    Win 6: Use session.add_all() for bulk insert.
    """
    import asyncio  # noqa: PLC0415
    from app.utils.enums import DB_WRITE_INTERVAL_SECONDS  # noqa: PLC0415

    while True:
        try:
            await asyncio.sleep(DB_WRITE_INTERVAL_SECONDS)
            # Win 4: Reuse already-computed spreads from cache
            cached = spread_calculator.get_latest()
            spreads = list(cached.values())
            if not spreads:
                continue

            from app.database import async_session_factory  # noqa: PLC0415
            if async_session_factory is None:
                continue

            from app.models.spread import SpreadRecord  # noqa: PLC0415
            async with async_session_factory() as session:
                async with session.begin():
                    # Win 6: Bulk insert
                    records = [
                        SpreadRecord(
                            exchange_a=s.exchange_a,
                            exchange_b=s.exchange_b,
                            symbol=s.symbol,
                            spread_pct=str(s.spread_pct),
                            spread_type=s.spread_type,
                            price_a=str(s.price_a),
                            price_b=str(s.price_b),
                            is_stale=1 if s.is_stale else 0,
                            stale_reason=s.stale_reason,
                            fx_rate=str(s.fx_rate) if s.fx_rate else None,
                            fx_source=s.fx_source,
                            timestamp_ms=s.timestamp_ms,
                        )
                        for s in spreads
                    ]
                    session.add_all(records)
            logger.debug("Wrote %d spread records to DB", len(spreads))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Spread DB writer error")


app = FastAPI(
    title="Crypto Arbitrage Monitor API",
    version="1.0.0",
    description="Real-time cryptocurrency arbitrage monitor tracking kimchi premium across 5 exchanges.",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Allow the Vite dev server (port 5173) and production frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:4173",   # Vite preview
        "http://localhost:3000",   # Alternative dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(ws_router, prefix="/api/v1")
