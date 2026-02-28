# System Architecture — Crypto Arbitrage Monitor

**Document Date:** 2026-02-28
**Step:** 4 (System Architecture Design)
**Input Dependencies:** Step 1 (Exchange API Analysis), Step 2 (Tech Stack Analysis), Step 3 (Tech Stack Selection)
**Purpose:** Complete system architecture for a real-time cryptocurrency arbitrage monitor tracking 5 exchanges with kimchi premium calculation and Telegram alerting

---

## Table of Contents

1. [High-Level Component Diagram](#1-high-level-component-diagram)
2. [Data Flow Pipeline](#2-data-flow-pipeline)
3. [WebSocket Connection Management](#3-websocket-connection-management)
4. [Data Normalization Layer](#4-data-normalization-layer)
5. [Spread Calculation Engine](#5-spread-calculation-engine)
6. [Alert Engine](#6-alert-engine)
7. [REST API & WebSocket Server](#7-rest-api--websocket-server)
8. [Database Layer](#8-database-layer)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Project Directory Structure](#10-project-directory-structure)
11. [Error Recovery & Resilience](#11-error-recovery--resilience)
12. [Deployment Architecture](#12-deployment-architecture)
13. [Design Decisions & Trade-offs](#13-design-decisions--trade-offs)

---

## 1. High-Level Component Diagram

### 1.1 System Overview

The system follows a **single-process, event-driven architecture** where all components run as asyncio Tasks within one Python process. This eliminates inter-process communication complexity while providing sufficient concurrency for 5 exchange WebSocket connections, spread calculation, alert delivery, and dashboard serving.

[trace:step-1:exchange-comparison-matrix] The five exchanges split into two currency zones: KRW-denominated (Bithumb, Upbit, Coinone) and USDT-denominated (Binance, Bybit). This dual-currency architecture is the fundamental constraint that shapes the entire data flow — every cross-zone spread calculation requires a live KRW/USD exchange rate as a third input.

```mermaid
graph TB
    subgraph ExchangeConnectors["Exchange Connectors (5 asyncio Tasks)"]
        BC[Bithumb Connector<br/>WS: ws-api.bithumb.com]
        UC[Upbit Connector<br/>WS: api.upbit.com]
        CC[Coinone Connector<br/>WS: stream.coinone.co.kr<br/>+ REST fallback]
        BNC[Binance Connector<br/>WS: stream.binance.com]
        BYC[Bybit Connector<br/>WS: stream.bybit.com]
    end

    subgraph FXRate["KRW/USD Rate Provider"]
        UPBIT_FX[Upbit KRW-USDT<br/>WebSocket - Primary]
        ER_API[ExchangeRate-API<br/>REST Polling - Fallback]
    end

    subgraph Core["Core Engine (asyncio Tasks)"]
        WSM[WebSocket Connection Manager<br/>Reconnection + Heartbeat]
        DN[Data Normalizer<br/>Exchange → Common Schema]
        PS[Price Store<br/>In-Memory Dict + DB Write]
        SC[Spread Calculator<br/>Kimchi Premium + Same-Currency]
        AE[Alert Engine<br/>Threshold + Cooldown + Telegram]
    end

    subgraph Server["Server Layer"]
        API[FastAPI REST API<br/>Uvicorn ASGI]
        WSS[WebSocket Server<br/>Dashboard Push]
    end

    subgraph Storage["Storage Layer"]
        DB[(SQLite WAL<br/>aiosqlite)]
    end

    subgraph External["External Services"]
        TG[Telegram Bot API<br/>aiogram 3.25]
    end

    subgraph Frontend["Frontend (Separate Process)"]
        REACT[React 19 + Vite 6<br/>TypeScript 5]
        TC[TradingView<br/>Lightweight Charts]
        RC[Recharts]
        ZS[Zustand Store]
    end

    BC & UC & CC & BNC & BYC --> WSM
    WSM --> DN
    UPBIT_FX --> DN
    ER_API --> DN
    DN --> PS
    PS --> SC
    SC --> AE
    SC --> WSS
    AE --> TG
    PS --> DB
    SC --> DB
    AE --> DB
    API --> PS
    API --> DB
    WSS --> REACT
    API --> REACT
    REACT --> TC & RC
    REACT --> ZS
```

### 1.2 Component Responsibilities

| Component | Responsibility | Concurrency Model |
|-----------|---------------|-------------------|
| Exchange Connectors (5) | Maintain persistent WS connections to each exchange | 1 asyncio Task per exchange |
| KRW/USD Rate Provider | Supply live exchange rate for cross-zone spreads | Shared with Upbit Connector (primary) + 1 polling Task (fallback) |
| WebSocket Connection Manager | Lifecycle management, reconnection, heartbeat scheduling | Coordinates connector Tasks |
| Data Normalizer | Transform exchange-specific formats to common `TickerUpdate` schema | Inline within each connector Task |
| Price Store | Latest prices per (exchange, symbol) pair; write-through to DB | Thread-safe dict (`asyncio.Lock` not needed — single-threaded event loop) |
| Spread Calculator | Compute all 10 exchange-pair spreads on every price update | Triggered by Price Store writes |
| Alert Engine | Check spreads against thresholds; manage cooldowns; deliver via Telegram | Triggered by Spread Calculator |
| FastAPI REST API | Historical data, configuration CRUD, health endpoints | Uvicorn ASGI server |
| WebSocket Server | Push real-time prices and spreads to connected dashboards | FastAPI WebSocket endpoints |
| Database Layer | Persist price snapshots, spread history, alert configs, alert logs | SQLAlchemy async + aiosqlite |
| Frontend | Dashboard rendering, charts, user configuration UI | React 19 + Vite dev server |

---

## 2. Data Flow Pipeline

### 2.1 End-to-End Data Flow

```mermaid
flowchart LR
    subgraph Sources["Data Sources"]
        EX["5 Exchange<br/>WebSockets"]
        FX["KRW/USD<br/>Rate"]
    end

    subgraph Ingestion["Ingestion"]
        RAW["Raw Messages<br/>(exchange-specific JSON)"]
        NORM["Normalizer<br/>→ TickerUpdate"]
    end

    subgraph Processing["Processing"]
        STORE["Price Store<br/>(in-memory dict)"]
        CALC["Spread Calculator<br/>(10 pairs)"]
        ALERT["Alert Engine<br/>(threshold check)"]
    end

    subgraph Output["Output"]
        DB_OUT["SQLite DB<br/>(async write)"]
        WS_OUT["WS Broadcast<br/>(dashboard)"]
        TG_OUT["Telegram<br/>(alert delivery)"]
    end

    EX --> RAW --> NORM --> STORE
    FX --> NORM
    STORE --> CALC --> ALERT
    STORE --> DB_OUT
    CALC --> DB_OUT
    CALC --> WS_OUT
    ALERT --> TG_OUT
    ALERT --> DB_OUT
```

### 2.2 Pipeline Stages in Detail

**Stage 1 — Raw Message Ingestion**

Each exchange connector receives JSON messages from its WebSocket connection. Message formats differ radically across exchanges:

- **Bithumb/Upbit**: `trade_price` (number), `timestamp` (integer ms)
- **Coinone**: `last` (string), `timestamp` (integer ms)
- **Binance**: `c` (string, single-char key), `E` (integer ms)
- **Bybit**: `lastPrice` (string), `ts` (integer ms)

[trace:step-1:data-format] Per Step 1 research, Coinone, Binance, and Bybit return numeric values as JSON strings, while Bithumb and Upbit return native numbers. The normalizer must handle both cases.

**Stage 2 — Normalization**

Each connector transforms its exchange-specific message into a common `TickerUpdate` dataclass:

```python
@dataclass(frozen=True, slots=True)
class TickerUpdate:
    exchange: str           # "bithumb", "upbit", "coinone", "binance", "bybit"
    symbol: str             # Normalized: "BTC", "ETH", etc.
    price: Decimal          # Latest trade price in native currency
    currency: str           # "KRW" or "USDT"
    volume_24h: Decimal     # 24h trading volume (base asset)
    timestamp_ms: int       # Unix milliseconds (exchange server time)
    received_at_ms: int     # Local receipt time (for latency tracking)
    bid_price: Decimal | None   # Best bid (if available)
    ask_price: Decimal | None   # Best ask (if available)
```

**Why `Decimal` instead of `float`**: Financial price comparison requires exact arithmetic. A `float` rounding error of 0.01 KRW is negligible, but using `Decimal` from the start eliminates an entire class of bugs and is standard practice for financial software. The performance cost is irrelevant at this throughput (~25 updates/second total).

**Stage 3 — Price Store Update**

The Price Store is a dictionary keyed by `(exchange, symbol)` → `TickerUpdate`. On every update:

1. Replace the in-memory entry
2. Enqueue an async DB write (batched, not per-tick — see Section 8)
3. Trigger the Spread Calculator for all pairs involving this exchange+symbol

**Stage 4 — Spread Calculation**

The Spread Calculator computes spreads for all relevant pairs. For a symbol like BTC:
- 3 KRW-vs-USDT pairs: (Bithumb, Upbit, Coinone) x (Binance, Bybit) = 6 kimchi premium pairs
- 3 same-KRW pairs: Bithumb-Upbit, Bithumb-Coinone, Upbit-Coinone
- 1 same-USDT pair: Binance-Bybit
- **Total: 10 pairs per symbol**

Each spread result includes a staleness flag (see Section 5).

**Stage 5 — Alert Check & Output**

- Spreads exceeding user-configured thresholds trigger the Alert Engine
- All spread updates are broadcast to connected dashboard clients via WebSocket
- Price and spread snapshots are periodically written to SQLite

### 2.3 Timing Characteristics

| Stage | Expected Latency | Notes |
|-------|-----------------|-------|
| WS receive → Normalize | < 1 ms | In-process string parsing |
| Normalize → Price Store | < 0.1 ms | Dict assignment |
| Price Store → Spread Calc | < 0.5 ms | 10 pairs × arithmetic |
| Spread Calc → WS Broadcast | < 1 ms | asyncio queue → send |
| Spread Calc → Alert Check | < 0.5 ms | Threshold comparison |
| Alert → Telegram delivery | 100-500 ms | Network round-trip to Telegram API |
| Price Store → DB write | 5-50 ms | Batched async SQLite write |

**End-to-end latency** (exchange WS → dashboard update): **< 5 ms** (excluding network transit to/from exchanges and to the browser).

---

## 3. WebSocket Connection Management

### 3.1 Connection State Machine

Each exchange connector follows a deterministic state machine:

```mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> CONNECTING: connect()
    CONNECTING --> CONNECTED: WS handshake success
    CONNECTING --> WAIT_RETRY: handshake failure / timeout
    CONNECTED --> SUBSCRIBING: send subscription message
    SUBSCRIBING --> ACTIVE: subscription confirmed
    SUBSCRIBING --> WAIT_RETRY: subscription rejected / timeout
    ACTIVE --> DISCONNECTED: connection lost / error / server close
    ACTIVE --> DISCONNECTED: 24h expiry (Binance)
    WAIT_RETRY --> CONNECTING: backoff timer expires
    ACTIVE --> ACTIVE: heartbeat sent/received
```

**States:**

| State | Description | Actions |
|-------|------------|---------|
| `DISCONNECTED` | No active connection | Initiate connection attempt |
| `CONNECTING` | TCP + TLS + WS handshake in progress | 10-second timeout |
| `CONNECTED` | Handshake complete, not yet subscribed | Send subscription message immediately |
| `SUBSCRIBING` | Subscription message sent, awaiting confirmation | 5-second timeout for confirmation |
| `ACTIVE` | Receiving live data | Process messages, send heartbeats |
| `WAIT_RETRY` | Backoff period before next reconnection attempt | Exponential backoff timer running |

### 3.2 Reconnection Strategy

**Exponential backoff with jitter:**

```python
def calculate_backoff(attempt: int) -> float:
    """
    Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, cap at 60s.
    Jitter: ±25% to prevent thundering herd across exchanges.
    """
    base_delay = min(2 ** attempt, 60)  # cap at 60 seconds
    jitter = base_delay * 0.25 * (random.random() * 2 - 1)  # ±25%
    return max(0.5, base_delay + jitter)
```

| Attempt | Base Delay | With Jitter Range |
|---------|-----------|-------------------|
| 0 | 1s | 0.75s - 1.25s |
| 1 | 2s | 1.5s - 2.5s |
| 2 | 4s | 3.0s - 5.0s |
| 3 | 8s | 6.0s - 10.0s |
| 4 | 16s | 12.0s - 20.0s |
| 5 | 32s | 24.0s - 40.0s |
| 6+ | 60s | 45.0s - 75.0s |

**On successful reconnection**: reset attempt counter to 0.

**Why jitter matters**: If the server goes down and all 5 connectors disconnect simultaneously, jitter prevents them from reconnecting at the same instant, which could trigger IP-based rate limits (especially Bithumb's 10 connections/sec limit and Upbit's 5 connections/sec limit).

### 3.3 Per-Exchange Heartbeat Configuration

[trace:step-1:heartbeat-requirements] Step 1 research identified different heartbeat requirements per exchange. The connection manager must handle these individually:

| Exchange | Heartbeat Mechanism | Interval | Implementation |
|----------|-------------------|----------|----------------|
| **Bithumb** | WebSocket protocol-level ping/pong (implicit) | Server-initiated | Respond to server pings automatically (handled by `websockets` library) |
| **Upbit** | Implicit (same as Bithumb — shared API design) | Server-initiated | Same as Bithumb — `websockets` handles pong responses |
| **Coinone** | Application-level JSON ping: `{"request_type": "PING"}` | Every 25 seconds | Dedicated asyncio task sends PING; idle timeout at 30 minutes |
| **Binance** | WebSocket protocol-level ping/pong | Server-initiated | `websockets` auto-responds; additionally reconnect every 23.5 hours (before 24h expiry) |
| **Bybit** | Application-level JSON ping: `{"op": "ping"}` | Every 20 seconds | Dedicated asyncio task sends ping; monitor for pong response |

```python
# Per-exchange heartbeat configuration
HEARTBEAT_CONFIG = {
    "bithumb":  {"type": "protocol", "interval_sec": None},   # server-initiated
    "upbit":    {"type": "protocol", "interval_sec": None},   # server-initiated
    "coinone":  {"type": "application", "interval_sec": 25,
                 "message": {"request_type": "PING"}},
    "binance":  {"type": "protocol", "interval_sec": None,
                 "max_lifetime_sec": 23.5 * 3600},            # reconnect before 24h
    "bybit":    {"type": "application", "interval_sec": 20,
                 "message": {"op": "ping"}},
}
```

### 3.4 Connection Manager Design

The `ConnectionManager` owns the lifecycle of all 5 exchange connectors plus the FX rate provider. It runs as the top-level asyncio Task that spawns child Tasks:

```python
class ConnectionManager:
    """
    Manages all exchange WebSocket connections.
    Each connector runs as an independent asyncio Task.
    """

    async def start(self) -> None:
        """Spawn all connector tasks and the FX rate task."""
        self._tasks = [
            asyncio.create_task(self._run_connector(BithumbConnector())),
            asyncio.create_task(self._run_connector(UpbitConnector())),
            asyncio.create_task(self._run_connector(CoinoneConnector())),
            asyncio.create_task(self._run_connector(BinanceConnector())),
            asyncio.create_task(self._run_connector(BybitConnector())),
            asyncio.create_task(self._run_fx_rate_provider()),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run_connector(self, connector: BaseConnector) -> None:
        """Run a single connector with automatic reconnection."""
        attempt = 0
        while True:
            try:
                await connector.connect()       # CONNECTING → CONNECTED
                await connector.subscribe()     # CONNECTED → SUBSCRIBING → ACTIVE
                attempt = 0                     # reset on success
                await connector.listen()        # ACTIVE (blocks until disconnect)
            except (ConnectionError, asyncio.TimeoutError, WebSocketException) as e:
                logger.warning(f"{connector.exchange} disconnected: {e}")
                connector.set_state(ConnectorState.DISCONNECTED)
            finally:
                await connector.close()

            delay = calculate_backoff(attempt)
            logger.info(f"{connector.exchange} reconnecting in {delay:.1f}s (attempt {attempt})")
            await asyncio.sleep(delay)
            attempt += 1
```

### 3.5 Subscription Messages Per Exchange

| Exchange | Subscription Format | Multi-Symbol |
|----------|-------------------|-------------|
| **Bithumb** | `[{"ticket": "uuid"}, {"type": "ticker", "codes": ["KRW-BTC", ...], "isOnlyRealtime": true}, {"format": "DEFAULT"}]` | Yes — array of codes in one message |
| **Upbit** | `[{"ticket": "uuid"}, {"type": "ticker", "codes": ["KRW-BTC", ...]}, {"format": "DEFAULT"}]` | Yes — same as Bithumb |
| **Coinone** | `{"request_type": "SUBSCRIBE", "channel": "TICKER", "topic": {"quote_currency": "KRW", "target_currency": "BTC"}}` | No — one message per symbol |
| **Binance** | `{"method": "SUBSCRIBE", "params": ["btcusdt@ticker", "ethusdt@ticker"], "id": 1}` | Yes — array of stream names |
| **Bybit** | `{"op": "subscribe", "args": ["tickers.BTCUSDT", "tickers.ETHUSDT"]}` | Yes — array of topic strings |

---

## 4. Data Normalization Layer

### 4.1 Normalization Strategy

Each connector implements a `normalize()` method that transforms exchange-specific JSON into the common `TickerUpdate` schema. The normalizer is **embedded within each connector** rather than being a separate shared module. This keeps exchange-specific parsing logic co-located with connection logic, making each connector a self-contained unit.

### 4.2 Exchange-Specific Normalization Map

| Field | Bithumb | Upbit | Coinone | Binance WS | Bybit WS |
|-------|---------|-------|---------|------------|----------|
| `price` | `trade_price` (number) | `trade_price` (number) | `data.last` (string→Decimal) | `c` (string→Decimal) | `data.lastPrice` (string→Decimal) |
| `symbol` | `code` → strip `"KRW-"` | `code` → strip `"KRW-"` | `data.target_currency` | `s` → strip `"USDT"` | `data.symbol` → strip `"USDT"` |
| `currency` | `"KRW"` (hardcoded) | `"KRW"` (hardcoded) | `"KRW"` (hardcoded) | `"USDT"` (hardcoded) | `"USDT"` (hardcoded) |
| `volume_24h` | `acc_trade_volume_24h` | `acc_trade_volume_24h` | `data.target_volume` (string) | `v` (string) | `data.volume24h` (string) |
| `timestamp_ms` | `timestamp` | `timestamp` | `data.timestamp` | `E` | `ts` (top-level) |
| `bid_price` | Not in ticker stream | Not in ticker stream | `data.best_bids[0].price` | `b` (string) | Not in ticker stream |
| `ask_price` | Not in ticker stream | Not in ticker stream | `data.best_asks[0].price` | `a` (string) | Not in ticker stream |

### 4.3 Symbol Normalization

Exchanges use different market code conventions. The normalizer extracts a canonical base symbol:

```python
SYMBOL_EXTRACTORS = {
    "bithumb": lambda code: code.replace("KRW-", ""),        # "KRW-BTC" → "BTC"
    "upbit":   lambda code: code.replace("KRW-", ""),         # "KRW-BTC" → "BTC"
    "coinone": lambda tc: tc.upper(),                         # "BTC" → "BTC"
    "binance": lambda s: s.replace("USDT", ""),               # "BTCUSDT" → "BTC"
    "bybit":   lambda s: s.replace("USDT", ""),               # "BTCUSDT" → "BTC"
}
```

**Tracked symbols** (configurable, default set):

```python
DEFAULT_SYMBOLS = ["BTC", "ETH", "XRP", "SOL", "DOGE"]
```

This list is configurable at runtime via the REST API and stored in the database.

### 4.4 Coinone Dual-Mode Handling

Coinone requires special treatment because its WebSocket reliability is lower than the other four exchanges. The Coinone connector implements a **dual-mode approach**:

1. **Primary**: WebSocket connection to `wss://stream.coinone.co.kr`
2. **Fallback**: REST polling to `GET /public/v2/ticker_new/KRW/{symbol}` at 2-second intervals if WebSocket is down for > 30 seconds

The fallback engages automatically and disengages when WebSocket reconnects:

```python
class CoinoneConnector(BaseConnector):
    REST_FALLBACK_DELAY = 30.0  # seconds before engaging REST polling
    REST_POLL_INTERVAL = 2.0    # seconds between REST polls

    async def listen(self) -> None:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._ws_listener())
            tg.create_task(self._rest_fallback_monitor())

    async def _rest_fallback_monitor(self) -> None:
        while True:
            if self._ws_stale_for > self.REST_FALLBACK_DELAY:
                await self._poll_rest()
            await asyncio.sleep(self.REST_POLL_INTERVAL)
```

---

## 5. Spread Calculation Engine

### 5.1 Spread Types

The system calculates two types of spreads:

**Type 1 — Kimchi Premium (Cross-Currency)**

Compares KRW-denominated prices against USDT-denominated prices using a live FX rate:

```
kimchi_premium_pct = ((krw_price / usd_krw_rate) / usdt_price - 1) × 100
```

- Positive value = KRW exchanges trade at a premium (typical "kimchi premium")
- Negative value = KRW exchanges trade at a discount

**Type 2 — Same-Currency Spread**

Compares prices within the same currency zone:

```
spread_pct = (price_a / price_b - 1) × 100
```

No FX conversion needed. The sign indicates which exchange is more expensive.

### 5.2 Full Spread Matrix

For each tracked symbol, 10 exchange pairs are computed:

| # | Exchange A | Exchange B | Type | Currency Conversion |
|---|-----------|-----------|------|-------------------|
| 1 | Bithumb (KRW) | Binance (USDT) | Kimchi Premium | KRW → USD via FX rate |
| 2 | Bithumb (KRW) | Bybit (USDT) | Kimchi Premium | KRW → USD via FX rate |
| 3 | Upbit (KRW) | Binance (USDT) | Kimchi Premium | KRW → USD via FX rate |
| 4 | Upbit (KRW) | Bybit (USDT) | Kimchi Premium | KRW → USD via FX rate |
| 5 | Coinone (KRW) | Binance (USDT) | Kimchi Premium | KRW → USD via FX rate |
| 6 | Coinone (KRW) | Bybit (USDT) | Kimchi Premium | KRW → USD via FX rate |
| 7 | Bithumb (KRW) | Upbit (KRW) | Same-Currency | None |
| 8 | Bithumb (KRW) | Coinone (KRW) | Same-Currency | None |
| 9 | Upbit (KRW) | Coinone (KRW) | Same-Currency | None |
| 10 | Binance (USDT) | Bybit (USDT) | Same-Currency | None |

### 5.3 KRW/USD Rate Strategy

**Primary source**: Upbit `KRW-USDT` WebSocket ticker

The Upbit connector already maintains a WebSocket connection. By subscribing to `KRW-USDT` in addition to crypto symbols, the system gets a sub-second KRW/USDT rate at zero extra cost. Since USDT pegs closely to USD (typically within ±0.1%), this provides a market-derived exchange rate that reflects the actual rate Korean traders use.

**Fallback source**: ExchangeRate-API REST polling

If the Upbit KRW-USDT feed is unavailable (e.g., Upbit connector is disconnected), the system falls back to ExchangeRate-API:

```python
class FxRateProvider:
    def __init__(self):
        self._rate: Decimal | None = None
        self._source: str = "none"
        self._last_update_ms: int = 0

    def update_from_upbit(self, krw_usdt_price: Decimal, timestamp_ms: int) -> None:
        """Called by Upbit connector on every KRW-USDT tick."""
        self._rate = krw_usdt_price
        self._source = "upbit"
        self._last_update_ms = timestamp_ms

    async def update_from_rest_fallback(self) -> None:
        """Polled every 60 seconds as fallback."""
        # GET https://open.er-api.com/v6/latest/USD → rates.KRW
        ...

    def get_rate(self) -> tuple[Decimal, str, bool]:
        """Returns (rate, source, is_stale)."""
        age_ms = current_time_ms() - self._last_update_ms
        is_stale = age_ms > 60_000  # stale if > 60 seconds old
        return self._rate, self._source, is_stale
```

### 5.4 Staleness Detection

A spread calculation is only valid when all its inputs are fresh. The system enforces a **5-second staleness threshold** per price input:

```python
PRICE_STALE_THRESHOLD_MS = 5_000
FX_RATE_STALE_THRESHOLD_MS = 60_000  # FX rate can be older (moves slowly)

@dataclass(frozen=True, slots=True)
class SpreadResult:
    exchange_a: str
    exchange_b: str
    symbol: str
    spread_pct: Decimal
    spread_type: str              # "kimchi_premium" or "same_currency"
    timestamp_ms: int
    is_stale: bool                # True if any input exceeded staleness threshold
    stale_reason: str | None      # e.g., "coinone price 12s old"
    price_a: Decimal
    price_b: Decimal
    fx_rate: Decimal | None       # None for same-currency spreads
    fx_source: str | None         # "upbit" or "exchangerate-api"
```

**Stale spread behavior**:
- Stale spreads are still computed and displayed (with a visual indicator on the dashboard)
- Stale spreads do **not** trigger alerts (to prevent false positives from cached prices)
- The dashboard shows the staleness reason (e.g., "Coinone disconnected 12s ago")

### 5.5 Update Trigger

The Spread Calculator runs **reactively** — it is triggered whenever any input changes:

```python
class SpreadCalculator:
    def __init__(self, price_store: PriceStore, fx_provider: FxRateProvider):
        self._price_store = price_store
        self._fx_provider = fx_provider
        self._subscribers: list[Callable] = []  # alert engine, WS broadcaster

    async def on_price_update(self, update: TickerUpdate) -> None:
        """Called by PriceStore on every incoming normalized price."""
        symbol = update.symbol
        spreads: list[SpreadResult] = []

        # Get all current prices for this symbol across exchanges
        prices = self._price_store.get_all_for_symbol(symbol)
        fx_rate, fx_source, fx_stale = self._fx_provider.get_rate()

        # Compute all 10 pairs (or however many have active prices)
        for (ex_a, price_a), (ex_b, price_b) in itertools.combinations(prices.items(), 2):
            spread = self._calculate_pair(ex_a, price_a, ex_b, price_b, fx_rate, fx_source, fx_stale)
            if spread is not None:
                spreads.append(spread)

        # Notify subscribers (alert engine, WS broadcaster)
        for subscriber in self._subscribers:
            await subscriber(spreads)
```

---

## 6. Alert Engine

### 6.1 Alert Configuration

Users configure alerts through the Telegram bot or the REST API. Configuration is stored in SQLite:

```python
@dataclass
class AlertConfig:
    id: int
    chat_id: int                    # Telegram chat ID
    symbol: str | None              # None = all symbols
    exchange_a: str | None          # None = any exchange
    exchange_b: str | None          # None = any exchange
    threshold_pct: Decimal           # e.g., 3.0 for 3%
    direction: str                  # "above", "below", "both"
    cooldown_minutes: int           # per-pair cooldown (default: 5)
    enabled: bool
    created_at: datetime
```

### 6.2 Alert Logic

```python
class AlertEngine:
    def __init__(self, db: Database, telegram: TelegramBot):
        self._db = db
        self._telegram = telegram
        self._cooldowns: dict[str, float] = {}  # "pair_key" → last_alert_timestamp

    async def check_spreads(self, spreads: list[SpreadResult]) -> None:
        configs = await self._db.get_active_alert_configs()

        for spread in spreads:
            if spread.is_stale:
                continue  # Never alert on stale data

            for config in configs:
                if self._matches(spread, config) and self._exceeds_threshold(spread, config):
                    pair_key = f"{config.chat_id}:{spread.exchange_a}:{spread.exchange_b}:{spread.symbol}"

                    if not self._in_cooldown(pair_key, config.cooldown_minutes):
                        await self._send_alert(spread, config)
                        self._cooldowns[pair_key] = time.time()
                        await self._log_alert(spread, config)
```

### 6.3 Cooldown Mechanism

Per-pair cooldown prevents alert spam. The key insight is that cooldown is scoped to `(chat_id, exchange_a, exchange_b, symbol)` — a user receives at most one alert per pair per cooldown period:

```python
def _in_cooldown(self, pair_key: str, cooldown_minutes: int) -> bool:
    last_sent = self._cooldowns.get(pair_key)
    if last_sent is None:
        return False
    elapsed = time.time() - last_sent
    return elapsed < (cooldown_minutes * 60)
```

**Default cooldown**: 5 minutes per pair per user. Configurable from 1 to 60 minutes.

### 6.4 Telegram Message Format

```
🔔 Kimchi Premium Alert

BTC: Bithumb vs Binance
Spread: +3.42% (threshold: ±3.00%)

Bithumb: ₩88,200,000 KRW
Binance: $65,000.15 USDT
FX Rate: ₩1,320.50/USD (Upbit USDT)

⏰ 2026-02-28 14:32:05 KST
```

For same-currency spreads:

```
🔔 Spread Alert

ETH: Upbit vs Bithumb
Spread: +1.85% (threshold: ±1.50%)

Upbit:   ₩4,320,000 KRW
Bithumb: ₩4,241,500 KRW

⏰ 2026-02-28 14:32:05 KST
```

### 6.5 Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register chat for alerts |
| `/status` | Show current spreads for all tracked symbols |
| `/alert set BTC 3.0` | Set kimchi premium alert at 3% for BTC |
| `/alert list` | List active alert configurations |
| `/alert remove <id>` | Remove an alert |
| `/exchanges` | Show connection status of all 5 exchanges |
| `/help` | Command reference |

### 6.6 Alert History Logging

Every alert sent is logged to the `alert_history` table:

```python
class AlertHistoryRecord:
    alert_config_id: int
    spread_result: SpreadResult    # full spread snapshot
    message_text: str
    telegram_delivered: bool
    telegram_message_id: int | None
    created_at: datetime
```

---

## 7. REST API & WebSocket Server

### 7.1 FastAPI Application Structure

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: launch all background tasks
    conn_manager = ConnectionManager(...)
    spread_calc = SpreadCalculator(...)
    alert_engine = AlertEngine(...)
    telegram_bot = TelegramBot(...)

    tasks = [
        asyncio.create_task(conn_manager.start()),
        asyncio.create_task(telegram_bot.start_polling()),
    ]

    yield  # Application runs

    # Shutdown: clean up
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(title="Crypto Arbitrage Monitor", lifespan=lifespan)
```

### 7.2 REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check + exchange connection status |
| `GET` | `/api/v1/prices` | Current prices for all exchanges and symbols |
| `GET` | `/api/v1/prices/{symbol}` | Prices for a specific symbol across exchanges |
| `GET` | `/api/v1/spreads` | Current spread matrix (all pairs) |
| `GET` | `/api/v1/spreads/history` | Historical spread data (query params: symbol, exchange pair, time range) |
| `GET` | `/api/v1/exchanges` | Exchange connection status and metadata |
| `GET` | `/api/v1/alerts` | List alert configurations |
| `POST` | `/api/v1/alerts` | Create new alert configuration |
| `PUT` | `/api/v1/alerts/{id}` | Update alert configuration |
| `DELETE` | `/api/v1/alerts/{id}` | Delete alert configuration |
| `GET` | `/api/v1/alerts/history` | Alert history log |
| `GET` | `/api/v1/symbols` | List of tracked symbols |
| `PUT` | `/api/v1/symbols` | Update tracked symbol list |
| `GET` | `/api/v1/fx-rate` | Current KRW/USD rate and source |

### 7.3 WebSocket Server (Dashboard Push)

The server exposes a single WebSocket endpoint for the dashboard:

```
WS /api/v1/ws
```

**Message protocol** (server → client, JSON):

```json
{
  "type": "price_update",
  "data": {
    "exchange": "bithumb",
    "symbol": "BTC",
    "price": "88200000",
    "currency": "KRW",
    "volume_24h": "1234.5678",
    "timestamp_ms": 1709107200000
  }
}
```

```json
{
  "type": "spread_update",
  "data": {
    "exchange_a": "bithumb",
    "exchange_b": "binance",
    "symbol": "BTC",
    "spread_pct": "3.42",
    "spread_type": "kimchi_premium",
    "is_stale": false,
    "fx_rate": "1320.50",
    "fx_source": "upbit",
    "timestamp_ms": 1709107200000
  }
}
```

```json
{
  "type": "connection_status",
  "data": {
    "exchange": "coinone",
    "state": "ACTIVE",
    "latency_ms": 45
  }
}
```

**Client → server messages**:

```json
{
  "type": "subscribe",
  "symbols": ["BTC", "ETH"]
}
```

**Broadcast pattern**: The server maintains a set of connected dashboard clients. On every spread update, the broadcast task iterates through all clients and sends the update. Disconnected clients are removed from the set.

```python
class DashboardBroadcaster:
    def __init__(self):
        self._clients: set[WebSocket] = set()

    async def broadcast(self, message: dict) -> None:
        payload = json.dumps(message)
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send_text(payload)
            except WebSocketDisconnect:
                disconnected.add(ws)
        self._clients -= disconnected
```

---

## 8. Database Layer

### 8.1 Schema Design

```mermaid
erDiagram
    exchanges {
        TEXT id PK "e.g., 'bithumb'"
        TEXT name "Display name"
        TEXT currency "KRW or USDT"
        TEXT ws_url "WebSocket endpoint"
        TEXT rest_url "REST base URL"
        INTEGER created_at
    }

    tracked_symbols {
        TEXT symbol PK "e.g., 'BTC'"
        INTEGER enabled "0 or 1"
        INTEGER created_at
    }

    price_snapshots {
        INTEGER id PK
        TEXT exchange FK
        TEXT symbol FK
        TEXT price "Decimal as string"
        TEXT currency
        TEXT volume_24h
        INTEGER exchange_timestamp_ms
        INTEGER received_at_ms
        INTEGER created_at
    }

    spread_records {
        INTEGER id PK
        TEXT exchange_a FK
        TEXT exchange_b FK
        TEXT symbol FK
        TEXT spread_pct "Decimal as string"
        TEXT spread_type "kimchi_premium or same_currency"
        INTEGER is_stale "0 or 1"
        TEXT fx_rate
        TEXT fx_source
        INTEGER timestamp_ms
        INTEGER created_at
    }

    alert_configs {
        INTEGER id PK
        INTEGER chat_id
        TEXT symbol
        TEXT exchange_a
        TEXT exchange_b
        TEXT threshold_pct
        TEXT direction "above, below, both"
        INTEGER cooldown_minutes
        INTEGER enabled "0 or 1"
        INTEGER created_at
        INTEGER updated_at
    }

    alert_history {
        INTEGER id PK
        INTEGER alert_config_id FK
        TEXT exchange_a
        TEXT exchange_b
        TEXT symbol
        TEXT spread_pct
        TEXT message_text
        INTEGER telegram_delivered "0 or 1"
        INTEGER telegram_message_id
        INTEGER created_at
    }

    fx_rate_history {
        INTEGER id PK
        TEXT rate "Decimal as string"
        TEXT source "upbit or exchangerate-api"
        INTEGER timestamp_ms
        INTEGER created_at
    }

    exchanges ||--o{ price_snapshots : "has"
    tracked_symbols ||--o{ price_snapshots : "has"
    tracked_symbols ||--o{ spread_records : "has"
    alert_configs ||--o{ alert_history : "triggered"
```

### 8.2 Write Strategy

**Problem**: At 5 exchanges x N symbols x ~1 update/second each, naively inserting every tick into SQLite would produce ~25 writes/second. SQLite WAL mode handles this easily, but storing every tick is unnecessary for historical analysis and wastes disk space.

**Solution — Tiered write strategy**:

| Tier | Data | Write Frequency | Retention |
|------|------|----------------|-----------|
| In-memory (Price Store) | Latest price per (exchange, symbol) | Every tick | Current only |
| `price_snapshots` table | Periodic snapshots | Every 10 seconds (configurable) | 30 days |
| `spread_records` table | Spread snapshots | Every 10 seconds | 30 days |
| `alert_history` table | Alert events | On every alert sent | Indefinite |
| `fx_rate_history` table | FX rate changes | On rate change (deduplicated) | 30 days |

The 10-second snapshot interval captures enough granularity for chart rendering (6 data points per minute) while reducing write volume to ~2.5 writes/second.

**Batch writer implementation**:

```python
class DatabaseWriter:
    BATCH_INTERVAL = 10.0  # seconds

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.BATCH_INTERVAL)
            snapshot = self._price_store.get_all_current()
            spreads = self._spread_calc.get_latest_spreads()

            async with self._db.begin() as session:
                # Batch insert all current prices
                session.add_all([
                    PriceSnapshot(**p) for p in snapshot.values()
                ])
                # Batch insert all current spreads
                session.add_all([
                    SpreadRecord(**s) for s in spreads
                ])
```

### 8.3 Data Retention

A daily cleanup task removes records older than the retention period:

```python
async def cleanup_old_records(db: AsyncSession) -> None:
    cutoff = datetime.utcnow() - timedelta(days=30)
    await db.execute(
        delete(PriceSnapshot).where(PriceSnapshot.created_at < cutoff)
    )
    await db.execute(
        delete(SpreadRecord).where(SpreadRecord.created_at < cutoff)
    )
```

### 8.4 SQLAlchemy Async Configuration

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    "sqlite+aiosqlite:///data/arbitrage.db",
    echo=False,
    connect_args={"check_same_thread": False},
)

# Enable WAL mode on first connection
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")  # faster writes, safe with WAL
    cursor.execute("PRAGMA busy_timeout=5000")    # 5s retry on lock
    cursor.close()

async_session = async_sessionmaker(engine, expire_on_commit=False)
```

### 8.5 Migration Path to TimescaleDB

The SQLAlchemy ORM layer enables a future migration to PostgreSQL/TimescaleDB by changing only the connection string and adding a schema migration:

```python
# SQLite (current)
engine = create_async_engine("sqlite+aiosqlite:///data/arbitrage.db")

# PostgreSQL + TimescaleDB (future)
engine = create_async_engine("postgresql+asyncpg://user:pass@host/arbitrage")
```

TimescaleDB-specific features (hypertables, continuous aggregates, compression) would require additional SQL migrations but no Python code changes.

---

## 9. Frontend Architecture

### 9.1 Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Framework | React | 19 | Component rendering, automatic batching for WS updates |
| Build | Vite | 6 | Fast HMR, TypeScript compilation |
| Language | TypeScript | 5 | Type safety |
| State | Zustand | 5 | Lightweight store for WS data |
| Styling | Tailwind CSS | 4 | Utility-first CSS |
| Charts (financial) | TradingView Lightweight Charts | 5 | Candlestick/line charts for prices |
| Charts (analytical) | Recharts | 2 | Spread trend lines, bar charts |

### 9.2 Application Structure

```
frontend/src/
├── App.tsx                     # Root component + router
├── main.tsx                    # Entry point
├── api/
│   ├── rest.ts                 # REST API client (fetch wrapper)
│   └── websocket.ts            # WebSocket connection manager
├── stores/
│   ├── priceStore.ts           # Zustand: per-exchange prices
│   ├── spreadStore.ts          # Zustand: spread matrix
│   ├── connectionStore.ts      # Zustand: exchange connection status
│   └── alertStore.ts           # Zustand: alert configurations
├── components/
│   ├── layout/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── StatusBar.tsx
│   ├── dashboard/
│   │   ├── SpreadMatrix.tsx    # Main spread matrix table
│   │   ├── PriceCard.tsx       # Per-exchange price display
│   │   ├── PriceChart.tsx      # TradingView Lightweight Chart
│   │   └── SpreadChart.tsx     # Recharts spread trend line
│   ├── alerts/
│   │   ├── AlertConfigList.tsx
│   │   ├── AlertConfigForm.tsx
│   │   └── AlertHistory.tsx
│   └── common/
│       ├── StaleBadge.tsx      # Visual indicator for stale data
│       ├── ExchangeStatus.tsx  # Connection status indicator
│       └── LoadingSpinner.tsx
├── hooks/
│   ├── useWebSocket.ts         # WS connection hook
│   ├── usePrices.ts            # Price data hook
│   └── useSpreads.ts           # Spread data hook
├── types/
│   └── index.ts                # Shared TypeScript interfaces
└── utils/
    ├── format.ts               # Price/percentage formatters
    └── constants.ts            # API URLs, default configs
```

### 9.3 WebSocket Client (Frontend)

```typescript
// api/websocket.ts
class ArbitrageWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempt = 0;

  connect() {
    this.ws = new WebSocket(`ws://${location.host}/api/v1/ws`);

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case "price_update":
          usePriceStore.getState().updatePrice(msg.data);
          break;
        case "spread_update":
          useSpreadStore.getState().updateSpread(msg.data);
          break;
        case "connection_status":
          useConnectionStore.getState().updateStatus(msg.data);
          break;
      }
    };

    this.ws.onclose = () => {
      // Reconnect with backoff
      const delay = Math.min(1000 * 2 ** this.reconnectAttempt, 30000);
      setTimeout(() => this.connect(), delay);
      this.reconnectAttempt++;
    };
  }
}
```

### 9.4 Zustand Price Store

```typescript
// stores/priceStore.ts
interface PriceEntry {
  exchange: string;
  symbol: string;
  price: string;
  currency: string;
  volume24h: string;
  timestampMs: number;
  isStale: boolean;
}

interface PriceStore {
  prices: Record<string, PriceEntry>;  // key: "exchange:symbol"
  updatePrice: (data: PriceEntry) => void;
}

export const usePriceStore = create<PriceStore>((set) => ({
  prices: {},
  updatePrice: (data) =>
    set((state) => ({
      prices: {
        ...state.prices,
        [`${data.exchange}:${data.symbol}`]: {
          ...data,
          isStale: false,
        },
      },
    })),
}));
```

### 9.5 Dashboard Layout

The dashboard is a single-page application with the following layout:

```
┌─────────────────────────────────────────────────────────┐
│ Header: "Crypto Arb Monitor"  [Status: 5/5 connected]  │
├─────────────┬───────────────────────────────────────────┤
│             │  Spread Matrix (main content)             │
│  Symbol     │  ┌─────┬─────┬─────┬─────┬─────┐        │
│  Selector   │  │     │ BTH │ UPB │ CON │ BIN │ BYB    │
│             │  ├─────┼─────┼─────┼─────┼─────┤        │
│  BTC  ●     │  │ BTH │  -  │+0.2%│+0.1%│+3.4%│+3.2%  │
│  ETH  ●     │  │ UPB │     │  -  │-0.1%│+3.2%│+3.0%  │
│  XRP  ○     │  │ CON │     │     │  -  │+3.3%│+3.1%  │
│  SOL  ●     │  │ BIN │     │     │     │  -  │-0.2%  │
│  DOGE ○     │  │ BYB │     │     │     │     │  -    │
│             │  └─────┴─────┴─────┴─────┴─────┘        │
│  ● active   ├───────────────────────────────────────────┤
│  ○ stale    │  Price Chart (TradingView) │ Spread Chart │
│             │  [Selected symbol]         │ (Recharts)   │
│             ├───────────────────────────────────────────┤
│             │  Exchange Prices Table                     │
│             │  Bithumb: ₩88,200,000 | Upbit: ₩88,150.. │
│             ├───────────────────────────────────────────┤
│             │  Alert Configuration Panel                 │
└─────────────┴───────────────────────────────────────────┘
```

---

## 10. Project Directory Structure

```
crypto-arb-monitor/
├── README.md
├── docker-compose.yml                # Optional containerization
├── .env.example                      # Template for environment variables
├── .gitignore
│
├── research/                         # Step 1-2 research outputs
│   ├── exchange-api-analysis.md
│   └── tech-stack-analysis.md
│
├── planning/                         # Step 4-5 design outputs
│   ├── system-architecture.md        # This document
│   └── api-data-model.md             # Step 5: API spec + data models
│
├── backend/
│   ├── pyproject.toml                # Python project config (dependencies, metadata)
│   ├── alembic.ini                   # Database migration config
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/                 # Migration scripts
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app factory + lifespan
│   │   ├── config.py                 # Settings (pydantic-settings, env vars)
│   │   │
│   │   ├── connectors/               # Exchange WebSocket connectors
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # BaseConnector ABC + ConnectorState enum
│   │   │   ├── bithumb.py
│   │   │   ├── upbit.py
│   │   │   ├── coinone.py
│   │   │   ├── binance.py
│   │   │   ├── bybit.py
│   │   │   └── manager.py            # ConnectionManager (spawns all connectors)
│   │   │
│   │   ├── core/                     # Core business logic
│   │   │   ├── __init__.py
│   │   │   ├── price_store.py        # In-memory price storage
│   │   │   ├── spread_calculator.py  # Spread engine (kimchi premium + same-currency)
│   │   │   ├── fx_rate.py            # KRW/USD rate provider (Upbit primary + REST fallback)
│   │   │   └── alert_engine.py       # Alert logic + cooldown + Telegram delivery
│   │   │
│   │   ├── models/                   # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── base.py               # DeclarativeBase
│   │   │   ├── price_snapshot.py
│   │   │   ├── spread_record.py
│   │   │   ├── alert_config.py
│   │   │   ├── alert_history.py
│   │   │   ├── exchange.py
│   │   │   ├── tracked_symbol.py
│   │   │   └── fx_rate_history.py
│   │   │
│   │   ├── schemas/                  # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── ticker.py             # TickerUpdate dataclass
│   │   │   ├── spread.py             # SpreadResult schema
│   │   │   ├── alert.py              # Alert config/history schemas
│   │   │   └── common.py             # Shared types (pagination, error responses)
│   │   │
│   │   ├── api/                      # FastAPI route handlers
│   │   │   ├── __init__.py
│   │   │   ├── router.py             # Main API router (includes sub-routers)
│   │   │   ├── prices.py             # GET /prices, /prices/{symbol}
│   │   │   ├── spreads.py            # GET /spreads, /spreads/history
│   │   │   ├── alerts.py             # CRUD /alerts, /alerts/history
│   │   │   ├── exchanges.py          # GET /exchanges
│   │   │   ├── symbols.py            # GET/PUT /symbols
│   │   │   ├── health.py             # GET /health
│   │   │   └── websocket.py          # WS /ws (dashboard push)
│   │   │
│   │   ├── telegram/                 # Telegram bot integration
│   │   │   ├── __init__.py
│   │   │   ├── bot.py                # aiogram Bot + Dispatcher setup
│   │   │   ├── handlers.py           # Command handlers (/start, /alert, /status)
│   │   │   └── formatters.py         # Alert message formatting
│   │   │
│   │   ├── db/                       # Database utilities
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # AsyncEngine + session factory
│   │   │   ├── writer.py             # Batched periodic writer
│   │   │   └── cleanup.py            # Data retention cleanup
│   │   │
│   │   └── utils/                    # Shared utilities
│   │       ├── __init__.py
│   │       ├── logging.py            # Structured logging setup
│   │       └── backoff.py            # Exponential backoff + jitter
│   │
│   ├── tests/
│   │   ├── conftest.py               # Shared fixtures
│   │   ├── test_connectors/
│   │   │   ├── test_bithumb.py
│   │   │   ├── test_upbit.py
│   │   │   ├── test_coinone.py
│   │   │   ├── test_binance.py
│   │   │   └── test_bybit.py
│   │   ├── test_core/
│   │   │   ├── test_spread_calculator.py
│   │   │   ├── test_alert_engine.py
│   │   │   └── test_fx_rate.py
│   │   └── test_api/
│   │       ├── test_prices.py
│   │       ├── test_spreads.py
│   │       └── test_alerts.py
│   │
│   └── data/                         # SQLite database file (gitignored)
│       └── .gitkeep
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   │
│   ├── public/
│   │   └── favicon.ico
│   │
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── api/
│       │   ├── rest.ts
│       │   └── websocket.ts
│       ├── stores/
│       │   ├── priceStore.ts
│       │   ├── spreadStore.ts
│       │   ├── connectionStore.ts
│       │   └── alertStore.ts
│       ├── components/
│       │   ├── layout/
│       │   ├── dashboard/
│       │   ├── alerts/
│       │   └── common/
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   ├── usePrices.ts
│       │   └── useSpreads.ts
│       ├── types/
│       │   └── index.ts
│       └── utils/
│           ├── format.ts
│           └── constants.ts
│
└── scripts/
    ├── dev.sh                        # Start backend + frontend in dev mode
    └── seed_db.py                    # Seed exchange metadata + default symbols
```

### 10.1 Design Rationale for Directory Structure

**Backend `app/` organization**: The backend follows a **layered architecture** where `connectors/` (data ingestion), `core/` (business logic), `models/` (persistence), and `api/` (presentation) are clearly separated. This makes each layer independently testable.

**Why `schemas/` is separate from `models/`**: SQLAlchemy models define database table structure. Pydantic schemas define API request/response shapes. These often overlap but have different concerns (ORM relationships vs. JSON serialization). Keeping them separate avoids coupling the API contract to the database schema.

**Why no `shared/` directory**: The TypeScript frontend and Python backend do not share code at runtime. The API contract is defined by the Pydantic schemas (which generate OpenAPI docs) and consumed by the TypeScript `types/index.ts`. No cross-language code sharing is needed.

---

## 11. Error Recovery & Resilience

### 11.1 Exchange WebSocket Disconnect

**Scenario**: An exchange WebSocket connection drops (network error, server maintenance, rate limit).

**Recovery**:

```mermaid
flowchart TD
    A[Connection Lost] --> B[Set state: DISCONNECTED]
    B --> C[Mark exchange prices as STALE]
    C --> D[Log warning + emit connection_status to dashboard]
    D --> E[Calculate backoff delay]
    E --> F{Attempt < max?}
    F -->|Yes| G[Wait backoff delay]
    G --> H[Reconnect attempt]
    H -->|Success| I[Resubscribe to all symbols]
    I --> J[Set state: ACTIVE]
    J --> K[Reset attempt counter]
    H -->|Failure| L[Increment attempt counter]
    L --> E
    F -->|No, capped at 60s| G
```

**Per-exchange specific handling**:

| Exchange | Specific Recovery Action |
|----------|------------------------|
| Bithumb | Check for maintenance schedule; double backoff during known maintenance windows |
| Upbit | If HTTP 418 received, honor `Retry-After` header (extended ban for rate limit abuse) |
| Coinone | If close code 4290, enforce single-connection-per-IP rule; do not attempt parallel connections |
| Binance | Schedule proactive reconnect at 23h 30m to avoid 24h forced disconnect |
| Bybit | If 500+ connections/5min triggered, increase minimum backoff to 30 seconds |

### 11.2 KRW/USD Rate Staleness

**Scenario**: Both rate sources (Upbit KRW-USDT and ExchangeRate-API) become unavailable.

**Recovery**:

1. Continue using the last known rate with a `stale_fx` flag
2. All kimchi premium spreads computed with a stale FX rate are marked `is_stale = true`
3. Dashboard shows a warning banner: "FX rate stale (last update: X minutes ago)"
4. No alerts triggered on stale-FX spreads
5. When either source recovers, normal operation resumes automatically

**Acceptable staleness**: KRW/USD moves ~0.1% per day. A rate that is 1 hour stale introduces at most ~0.004% error. The system tolerates up to **1 hour** of FX staleness before marking spreads as stale. Beyond 1 hour, all cross-currency spreads are flagged.

### 11.3 Database Write Failure

**Scenario**: SQLite write fails (disk full, file lock timeout, corruption).

**Recovery**:

```python
class ResilientDatabaseWriter:
    MAX_BUFFER_SIZE = 10_000  # max records to buffer in memory

    async def write_batch(self, records: list) -> None:
        try:
            async with self._session() as session:
                session.add_all(records)
                await session.commit()
                self._buffer.clear()
        except OperationalError as e:
            logger.error(f"DB write failed: {e}")
            self._buffer.extend(records)

            if len(self._buffer) > self.MAX_BUFFER_SIZE:
                # Drop oldest records to prevent memory exhaustion
                dropped = len(self._buffer) - self.MAX_BUFFER_SIZE
                self._buffer = self._buffer[dropped:]
                logger.warning(f"Dropped {dropped} oldest buffered records")

            # Retry on next batch interval (10 seconds)
```

**Key principle**: Database write failures never affect the real-time pipeline. Prices, spreads, and alerts continue to function from in-memory state. Only historical data persistence is degraded.

### 11.4 Telegram API Failure

**Scenario**: Telegram Bot API returns an error or is unreachable.

**Recovery**:

```python
class ResilientTelegramSender:
    MAX_QUEUE_SIZE = 100
    RETRY_DELAYS = [5, 15, 30, 60]  # seconds

    async def send_alert(self, chat_id: int, text: str) -> bool:
        for attempt, delay in enumerate(self.RETRY_DELAYS):
            try:
                await self._bot.send_message(chat_id, text, parse_mode="HTML")
                return True
            except TelegramAPIError as e:
                logger.warning(f"Telegram send failed (attempt {attempt}): {e}")
                if attempt < len(self.RETRY_DELAYS) - 1:
                    await asyncio.sleep(delay)

        # All retries exhausted — log to DB as undelivered
        logger.error(f"Telegram delivery failed after {len(self.RETRY_DELAYS)} attempts")
        return False
```

**Behavior**: Failed Telegram deliveries are logged in `alert_history` with `telegram_delivered = false`. The alert is not re-queued (since the spread condition may no longer be valid by the time retries exhaust). Users can view undelivered alerts in the dashboard's alert history.

### 11.5 Resilience Summary

| Failure | Impact | Recovery Time | Data Loss |
|---------|--------|---------------|-----------|
| Single exchange WS disconnect | 1 exchange stale; spreads involving it flagged | 1-60s (backoff) | None (other exchanges continue) |
| All exchange WS disconnect | All prices stale; no alerts | 1-60s per exchange | None (in-memory state preserved) |
| FX rate unavailable | Cross-currency spreads stale; same-currency spreads unaffected | Automatic on source recovery | None |
| SQLite write failure | No historical data written; real-time pipeline unaffected | Next batch attempt (10s) | Buffered records up to 10K |
| Telegram API down | Alerts logged but not delivered | Up to 4 retries over ~2 min | Alerts marked undelivered in DB |
| Process crash | Full restart required | ~5s (Uvicorn restart) | In-memory prices lost; DB intact |

---

## 12. Deployment Architecture

### 12.1 Single-Server Deployment

This is a portfolio project designed for single-server deployment. The entire system runs on one machine (developer PC, VPS, or Docker host):

```mermaid
graph TB
    subgraph Server["Single Server / VPS"]
        subgraph Backend["Python Process (Uvicorn)"]
            FA[FastAPI App]
            WS_OUT[WS Connectors × 5]
            WS_IN[WS Server for Dashboard]
            TG[Telegram Bot Polling]
            DB_W[DB Writer]
        end

        subgraph Frontend["Node Process (Vite dev) or Static Files"]
            REACT[React SPA]
        end

        subgraph Storage["Filesystem"]
            SQLITE[(arbitrage.db)]
        end
    end

    Internet((Internet)) --> FA
    Internet --> WS_OUT
    Internet --> TG
    FA --> SQLITE
    DB_W --> SQLITE
    REACT --> FA
```

### 12.2 Environment Variables

All secrets and configuration are managed via environment variables:

```bash
# .env.example

# Telegram Bot
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321  # comma-separated

# Database
DATABASE_URL=sqlite+aiosqlite:///data/arbitrage.db

# ExchangeRate-API (fallback FX rate)
EXCHANGERATE_API_KEY=your-key-here  # optional; open access works without key

# Server
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# Frontend (for CORS)
FRONTEND_URL=http://localhost:5173

# Tracked symbols (initial set)
DEFAULT_SYMBOLS=BTC,ETH,XRP,SOL,DOGE

# Alert defaults
DEFAULT_ALERT_COOLDOWN_MINUTES=5
DEFAULT_ALERT_THRESHOLD_PCT=3.0

# Data retention
PRICE_SNAPSHOT_RETENTION_DAYS=30
SPREAD_RECORD_RETENTION_DAYS=30
DB_WRITE_INTERVAL_SECONDS=10
```

### 12.3 Docker Compose (Optional)

```yaml
# docker-compose.yml
version: "3.9"

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - db-data:/app/data
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  db-data:
```

**Backend Dockerfile** (conceptual):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app/ app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Frontend Dockerfile** (conceptual):

```dockerfile
FROM node:22-slim AS build
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

### 12.4 Development Workflow

```bash
# Terminal 1: Backend
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev  # Vite dev server on port 5173, proxies /api to :8000
```

Vite proxy configuration in `vite.config.ts`:

```typescript
export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        ws: true,  // proxy WebSocket connections too
      },
    },
  },
});
```

---

## 13. Design Decisions & Trade-offs

### DD-1: Single Process vs. Multi-Process Architecture

**Decision**: Single asyncio process for all backend components.

**Alternatives considered**:
- Separate processes for connectors, spread engine, and API server (with Redis pub/sub)
- Worker pool with message queuing (RabbitMQ/Redis)

**Trade-off**: Single process eliminates IPC complexity, shared-nothing synchronization issues, and Redis dependency. The cost is that a crash in any component takes down the entire process. For a portfolio project monitoring 5 exchanges with 1-10 dashboard users, this is the right trade-off. The system handles ~25 messages/second total — orders of magnitude below asyncio's capacity.

**Migration path**: If the system ever needs multi-process scaling, the `PriceStore` interface and `SpreadCalculator` subscription pattern are already decoupled enough to insert Redis pub/sub between them.

### DD-2: In-Memory Price Store vs. Database-First

**Decision**: In-memory dict as the primary price store; database as a secondary periodic snapshot.

**Rationale**: The spread calculator needs sub-millisecond access to latest prices. Reading from SQLite on every tick would add 5-50ms latency per read and create unnecessary I/O. The in-memory dict provides O(1) access. Database writes are batched at 10-second intervals for historical analysis only.

**Risk**: Process crash loses in-memory prices. This is acceptable because exchange WebSockets immediately replenish prices on reconnection (typically within 1-2 seconds for active markets).

### DD-3: Decimal vs. Float for Price Arithmetic

**Decision**: Use `decimal.Decimal` for all price and spread calculations.

**Trade-off**: `Decimal` is ~10x slower than `float` for arithmetic operations. At ~25 updates/second with 10 spread calculations each, this amounts to ~250 Decimal operations/second — trivially fast even on modest hardware. The benefit is exact arithmetic that eliminates floating-point representation errors in financial comparisons.

### DD-4: Upbit KRW-USDT as Primary FX Rate

**Decision**: Use Upbit's `KRW-USDT` ticker (already subscribed via WebSocket) as the primary KRW/USD exchange rate, with ExchangeRate-API as fallback.

**Trade-off**: USDT is not exactly USD — Tether occasionally trades at a slight premium or discount (±0.1%). However, Upbit's KRW-USDT rate reflects the **actual conversion rate Korean traders experience**, making it more accurate for kimchi premium calculation than an official bank rate. The ExchangeRate-API fallback provides a safety net if Upbit is disconnected.

### DD-5: Per-Exchange Connector vs. Unified Library (ccxt)

**Decision**: 5 manual per-exchange connectors using the `websockets` library.

[trace:step-2:websocket-client-recommendation] Step 2 analysis showed that `websockets 14.x` with per-exchange connectors provides full control over reconnection, heartbeat, and parsing at the cost of more upfront code. The alternative (ccxt) would reduce code but abstracts away exchange-specific reconnection strategies and does not support Coinone WebSocket.

**Trade-off**: More code to write (~200-300 lines per connector) but full control over error handling, heartbeat timing, and message parsing. Each connector is independently testable with mock WebSocket servers.

### DD-6: Periodic DB Snapshots vs. Every-Tick Writes

**Decision**: Write price and spread snapshots to SQLite every 10 seconds instead of on every tick.

**Trade-off**: 10-second granularity means the database cannot reconstruct sub-10-second price movements. For a monitoring dashboard (not a trading bot), this granularity is sufficient. The benefit is reducing write volume from ~25/sec to ~2.5/sec, which keeps SQLite WAL mode comfortable and extends database file longevity.

### DD-7: Telegram-Only Alerts (No Browser Push or Email)

**Decision**: Telegram as the sole alert delivery channel.

**Rationale**: Telegram is the dominant communication platform for Korean crypto communities. Browser push notifications require service workers and HTTPS (complex for local development). Email delivery requires SMTP configuration and has high latency. Telegram provides instant, reliable delivery via a simple `bot.send_message()` call with rich formatting support.

### DD-8: SQLite WAL Mode vs. PostgreSQL

**Decision**: SQLite WAL mode for initial deployment; architecture supports PostgreSQL migration.

**Trade-off**: SQLite requires zero infrastructure (no database server) and is perfect for a single-user portfolio project. The limitation is single-writer concurrency — only one write transaction at a time. With batched writes every 10 seconds, this is not a bottleneck. The SQLAlchemy async ORM layer means migrating to PostgreSQL/TimescaleDB requires only a connection string change and schema migration.

### DD-9: Tailwind CSS 4 vs. Component Library

**Decision**: Tailwind CSS 4 utility classes instead of a pre-built component library (MUI, Ant Design).

**Trade-off**: Tailwind requires writing more markup but produces smaller bundles and avoids the "every app looks the same" problem of component libraries. For a dashboard with custom spread matrix layouts and chart integrations, utility-first CSS provides more layout flexibility than opinionated component libraries.

### DD-10: Zustand vs. Redux/Context for Frontend State

**Decision**: Zustand 5 for all frontend state management.

**Rationale**: Zustand stores can be updated directly from WebSocket callbacks without React component context. This is critical because the WebSocket `onmessage` handler fires outside React's rendering cycle. Zustand's `getState()` method provides synchronous access that Redux's `dispatch()` pattern cannot match for external event sources. The store is also ~1KB (vs. Redux Toolkit's ~12KB).

---

## Appendix A: Tracked Symbol Coverage

Not all symbols are listed on all 5 exchanges. The system must handle partial coverage:

| Symbol | Bithumb | Upbit | Coinone | Binance | Bybit |
|--------|---------|-------|---------|---------|-------|
| BTC | Yes | Yes | Yes | Yes | Yes |
| ETH | Yes | Yes | Yes | Yes | Yes |
| XRP | Yes | Yes | Yes | Yes | Yes |
| SOL | Yes | Yes | Yes | Yes | Yes |
| DOGE | Yes | Yes | Yes | Yes | Yes |

For symbols not listed on a particular exchange, those exchange-pair spreads are simply not computed. The spread matrix dynamically adjusts based on actual data availability.

## Appendix B: Estimated Resource Requirements

| Resource | Estimate | Notes |
|----------|----------|-------|
| RAM | ~50-100 MB | Python process + in-memory price store |
| CPU | < 5% of 1 core | Arithmetic spread calculation is trivial |
| Disk (DB) | ~500 MB/month | At 10-sec snapshot intervals, 30-day retention |
| Network (outbound) | ~1 MB/hour | 5 WS connections receiving ticker data |
| Network (inbound) | ~0.5 MB/hour | Dashboard WS broadcasts (1-10 clients) |
| WS connections (outbound) | 6 persistent | 5 exchanges + 1 Telegram long-poll |
| WS connections (inbound) | 1-10 | Dashboard clients |
