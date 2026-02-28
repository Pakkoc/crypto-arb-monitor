# Tech Stack Analysis — Crypto Arbitrage Monitor

**Research Date:** 2026-02-27
**Scope:** Backend framework, frontend framework, database, Telegram bot, KRW/USD exchange rate API, and existing project analysis for a real-time 5-exchange cryptocurrency arbitrage monitor
**Purpose:** Step 2 output — foundation for tech stack selection (Step 3) and system architecture design (Step 4)

---

## Executive Summary

This system monitors 5 exchanges simultaneously via WebSocket (Bithumb, Upbit, Coinone, Binance, Bybit), calculates spreads with KRW/USD conversion, and delivers Telegram alerts with a PC web dashboard.

**Recommended Stack:**

| Layer | Recommendation | Rationale |
|-------|---------------|-----------|
| Backend | **FastAPI + asyncio** (Python 3.12) | Native asyncio fits the 5-concurrent-WebSocket use case; Python ecosystem dominates crypto tooling (ccxt, cryptofeed); single language for all backend logic |
| Frontend | **React + Vite** | Broadest chart ecosystem (TradingView Lightweight Charts); largest talent pool and library ecosystem; Vite gives fast iteration without Next.js SSR overhead |
| Time-series DB | **SQLite + WAL mode** (with optional TimescaleDB migration path) | Zero-setup for single-user portfolio project; WAL mode handles concurrent writes; TimescaleDB if scale is needed |
| Alert config DB | **SQLite** (same file, different tables) | Relational, embedded, zero-ops; perfect for user settings CRUD |
| Telegram | **aiogram 3.x** | Native asyncio; no thread-pool overhead; integrates into FastAPI event loop without friction |
| KRW/USD rate | **ExchangeRate-API (free tier)** with Upbit USD fallback | Reliable, no key required for open-access endpoint, hourly updates sufficient for spread normalization |
| Exchange WS client | **websockets 14.x** (direct, per-exchange) | More control than ccxt for multi-exchange normalization; ccxt.pro available as paid upgrade if standardization outweighs control |

**Key principle:** Python async throughout the backend eliminates thread-pool complexity. All 5 exchange WebSocket clients, the spread engine, the alert engine, and the REST API server run in the same asyncio event loop — no cross-process messaging required.

---

## 1. Backend Framework

### 1.1 Evaluation Criteria

For this system, backend framework selection is dominated by three constraints:

1. **Concurrency model**: Must sustain 5+ long-lived outbound WebSocket connections (exchange clients) + N inbound WebSocket connections (dashboard clients) simultaneously, at sub-second latency.
2. **Ecosystem fit**: Exchange API client libraries (ccxt, cryptofeed), Telegram bot libraries, and data processing libraries (pydantic, pandas) are overwhelmingly Python-first. Using Node.js or Go sacrifices this ecosystem.
3. **Development velocity**: Portfolio project; maintainability and debuggability matter more than raw throughput at this scale.

### 1.2 Python Options

#### Option A: FastAPI + asyncio + Uvicorn

**Version (2025-2026):** FastAPI 0.115.x, Uvicorn 0.32.x (with uvloop 0.21.x on Linux/macOS)

**Architecture fit:**
FastAPI is an ASGI framework built on Starlette. Both outbound WebSocket clients (connecting *to* exchanges) and inbound WebSocket servers (serving the dashboard) can coexist in the same asyncio event loop. Each exchange connector runs as an asyncio Task; the spread engine runs as another Task; the REST API and WebSocket server are served by Uvicorn. No threads, no multiprocessing, no IPC.

**WebSocket handling:**
- Inbound (dashboard): Native `WebSocket` support via Starlette's ASGI layer. Documented benchmark: 45,000+ concurrent WebSocket connections on a single DigitalOcean droplet. For broadcast scenarios (price updates to all dashboard clients), the pattern is asyncio queues per client with a shared publisher.
- Outbound (exchange connectors): Uses the `websockets` library (or `aiohttp` WebSocket client) directly as asyncio Tasks running inside the same event loop.
- Demonstrated performance: 250,000 WebSocket messages/second with Redis Pub/Sub backing in production deployments. For this project (5 exchanges, 1-10 dashboard users), in-memory broadcast is sufficient — no Redis required.

**Pros:**
- Automatic OpenAPI/Swagger docs generation (useful for Step 5 API design)
- Pydantic v2 for request/response validation with sub-millisecond overhead
- Native async: no `asyncio.run_in_executor` needed for exchange connectors
- Huge Python ecosystem: `ccxt` (4,000+ stars), `cryptofeed` (40+ exchange WebSocket normalization), `pandas`, `pydantic`
- Active community: ~80,000 GitHub stars (fastest-growing Python web framework)
- Type hints throughout = IDE support + runtime validation

**Cons:**
- Python GIL limits true parallelism for CPU-bound computation; not a concern here since spread calculation is arithmetic, not CPU-intensive
- Slightly higher memory footprint than Go for the same connection count
- Cold start slower than compiled languages (not relevant for long-running service)

**Verdict:** Best fit. The async-native architecture and Python ecosystem alignment make this the clear choice.

---

#### Option B: Django Channels

**Version (2025-2026):** Django 5.x + Channels 4.x

**Architecture fit:**
Django Channels extends Django's HTTP/2 model with WebSocket support via ASGI. Uses a channel layer (Redis-backed or in-memory) to route messages between consumers.

**Pros:**
- Django ORM is mature and well-documented for relational data
- Channel layers provide built-in pub/sub without custom code
- Battle-tested in production for millions of concurrent connections at enterprise scale

**Cons:**
- Heavyweight for this use case: Django ORM, admin, auth, session middleware are unnecessary complexity
- Channel layer architecture (even in-memory) adds indirection vs. direct asyncio queues
- Configuration complexity: `CHANNEL_LAYERS` config, consumer routing, ASGI application composition
- Slower startup and higher baseline memory than FastAPI
- Django's synchronous-first ORM requires explicit `database_sync_to_async` wrappers even with Channels
- More boilerplate per endpoint

**Verdict:** Eliminated. Overengineered for a single-developer portfolio project. The channel layer abstraction adds complexity without commensurate benefit at this scale.

---

#### Option C: aiohttp (as framework)

**Version (2025-2026):** aiohttp 3.11.x

**Architecture fit:**
aiohttp is simultaneously an HTTP client and server library. It predates FastAPI and was the de-facto asyncio HTTP library before FastAPI's rise.

**Pros:**
- Extremely mature WebSocket client implementation — often faster than `websockets` library for outbound connections (cited benchmark: aiohttp WebSocket client outperforms `websockets` in throughput)
- Single dependency for both HTTP server and WebSocket client
- Low-level control over connection pooling

**Cons:**
- No automatic API documentation (no Pydantic integration, no OpenAPI)
- More verbose request/response handling vs. FastAPI decorators
- Smaller ecosystem compared to FastAPI for modern Python development
- Less type-safety by default
- Community momentum has shifted toward FastAPI; fewer 2025 tutorials

**Verdict:** Useful as a WebSocket *client* library within a FastAPI app (for outbound exchange connections). Not recommended as the primary server framework.

**Hybrid note:** The optimal architecture uses FastAPI as the server framework and `aiohttp.ClientSession` (or the `websockets` library) for outbound exchange WebSocket connections. Both coexist in the same event loop.

---

### 1.3 Node.js Options

#### Option D: NestJS

**Version (2025-2026):** NestJS 10.x + `@nestjs/websockets` + Socket.IO or ws adapter

**Architecture fit:**
NestJS is an opinionated Node.js framework with Angular-inspired module system. WebSocket support is a first-class feature via `@WebSocketGateway` decorators.

**Pros:**
- TypeScript throughout; full type safety
- Built-in WebSocket gateway with Socket.IO fallback for older browsers
- Dependency injection makes large codebases testable
- Strong ecosystem for enterprise backend patterns

**Cons:**
- No `ccxt` parity: Node.js ccxt works, but Python ccxt has more mature async support and more stars. Critical difference: Bithumb and Coinone have no official Node.js SDK; Python libraries are the community standard.
- Node.js single-threaded event loop is excellent for I/O but has the same CPU-bound limitation as Python; for 5 exchange WebSocket connections there is no meaningful difference
- TypeScript adds compile step; two-language stack if any data analysis tools (pandas, numpy) are needed
- Over-architected module system for a portfolio project

**Verdict:** Eliminated. Python ecosystem dominance in crypto tooling (ccxt, cryptofeed, python-telegram-bot/aiogram, pandas for spread data analysis) is a decisive advantage. Using Node.js would require reimplementing or wrapping exchange-specific libraries that already exist in Python.

---

#### Option E: Fastify

**Version (2025-2026):** Fastify 5.x + `@fastify/websocket`

**Pros:**
- Fastest Node.js HTTP framework in benchmarks (70,000+ req/s vs Express's 45,000)
- JSON schema validation built-in
- Lightweight and extensible

**Cons:**
- Same ecosystem gap as NestJS for crypto-specific Python libraries
- WebSocket support via plugin, not core — less integrated than NestJS
- Minimal structure; requires more architectural decisions vs. NestJS

**Verdict:** Eliminated for the same Python ecosystem reasons as NestJS. Fastify would be compelling for a pure API service, but not for a crypto monitor where Python libraries are decisive.

---

### 1.4 Go Options

#### Option F: Go + Gin/Fiber

**Version (2025-2026):** Go 1.23, Gin 1.10.x / Fiber 3.x

**Architecture fit:**
Go's goroutines handle concurrent WebSocket connections with minimal memory footprint (~4KB per goroutine vs Python asyncio Task's overhead). Go is used in production HFT systems for sub-millisecond latency.

**Pros:**
- Best raw performance: Fiber handles 300,000+ req/s in benchmarks; goroutine concurrency model is excellent for 5 WebSocket connections
- Compiled binary: instant cold start, minimal memory
- Native goroutine per connection pattern is simple and robust
- Strong WebSocket library: `gorilla/websocket` (19,000 GitHub stars)

**Cons:**
- Critical: No mature ccxt equivalent in Go. `go-ccxt` forks exist but are incomplete and unmaintained. Exchange-specific WebSocket normalization must be implemented from scratch.
- No aiogram equivalent in Go; Telegram bot libraries (`telebot`, `telegram-bot-api`) are less mature than Python counterparts
- Go is not the right language for a portfolio project targeting a Python-dominated domain
- Verbose error handling and no generics-based ORM as mature as SQLAlchemy

**Verdict:** Eliminated. Performance advantage is real but irrelevant at this scale (5 exchange connections). The missing ecosystem (no ccxt, no cryptofeed, no aiogram) creates substantial implementation risk.

---

### 1.5 Backend Recommendation

**FastAPI + asyncio + Uvicorn (Python 3.12)**

Rationale:
1. Python's asyncio model handles 5 concurrent outbound WebSocket connections and N inbound connections without threads or processes
2. Python is the lingua franca of crypto tooling: ccxt (200+ exchanges), cryptofeed (40+ exchange WebSocket normalization), aiogram, pandas are all Python-first
3. FastAPI's Pydantic v2 integration means request/response types are defined once and shared with API documentation
4. Documented production performance is orders of magnitude above this project's requirements

---

## 2. Frontend Framework

### 2.1 Evaluation Criteria

1. **Real-time data handling**: How efficiently does the framework update when WebSocket messages arrive at 1-5Hz per exchange?
2. **Chart/graph library availability**: Financial price charts, spread trend lines, multi-exchange comparison views
3. **Developer experience**: State management for live data, TypeScript support, build tooling
4. **Bundle size**: Affects dashboard load time

### 2.2 Option A: React + Vite (TypeScript)

**Version (2025-2026):** React 19.x, Vite 6.x, TypeScript 5.x

**Real-time data handling:**
React's reconciler batches state updates. React 19 introduces automatic batching for all updates (including those inside async callbacks and WebSocket event handlers), which is ideal for high-frequency price updates. The pattern is: WebSocket message → `useState` setter → batched re-render. For 5 exchanges at 1-2 ticks/second, React handles this trivially without memoization.

**Chart libraries available:**
- **TradingView Lightweight Charts 5.x** (Apache 2.0): Purpose-built for financial data. Handles thousands of bars and real-time tick updates multiple times per second. Native candlestick, line, histogram. 12,000+ GitHub stars. React wrapper available.
- **Recharts 2.x**: D3-based, React component API. Good for spread trend lines and non-OHLCV charts.
- **Apache ECharts 5.x + echarts-for-react**: GPU-accelerated Canvas/WebGL, handles millions of data points. Overkill for this project but excellent if price history grows large.
- **Victory, Nivo**: Alternative React chart libraries, well-maintained

**Pros:**
- Largest ecosystem: `react-query` (TanStack Query) for REST data fetching, `zustand` or `jotai` for lightweight state management (better than Redux for this use case), `react-router-dom` for routing
- Best chart library support: TradingView Lightweight Charts has explicit React tutorial and React wrapper
- 52% of frontend job postings (Stack Overflow 2024); largest talent pool
- TypeScript integration is mature and well-documented
- Vite provides sub-100ms HMR for fast development iteration
- No SSR overhead (dashboard is not SEO-sensitive; Vite SPA is appropriate)

**Cons:**
- Virtual DOM adds runtime overhead vs. Svelte's compiled approach (React bundle: 156KB vs Svelte's 47KB)
- `useEffect` + WebSocket setup requires careful cleanup (not unique to React; just needs discipline)
- No built-in state management — requires choosing zustand/jotai/redux (this is a pro for flexibility, but a con for beginners)

**Verdict:** Recommended. The chart library ecosystem (especially TradingView Lightweight Charts) and the React 19 automatic batching for WebSocket updates make this the strongest choice for the dashboard use case.

---

### 2.3 Option B: Vue 3 + Vite (TypeScript)

**Version (2025-2026):** Vue 3.5.x, Vite 6.x, Pinia 3.x (state management)

**Real-time data handling:**
Vue 3's Composition API with `ref()` and reactive stores (Pinia) is well-suited for live data. Pinia stores can be updated directly from WebSocket event handlers. The reactivity system is granular — only components consuming a changed `ref` re-render.

**Chart libraries available:**
- `vue-chartjs` (Chart.js wrapper for Vue): maintained, but Chart.js is SVG-based and slower for high-frequency updates vs. Canvas
- `vue-echarts` (ECharts wrapper): excellent performance
- TradingView Lightweight Charts: no official Vue wrapper; requires manual integration with `onMounted`/`onUnmounted` lifecycle hooks — adds boilerplate

**Pros:**
- Composition API feels natural for real-time data (reactive stores, computed properties)
- Smaller bundle than React out of the box
- Pinia is officially endorsed by Vue team; excellent TypeScript support
- Good documentation

**Cons:**
- Smaller job market than React (about half the postings)
- TradingView Lightweight Charts lacks an official Vue wrapper — manual canvas management required
- `vue-chartjs` lags behind in performance for real-time financial data compared to React + Lightweight Charts
- Fewer total npm packages in the Vue ecosystem vs. React

**Verdict:** Viable but not recommended. The lack of an official TradingView Lightweight Charts Vue wrapper is a meaningful friction point for a financial dashboard. React's chart ecosystem is the decisive differentiator.

---

### 2.4 Option C: Svelte 5 / SvelteKit

**Version (2025-2026):** Svelte 5.x (Runes API), SvelteKit 2.x

**Real-time data handling:**
Svelte 5's Runes API (`$state`, `$derived`) compiles reactivity away — no virtual DOM, no reconciler overhead. WebSocket messages update `$state` directly, triggering precise DOM mutations. For high-frequency price updates, Svelte is theoretically the most efficient approach.

**Benchmarks:**
- Bundle size: Svelte 5 runtime 47KB vs React 19's 156KB
- Initial render: Svelte 5 renders 60% faster than React 19 in benchmarks
- Real-time dashboard benchmark (5,000 row table + WebSocket + charts): Svelte outperforms React by ~30% on frame time

**Chart libraries available:**
- `svelte-lightweight-charts` (community wrapper for TradingView Lightweight Charts): exists but community-maintained, not official
- `layerchart`: Svelte-native chart library with D3 integration, v1.0 released 2024
- Chart.js via `svelte-chartjs`: works but same SVG performance limitation

**Pros:**
- Best raw rendering performance for high-frequency DOM updates
- Smallest bundle size
- SvelteKit's native WebSocket support landed in 2024 (via Node.js adapter hooks)
- Stores system integrates naturally with WebSocket data streams
- Genuinely elegant reactive syntax — less boilerplate than React hooks

**Cons:**
- Svelte has ~900 job postings vs React's 110,000 (Stack Overflow 2024) — smallest community
- TradingView Lightweight Charts Vue/Svelte wrappers are community-maintained; React wrapper is officially documented
- Smaller npm ecosystem — fewer pre-built UI component libraries for admin/dashboard UIs
- SvelteKit WebSocket support is newer and less battle-tested than React + Vite solutions
- Performance advantage is real but undetectable for 5-exchange data at human-visible refresh rates

**Verdict:** Not recommended for a portfolio project. Performance advantage is real but irrelevant at 5 Hz update frequency with 1-10 users. The smaller ecosystem and community-maintained chart wrappers create avoidable risk.

---

### 2.5 Frontend Recommendation

**React 19 + Vite 6 + TypeScript + TradingView Lightweight Charts**

State management: **Zustand 5.x** (lightweight, no boilerplate, works directly in WebSocket callbacks)
Chart library: **TradingView Lightweight Charts 5.x** (primary) + **Recharts 2.x** (spread history)

---

## 3. Database

### 3.1 Requirements Analysis

This system has two distinct storage categories:

| Category | Access Pattern | Volume | Characteristics |
|----------|---------------|--------|----------------|
| Price snapshots / spread records | Write: 5 exchanges × N ticks/sec; Read: historical queries for charts | ~500 rows/min at 1Hz per exchange | Time-series; append-only writes; time-range queries |
| Alert configurations / user settings | Read/write on user action | ~10-100 rows | Relational; low volume; CRUD |

### 3.2 Option A: SQLite (WAL mode)

**Version:** SQLite 3.47.x (bundled with Python via `sqlite3` stdlib)

**Time-series fit:**
SQLite in WAL (Write-Ahead Logging) mode supports concurrent readers while a single writer appends rows. For 5 exchanges at 1Hz each (300 rows/min), SQLite's WAL mode easily handles the write rate.

**Benchmark reference:** SQLite officially documents "appropriate use" for applications with write throughput under ~100,000 writes/day per file — this project generates at most ~432,000 rows/day at 1Hz across 5 exchanges, which approaches but does not exceed the limit. With a 5-minute candle aggregation table (common in crypto systems), actual row count is 5 × 288 candles/day = 1,440 rows/day — trivially within limits.

**Pros:**
- Zero setup: file-based, no server process, no connection strings beyond a file path
- `sqlite3` is Python's standard library — no additional dependencies for basic use
- `aiosqlite` provides async SQLite access without blocking the event loop
- Single file: easy to back up, version, or transfer
- Excellent Python ecosystem: SQLAlchemy 2.x async supports SQLite; `alembic` for migrations
- Full SQL support including window functions (useful for spread moving averages)

**Cons:**
- No native time-series compression or continuous aggregates (unlike TimescaleDB)
- Write lock is per-database file (WAL mode mitigates this but doesn't eliminate it)
- Not suitable if this project ever scales to a multi-process deployment
- No built-in data retention policies (must implement manual cleanup)

**Verdict:** Recommended for this project scope. The simplicity advantage is decisive for a portfolio project.

---

### 3.3 Option B: PostgreSQL + TimescaleDB

**Version (2025-2026):** PostgreSQL 17.x + TimescaleDB 2.17.x

**Time-series fit:**
TimescaleDB's `hypertable` feature automatically partitions time-series data by time intervals. Continuous aggregates pre-compute OHLCV candles. Compression reduces storage by 90%+ for historical price data.

**Benchmark comparison (ClickHouse vs TimescaleDB vs InfluxDB, 2025):**
TimescaleDB significantly outperforms InfluxDB for complex queries (seconds vs tens of seconds difference). For write-heavy ingestion, InfluxDB is faster; TimescaleDB has better complex query performance.

**Pros:**
- Full SQL + time-series extensions: `time_bucket()`, continuous aggregates, compression
- Production-proven for cryptocurrency exchanges (used at actual trading platforms for tick capture)
- Scales horizontally if needed
- `asyncpg` provides high-performance async PostgreSQL client

**Cons:**
- Requires a running PostgreSQL server: Docker or native installation
- Significant operational overhead for a single-user portfolio project
- TimescaleDB extension requires PostgreSQL — adds dependency chain
- SQLAlchemy + TimescaleDB requires Timescale-specific query constructs that bypass ORM

**Verdict:** Migration target if project scales. Not recommended for initial development. Architecture should use the SQLAlchemy ORM layer so switching from SQLite to PostgreSQL/TimescaleDB requires only a connection string change and a schema migration.

---

### 3.4 Option C: InfluxDB

**Version (2025-2026):** InfluxDB 3.x (Cloud-Native, OSS)

**Time-series fit:**
InfluxDB is purpose-built for time-series metrics. Write throughput is best-in-class. Flux query language is powerful for time-series transformations.

**Pros:**
- Highest write throughput for append-only time-series data
- Built-in data retention policies (TTL per bucket)
- Native compression for numeric time-series
- Native Grafana integration for dashboards (if using Grafana instead of custom frontend)

**Cons:**
- Line Protocol write syntax is non-standard; requires the `influxdb-client-python` library
- No relational tables for alert configurations — requires a second database (PostgreSQL or SQLite) for user settings
- Flux query language has a steep learning curve and is being deprecated in favor of InfluxQL in v3
- Over-engineered for 5-exchange monitoring
- InfluxDB v3 moved to cloud-native architecture; OSS version has reduced features

**Verdict:** Eliminated. The requirement for a second database for relational data (alert configs) makes InfluxDB an awkward fit. SQLite handles both time-series and relational data in one file.

---

### 3.5 Option D: Redis

**Role:** Caching / Pub/Sub, not primary storage

Redis is not a primary database for this project, but has a specific role: if the backend ever scales to multiple FastAPI workers, Redis Pub/Sub provides the broadcast channel for WebSocket price updates across workers. For a single-worker deployment (the expected case for this portfolio project), in-memory asyncio queues are sufficient and Redis is unnecessary overhead.

**Verdict:** Optional infrastructure. Include in architecture as a future scaling path, but do not require it for initial deployment.

---

### 3.6 Database Recommendation

**SQLite 3.47+ in WAL mode** with SQLAlchemy 2.x async + aiosqlite

- **Schema**: Single SQLite file with separate tables for `price_snapshots`, `spread_records`, `alert_configs`, `alert_history`, `exchanges`, `trading_pairs`
- **Migration strategy**: Alembic for schema migrations
- **Migration path**: SQLAlchemy ORM + asyncio dialect means switching to PostgreSQL/TimescaleDB requires only a connection string change

---

## 4. Telegram Bot Integration

### 4.1 Library Comparison

#### Option A: aiogram 3.x

**Version (2025-2026):** aiogram 3.25.x (supports Telegram Bot API 9.2)

**Architecture fit:**
aiogram is built on asyncio and aiohttp from the ground up. The dispatcher (`Dispatcher`) and bot (`Bot`) instances integrate naturally with FastAPI's asyncio event loop. Alert triggers from the spread engine can call `bot.send_message()` directly as an `await` expression.

**Polling vs Webhook:**
- Polling: `await dp.start_polling(bot)` — starts long-polling in the same event loop as FastAPI. Simple but adds one more network connection.
- Webhook: `await dp.feed_update(bot, update)` called from a FastAPI POST endpoint that Telegram calls. Requires a public HTTPS URL — not practical for local development without a tunnel (ngrok).

**Pros:**
- Fully async: no `asyncio.run_in_executor` wrapper needed
- Lower latency under load (non-blocking, unlike python-telegram-bot's sync approach pre-v20)
- Active maintenance: Telegram Bot API 9.2 supported within days of release
- Finite State Machine (FSM) support for multi-step bot conversations (/settings flow)
- Middleware system for logging, error handling

**Cons:**
- Steeper learning curve: assumes asyncio familiarity
- Smaller community than python-telegram-bot for tutorials

---

#### Option B: python-telegram-bot 21.x

**Version (2025-2026):** python-telegram-bot 21.x

**Architecture fit:**
python-telegram-bot was synchronous through v13; v20+ fully rebuilt on asyncio. v21 adds support for Telegram Bot API features through 2024.

**Pros:**
- Larger community; more Stack Overflow answers and tutorials
- High-level `Application` class handles polling lifecycle automatically
- Supports both polling and webhook equally well

**Cons:**
- asyncio integration is less seamless than aiogram — `Application.run_polling()` blocks in a separate thread context, requiring `asyncio.ensure_future()` to bridge with FastAPI's event loop
- Slightly higher overhead for simple fire-and-forget alert delivery

---

#### Option C: pyTelegramBotAPI (telebot) 4.x

**Version (2025-2026):** pyTelegramBotAPI 4.x

**Architecture fit:**
telebot is synchronous by default; `asyncio_helper` module provides async support, but it's not the core design.

**Pros:**
- Simplest API: `bot.send_message(chat_id, text)` with no async ceremony
- Fastest to prototype

**Cons:**
- Synchronous calls block the event loop unless wrapped with `asyncio.run_in_executor`
- Not recommended for production async applications

**Verdict:** Eliminated for async FastAPI integration.

---

### 4.2 Polling vs Webhook Decision

| Approach | Best For | Drawback |
|----------|---------|----------|
| Long Polling | Development; no public URL required | One extra persistent HTTP connection to Telegram |
| Webhook | Production with public HTTPS server | Requires domain + SSL certificate; not practical for local dev |

**Recommendation:** Long polling for this project. The system runs on a developer's PC (or a simple VPS without a domain). Polling adds ~one HTTP/2 long-poll connection, which is negligible alongside 5 exchange WebSocket connections.

### 4.3 Telegram Recommendation

**aiogram 3.25.x** with long polling integrated into FastAPI's asyncio lifespan

Integration pattern:
```python
# FastAPI lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(dp.start_polling(bot))  # runs alongside FastAPI
    yield
    await bot.session.close()
```

---

## 5. KRW/USD Exchange Rate

### 5.1 Requirement Analysis

The kimchi premium calculation requires a live KRW/USD rate:

```
kimchi_premium_pct = ((krw_price / krw_usd_rate) - usdt_price) / usdt_price × 100
```

Update frequency required: Exchange WebSocket ticks arrive every 1-5 seconds. The exchange rate moves slowly (USD/KRW changes by ~0.1% per day). Updating once per minute is sufficient for accurate premium calculation.

### 5.2 Option A: ExchangeRate-API (Open Access)

**URL:** `https://open.er-api.com/v6/latest/USD`

**Pricing:** Free, no API key required for open access endpoint
**Update frequency:** Daily (sufficient for KRW/USD)
**Reliability:** Documented SLA: "dead simple and extremely reliable"
**Rate limit:** Once per 24 hours for open access; hourly with free registered key

**Pros:**
- No API key required for basic usage
- KRW supported
- Simple JSON response: `{ "rates": { "KRW": 1370.5, ... } }`

**Cons:**
- Open access updates once per 24 hours
- With free registered key: once per hour

**Verdict:** Primary source. With a free registered key, hourly updates are more than sufficient.

---

### 5.3 Option B: Fixer.io

**Pricing:** Free plan available; 100 requests/month on free tier (severely limited)
**Update frequency:** Every 60 seconds on paid plans; once daily on free

**Cons:**
- Free tier: only 100 requests/month — far too restrictive for a monitoring service
- Requires paid plan for useful update frequency

**Verdict:** Eliminated due to free tier restrictions.

---

### 5.4 Option C: Upbit USDT/KRW Real-Time Rate

Upbit lists a `KRW-USDT` pair (Tether, pegged to USD). The real-time spot price provides a market-derived KRW/USD rate with sub-second updates — already available from the Upbit WebSocket connection this system establishes anyway.

**Pros:**
- No additional API call required
- Sub-second update frequency
- Reflects the actual trading rate used by market participants in Korea
- Free

**Cons:**
- USDT ≠ USD exactly (Tether occasionally depegs); introduces small premium/discount
- Depends on Upbit's liquidity for USDT pairs

**Verdict:** Recommended as the primary rate source during active monitoring. ExchangeRate-API as fallback if Upbit USDT/KRW feed is unavailable.

---

### 5.5 Option D: Binance USDT/KRW (via KRWUSDT pair)

Binance does not list KRW-denominated pairs for most users. Not applicable.

---

### 5.6 KRW/USD Recommendation

**Primary:** Upbit `KRW-USDT` WebSocket tick (already connected; no extra request)
**Fallback:** ExchangeRate-API with free registered key (`https://v6.exchangerate-api.com/v6/{KEY}/latest/USD`), polled once per minute

---

## 6. Exchange WebSocket Client Library

### 6.1 Option A: websockets 14.x (Direct, per-exchange)

**Version (2025-2026):** websockets 14.x

**Architecture:**
Each exchange gets a dedicated asyncio Task with a persistent WebSocket connection. The exchange-specific JSON normalization is implemented in each connector module. This gives full control over reconnection logic, heartbeat handling, and the exact data fields extracted.

**Pros:**
- Full control over message parsing and normalization
- Per-exchange reconnection strategy can be tuned independently
- No licensing constraints (ccxt.pro WebSocket is LGPL-licensed, websockets is BSD)
- Simpler debugging: single library, standard asyncio patterns
- websockets 14.x includes C extension for high-throughput JSON parsing paths

**Cons:**
- Must implement exchange-specific normalization manually (5 exchange-specific connectors)
- More code to write upfront

**Verdict:** Recommended for this project. The exchange-specific normalization is bounded work (5 connectors), and full control over reconnection and parsing is valuable.

---

### 6.2 Option B: cryptofeed 3.x

**Version:** cryptofeed ~3.x

**Architecture:**
cryptofeed is a WebSocket data feed library specifically for cryptocurrency exchanges. It uses a `FeedHandler` object to manage multiple exchange connections and normalizes data into standard callbacks.

**Exchange support:** 40+ exchanges including Bithumb, Upbit, Binance, Bybit (Coinone is NOT listed as supported as of 2025)

**Pros:**
- Exchange connectors pre-built and maintained by the community
- Normalized callbacks: `async def ticker(t: Ticker, receipt_timestamp: float): ...`
- Handles reconnection, heartbeat, and backpressure automatically

**Cons:**
- Coinone is not supported — requires a custom connector regardless
- Library overhead: FeedHandler runs in its own asyncio loop, requiring `asyncio.gather` or thread coordination
- Less flexibility for custom message handling
- Community-maintained; exchange support may lag behind API changes

**Verdict:** Viable for 4 of 5 exchanges (Bithumb, Upbit, Binance, Bybit). Not viable as the sole solution since Coinone requires a custom connector. Not recommended as primary approach due to the Coinone gap and reduced flexibility.

---

### 6.3 Option C: ccxt.pro (paid WebSocket API)

**Version (2025-2026):** ccxt 4.4.x (base, free); ccxt.pro (WebSocket, now included in ccxt as of 2024 — verify current pricing)

**Status (2025):** ccxt documentation states WebSocket APIs are now included in the base ccxt package (previously ccxt.pro was a paid subscription). Verify current license before use.

**Exchange support:** All 5 exchanges supported (Bithumb, Upbit, Coinone, Binance, Bybit)

**Pros:**
- All 5 exchanges in one library
- `watch_ticker()`, `watch_order_book()` methods provide normalized data
- Widely used in the crypto Python community

**Cons:**
- Abstraction layer limits per-exchange optimization
- Historical pricing confusion (pro vs free) makes long-term maintenance risk
- Less control over reconnection strategies

**Verdict:** Worth evaluating if ccxt WebSocket is confirmed free in current version. If the ccxt.pro WebSocket is now free, use ccxt for the 4 standard exchanges and implement Coinone manually. Final decision should be made at implementation time with current ccxt documentation.

---

### 6.4 WebSocket Client Recommendation

**Primary:** `websockets 14.x` with per-exchange asyncio Task connectors

**Rationale:** Full control, BSD license, no Coinone support gap, and the implementation cost (5 exchange connectors) is bounded and well-understood from Step 1 API research.

---

## 7. Existing Project Analysis

### 7.1 Project 1: crypto-arbitrage-framework (hzjken)

**Repository:** `github.com/hzjken/crypto-arbitrage-framework`
**Stack:** Python + ccxt + docplex (IBM CPLEX solver)
**Architecture pattern:** Three-component — PathOptimizer (LP solver) → AmtOptimizer → TradeExecutor (multi-threaded)
**WebSocket approach:** REST polling via ccxt; no WebSocket streaming
**Alert mechanism:** Not present; execution-focused

**Lessons learned:**
1. ccxt abstracts exchange API differences effectively for multi-exchange portfolio projects
2. Multi-threading for trade execution (not applicable here — monitoring only)
3. No WebSocket = polling latency; this design is suboptimal for real-time spread monitoring where sub-second latency matters
4. Linear programming for path optimization is clever for triangular arbitrage but overly complex for a simple kimchi premium monitor

**Architectural pattern extracted:** ccxt as exchange abstraction layer; modular per-exchange connector with a central aggregator is the right pattern even if this project implements connectors manually.

---

### 7.2 Project 2: realtime_crypto_arbitrage_bot (ehgp)

**Repository:** `github.com/ehgp/realtime_crypto_arbitrage_bot`
**Stack:** Python + ccxt + Redis/RabbitMQ (message broker) + Pandas/NumPy
**Architecture pattern:** Producer → Message Queue → Consumer pattern
**WebSocket approach:** ccxt WebSocket watch methods
**Alert mechanism:** Configured thresholds with notification delivery

**Lessons learned:**
1. Message queue (Redis/RabbitMQ) between exchange connectors and spread calculator adds resilience but also complexity — for a 5-exchange single-user monitor, direct asyncio queues are simpler and sufficient
2. Pandas for spread calculation is convenient but introduces dependency weight; for simple arithmetic (kimchi premium = (KRW price / rate) - USDT price), raw Python arithmetic is faster and avoids the pandas import overhead
3. ccxt WebSocket watch methods work but abstract away exchange-specific reconnection strategies — a concern when exchange APIs change
4. The architecture of Producer (exchange connectors) → shared state → Consumer (spread calculator) is exactly right. Whether the shared state is a message queue or an asyncio Queue depends on scale.

**Architectural pattern extracted:** Separate concerns — exchange data collection, normalization, spread calculation, alert checking, and notification delivery are distinct modules. This modular separation makes the system testable and maintainable.

---

### 7.3 Project 3: albertoecf/crypto_arbitrage (Enterprise Pattern)

**Repository:** `github.com/albertoecf/crypto_arbitrage`
**Stack:** Python + ccxt + Kafka + Pandas
**Architecture pattern:** Enterprise messaging — market_data queue → arbitrage_detection → trade_orders queue → trade_execution
**WebSocket approach:** ccxt + Kafka producers

**Lessons learned:**
1. Kafka is valuable for high-throughput trading systems but is severe overkill for a 5-exchange monitoring service — adds Docker/ZooKeeper/Kafka operational overhead
2. The three-stage pipeline pattern (data collection → analysis → action) is correct and should be preserved in simpler form: asyncio queues instead of Kafka, same logical separation
3. Python + ccxt is the community-standard stack for this domain; the pattern appears in project after project

**Architectural pattern extracted:** The data collection → analysis → action pipeline is universal. For this project: exchange WebSocket tasks → asyncio internal queue → spread engine → alert engine → Telegram/WebSocket broadcast.

---

### 7.4 Architecture Pattern Synthesis

Across all analyzed projects, a consistent architecture emerges:

```
Exchange WebSocket Tasks (5x)
           ↓ (asyncio Queue or direct call)
    Normalization Layer (per-exchange → unified PriceTick)
           ↓
    Spread Calculation Engine (KRW/USDT → % premium)
           ↓
    ┌─────────────────────────┐
    │  Alert Engine           │──→ Telegram Bot
    │  (threshold check)      │
    └─────────────────────────┘
           ↓
    ┌─────────────────────────┐
    │  WebSocket Broadcast    │──→ Dashboard WebSocket clients
    │  (connected clients)    │
    └─────────────────────────┘
           ↓
    ┌─────────────────────────┐
    │  Storage Layer          │──→ SQLite (price_snapshots, spreads)
    └─────────────────────────┘
```

REST API serves historical data and alert configuration CRUD on top of the same SQLite storage.

---

## 8. Final Recommended Stack

### Complete Stack

| Component | Technology | Version | Rationale |
|-----------|-----------|---------|-----------|
| **Language** | Python | 3.12 | Ecosystem, asyncio maturity, type hints |
| **Backend framework** | FastAPI | 0.115.x | Async-native, OpenAPI docs, Pydantic v2 |
| **ASGI server** | Uvicorn + uvloop | 0.32.x | Production ASGI server; uvloop on Linux for 2x throughput |
| **Exchange WS client** | websockets | 14.x | BSD, full control, asyncio-native |
| **HTTP client** | httpx | 0.27.x | Async HTTP for REST snapshots + KRW rate polling |
| **Data validation** | Pydantic | v2.x | Request/response types, runtime validation |
| **ORM** | SQLAlchemy | 2.x (async) | Async ORM, easy SQLite→PostgreSQL migration |
| **DB migrations** | Alembic | 1.14.x | Schema versioning |
| **Database** | SQLite 3.47+ (WAL) | — | Zero-setup, single-user, WAL for concurrent reads |
| **Async DB client** | aiosqlite | 0.20.x | Non-blocking SQLite in asyncio event loop |
| **Telegram bot** | aiogram | 3.25.x | Native asyncio, Telegram Bot API 9.2 |
| **KRW/USD rate** | Upbit USDT/KRW WS (primary) + ExchangeRate-API (fallback) | — | Real-time from existing connection |
| **Frontend framework** | React | 19.x | Ecosystem, TradingView Lightweight Charts support |
| **Build tool** | Vite | 6.x | Fast HMR, SPA (no SSR needed) |
| **Language (FE)** | TypeScript | 5.x | Type safety, API contract sharing |
| **State management** | Zustand | 5.x | Minimal boilerplate, works in WS callbacks |
| **Charts (price)** | TradingView Lightweight Charts | 5.x | Financial-grade, real-time ticks, Apache 2.0 |
| **Charts (spread)** | Recharts | 2.x | Spread trend lines, React-native API |
| **Styling** | Tailwind CSS | 4.x | Utility-first, minimal CSS overhead |
| **API client (FE)** | TanStack Query (React Query) | 5.x | REST data fetching with caching |
| **Linting/Format** | ESLint 9 + Prettier 3 (FE) / Ruff 0.8 (BE) | — | Code quality |
| **Testing (BE)** | pytest + pytest-asyncio | — | Async test support |

### Dependency Summary (Backend, key packages)

```txt
fastapi==0.115.*
uvicorn[standard]==0.32.*
websockets==14.*
httpx==0.27.*
pydantic==2.*
sqlalchemy[asyncio]==2.*
aiosqlite==0.20.*
alembic==1.14.*
aiogram==3.25.*
python-dotenv==1.*
```

### Dependency Summary (Frontend, key packages)

```json
{
  "react": "^19.0.0",
  "react-dom": "^19.0.0",
  "typescript": "^5.0.0",
  "vite": "^6.0.0",
  "zustand": "^5.0.0",
  "lightweight-charts": "^5.0.0",
  "recharts": "^2.10.0",
  "@tanstack/react-query": "^5.0.0",
  "tailwindcss": "^4.0.0"
}
```

---

## 9. Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Bithumb API changes (v1 migration) | Medium | High | Implement Bithumb connector against v1 API with fallback detection |
| Coinone WebSocket instability (older API) | Medium | Medium | Polling fallback for Coinone if WebSocket degrades |
| USDT depegging (Upbit KRW/USDT rate) | Low | Medium | ExchangeRate-API fallback at 1% USDT deviation threshold |
| SQLite write lock under high load | Low | Low | WAL mode; rate-limit write throughput to 1 write/tick |
| aiogram/FastAPI event loop conflict | Low | Medium | Use FastAPI lifespan context for aiogram initialization |
| ccxt WebSocket licensing change | Low | Low | Using `websockets` directly; ccxt is optional enhancement only |

---

## 10. Sources

- FastAPI WebSocket benchmarks: [blog.poespas.me](https://blog.poespas.me/posts/2025/03/05/fastapi-websockets-asynchronous-tasks/), [Medium (250k msg/s)](https://medium.com/@bhagyarana80/the-fastapi-stack-that-handled-250-000-websocket-messages-per-second-77c15339e31c)
- FastAPI 45k concurrent WebSocket: [Medium](https://medium.com/@ar.aldhafeeri11/part-1-fastapi-45k-concurrent-websocket-on-single-digitalocean-droplet-1e4fce4c5a64)
- Framework comparison: [FastAPI vs NestJS](https://slashdot.org/software/comparison/FastAPI-vs-NestJS/)
- React vs Vue vs Svelte 2025: [jsgurujobs.com](https://jsgurujobs.com/blog/svelte-5-vs-react-19-vs-vue-4-the-2025-framework-war-nobody-expected-performance-benchmarks), [Medium](https://medium.com/@jessicajournal/react-vs-vue-vs-svelte-the-ultimate-2025-frontend-performance-comparison-5b5ce68614e2)
- Vite vs Next.js: [strapi.io](https://strapi.io/blog/vite-vs-nextjs-2025-developer-framework-comparison)
- TimescaleDB vs InfluxDB: [sanj.dev](https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison), [Timescale](https://www.timescale.com/blog/timescaledb-vs-influxdb-for-time-series-data-timescale-influx-sql-nosql-36489299877)
- aiogram vs python-telegram-bot: [restack.io](https://www.restack.io/p/best-telegram-bot-frameworks-ai-answer-python-telegram-bot-vs-aiogram-cat-ai), [piptrends.com](https://piptrends.com/compare/python-telegram-bot-vs-aiogram)
- ExchangeRate-API: [exchangerate-api.com](https://www.exchangerate-api.com/docs/free)
- cryptofeed library: [github.com/bmoscon/cryptofeed](https://github.com/bmoscon/cryptofeed)
- ccxt library: [github.com/ccxt/ccxt](https://github.com/ccxt/ccxt)
- websockets library: [websockets.readthedocs.io](https://websockets.readthedocs.io/)
- SQLite vs PostgreSQL: [betterstack.com](https://betterstack.com/community/guides/databases/postgresql-vs-sqlite/), [sqlite.org](https://sqlite.org/whentouse.html)
- TradingView Lightweight Charts: [tradingview.github.io/lightweight-charts](https://tradingview.github.io/lightweight-charts/)
- Existing projects: [hzjken/crypto-arbitrage-framework](https://github.com/hzjken/crypto-arbitrage-framework), [albertoecf/crypto_arbitrage](https://github.com/albertoecf/crypto_arbitrage), [ehgp/realtime_crypto_arbitrage_bot](https://ehgp.github.io/realtime_crypto_arbitrage_bot/getting_started.html)
- Go framework comparison: [buanacoding.com](https://www.buanacoding.com/2025/09/fiber-vs-gin-vs-echo-golang-framework-comparison-2025.html)
- Redis WebSocket scaling: [itnext.io](https://itnext.io/scalable-real-time-apps-with-python-and-redis-exploring-asyncio-fastapi-and-pub-sub-79b56a9d2b94)
