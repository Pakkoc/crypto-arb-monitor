# Tech Decision Matrix — Crypto Arbitrage Monitor

**Date:** 2026-02-27
**For:** Human review at Step 3 (tech stack selection)
**Full analysis:** `research/tech-stack-analysis.md`

---

## 1. Backend Framework

| Framework | Language | WebSocket Concurrency | Crypto Ecosystem | Async Native | Complexity | Recommended |
|-----------|----------|----------------------|-----------------|-------------|------------|-------------|
| **FastAPI + asyncio** | Python 3.12 | ✅ 45k+ concurrent WS documented | ✅ ccxt, cryptofeed, aiogram all Python-first | ✅ Yes — asyncio throughout | Low | **YES** |
| Django Channels | Python | ✅ Production-proven | ✅ Good | Partial (sync ORM requires wrappers) | High (channel layers, routing config) | No |
| aiohttp (as server) | Python | ✅ Good | ✅ Good | ✅ Yes | Medium (no auto-docs, verbose) | No (use as WS client only) |
| NestJS | TypeScript | ✅ Good | ⚠️ No mature Python ccxt equivalent in JS | ✅ Event loop | Medium-High | No |
| Fastify | TypeScript | ✅ 70k req/s | ⚠️ Same JS ecosystem gap | ✅ Event loop | Low-Medium | No |
| Go + Gin/Fiber | Go | ✅ Best raw perf (goroutines, 300k req/s) | ❌ No ccxt/cryptofeed/aiogram in Go | ✅ Goroutines | High (no ORM maturity, exchange libs) | No |

**Decision driver:** Python ecosystem for crypto tooling (ccxt, cryptofeed, aiogram) is decisive.

---

## 2. Frontend Framework

| Framework | Bundle Size | Real-time Update Perf | TradingView Chart Support | Ecosystem Size | Recommended |
|-----------|-------------|----------------------|--------------------------|----------------|-------------|
| **React 19 + Vite** | 156 KB runtime | ✅ Auto-batching in v19 | ✅ Official React tutorial + wrapper | ✅ Largest (110k job posts) | **YES** |
| Vue 3 + Vite | ~89 KB | ✅ Granular reactivity (Pinia) | ⚠️ No official wrapper, manual canvas | Medium | No |
| Svelte 5 / SvelteKit | 47 KB runtime | ✅ Best (compiled, no vDOM) | ⚠️ Community-maintained wrapper | Smallest (900 job posts) | No |

**Decision driver:** TradingView Lightweight Charts has official React tutorial; Svelte's perf advantage is undetectable at 5 Hz with ≤10 users.

---

## 3. Database

| Database | Setup | Time-Series Fit | Relational (alert config) | Migration Path | Recommended |
|----------|-------|----------------|--------------------------|----------------|-------------|
| **SQLite WAL** | ✅ Zero (stdlib) | ✅ Good for ≤500 rows/min | ✅ Full SQL | TimescaleDB via SQLAlchemy | **YES** |
| PostgreSQL + TimescaleDB | Requires server | ✅ Excellent (hypertable, continuous aggregates) | ✅ Full SQL | N/A (is the target) | No (migration target) |
| InfluxDB | Requires server | ✅ Best ingestion throughput | ❌ Needs second DB for relational | Complex (different query language) | No |
| Redis | Requires server | ❌ Not persistent by default | ❌ Not relational | N/A | No (optional for WS broadcast scaling) |

**Decision driver:** Zero-setup (no Docker required) and single-file backup are decisive for a portfolio project. SQLAlchemy async ORM makes migration to PostgreSQL a connection string change.

---

## 4. Telegram Bot Library

| Library | Async Native | FastAPI Integration | Bot API Version | Community | Recommended |
|---------|-------------|--------------------|-----------------|-----------| ------------|
| **aiogram 3.25** | ✅ asyncio-first | ✅ Runs in same event loop via lifespan | 9.2 (latest) | Medium | **YES** |
| python-telegram-bot 21 | Partial (v20+ rebuilt on asyncio) | ⚠️ `run_polling()` needs bridging | Current | Large | Second choice |
| pyTelegramBotAPI (telebot) 4 | ❌ Sync by default | ❌ Requires `run_in_executor` | Current | Medium | No |

**Decision driver:** aiogram integrates into FastAPI's asyncio event loop without bridging; eliminates thread-pool overhead.

---

## 5. Exchange WebSocket Client Library

| Library | All 5 Exchanges | Normalization | Control | License | Recommended |
|---------|----------------|--------------|---------|---------|-------------|
| **websockets 14.x (direct)** | ✅ Manual (5 connectors) | Manual (per-exchange in connector) | ✅ Full | BSD | **YES** |
| cryptofeed 3.x | ⚠️ 4/5 (Coinone NOT supported) | ✅ Automatic FeedHandler | Partial | BSD | No (Coinone gap) |
| ccxt 4.4.x (incl. WS in 2024) | ✅ All 5 | ✅ watch_ticker() normalized | Partial | MIT/LGPL (verify) | Secondary option — verify license |

**Decision driver:** Coinone is missing from cryptofeed; manual connectors give full control over the reconnection and normalization logic documented in Step 1 research.

---

## 6. KRW/USD Exchange Rate Source

| Source | Cost | Update Frequency | Reliability | API Key Required | Recommended |
|--------|------|-----------------|-------------|-----------------|-------------|
| **Upbit KRW-USDT WS** (primary) | Free | Sub-second (from existing connection) | ✅ High (part of live feed) | No | **YES (primary)** |
| **ExchangeRate-API** (fallback) | Free tier | Hourly (with free key) | ✅ High | Free registration | **YES (fallback)** |
| Fixer.io | Paid for useful frequency | 60s (paid), daily (free) | ✅ High | Yes (free tier: 100 req/month) | No (free tier too limited) |
| Open Exchange Rates | Free tier limited | Hourly (paid) | ✅ High | Yes | No (paid required) |

**Decision driver:** Upbit KRW-USDT is already connected; zero extra cost or latency. ExchangeRate-API provides a clean fallback if Upbit feed degrades.

---

## 7. Chart Libraries (Frontend)

| Library | Use Case | Real-Time Perf | Framework | License | Recommended |
|---------|---------|---------------|-----------|---------|-------------|
| **TradingView Lightweight Charts 5** | OHLCV price charts | ✅ Handles thousands of ticks/sec | React (official wrapper) | Apache 2.0 | **YES (primary)** |
| **Recharts 2** | Spread trend lines, % charts | ✅ Good for <1000 points | React (native) | MIT | **YES (secondary)** |
| Apache ECharts + echarts-for-react | Any chart type | ✅ GPU/WebGL for millions of points | React wrapper | Apache 2.0 | Optional (overkill) |
| Chart.js + react-chartjs-2 | General | ⚠️ SVG-based, slower for real-time | React wrapper | MIT | No |

---

## 8. Summary: Final Recommended Stack

```
Backend:    FastAPI 0.115 + asyncio + Uvicorn 0.32 (Python 3.12)
WS Client:  websockets 14.x (per-exchange asyncio Tasks)
HTTP Client: httpx 0.27.x
ORM:        SQLAlchemy 2.x async + aiosqlite 0.20
DB:         SQLite 3.47 (WAL mode)
Migrations: Alembic 1.14
Telegram:   aiogram 3.25
KRW/USD:    Upbit KRW-USDT WebSocket (primary) + ExchangeRate-API (fallback)

Frontend:   React 19 + Vite 6 + TypeScript 5
State:      Zustand 5
Charts:     TradingView Lightweight Charts 5 (OHLCV) + Recharts 2 (spreads)
Data fetch: TanStack Query (React Query) 5
Styling:    Tailwind CSS 4
```

---

## 9. Open Questions for Step 3 Human Review

1. **ccxt WebSocket**: Should ccxt 4.4 watch methods be used for the 4 supported exchanges (Bithumb, Upbit, Binance, Bybit), with a custom connector only for Coinone? Or should all 5 connectors be manual for consistency?

2. **Redis**: Include Redis in initial architecture for WebSocket broadcast (enabling multi-worker scaling), or defer until needed? Adds Docker dependency but simplifies future scaling.

3. **TimescaleDB**: Should the architecture target TimescaleDB from day one (with Docker) to avoid a migration later, or start with SQLite and migrate if scale is needed?

4. **Polling mode for Coinone**: Step 1 research found Coinone WebSocket support is available but less documented. Should the architecture include a polling fallback for Coinone if WebSocket proves unreliable?

5. **Alert notification format**: In addition to Telegram, should the system support browser push notifications or email alerts? (Affects backend notification service design.)
