# 시스템 아키텍처 — 암호화폐 차익거래 모니터

**문서 일자:** 2026-02-28
**단계:** 4 (시스템 아키텍처 설계)
**입력 의존성:** 단계 1 (거래소 API 분석), 단계 2 (기술 스택 분석), 단계 3 (기술 스택 선정)
**목적:** 5개 거래소를 실시간으로 추적하고 김치 프리미엄 계산 및 Telegram 알림을 제공하는 암호화폐 차익거래 모니터의 전체 시스템 아키텍처

---

## 목차

1. [고수준 컴포넌트 다이어그램](#1-고수준-컴포넌트-다이어그램)
2. [데이터 플로우 파이프라인](#2-데이터-플로우-파이프라인)
3. [WebSocket 연결 관리](#3-websocket-연결-관리)
4. [데이터 정규화 계층](#4-데이터-정규화-계층)
5. [스프레드 계산 엔진](#5-스프레드-계산-엔진)
6. [알림 엔진](#6-알림-엔진)
7. [REST API 및 WebSocket 서버](#7-rest-api-및-websocket-서버)
8. [데이터베이스 계층](#8-데이터베이스-계층)
9. [프론트엔드 아키텍처](#9-프론트엔드-아키텍처)
10. [프로젝트 디렉터리 구조](#10-프로젝트-디렉터리-구조)
11. [에러 복구 및 복원력](#11-에러-복구-및-복원력)
12. [배포 아키텍처](#12-배포-아키텍처)
13. [설계 결정 및 트레이드오프](#13-설계-결정-및-트레이드오프)

---

## 1. 고수준 컴포넌트 다이어그램

### 1.1 시스템 개요

본 시스템은 **단일 프로세스, 이벤트 기반 아키텍처**를 따르며, 모든 컴포넌트가 하나의 Python 프로세스 내에서 asyncio Task로 실행된다. 이를 통해 프로세스 간 통신의 복잡성을 제거하면서도, 5개 거래소 WebSocket 연결, 스프레드 계산, 알림 전달, 대시보드 서빙에 충분한 동시성을 확보한다.

[trace:step-1:exchange-comparison-matrix] 5개 거래소는 두 통화 영역으로 나뉜다: KRW 표시(빗썸, 업비트, 코인원)와 USDT 표시(Binance, Bybit). 이 이중 통화 아키텍처는 전체 데이터 흐름을 형성하는 근본적 제약 조건이다 — 모든 영역 간 스프레드 계산에는 실시간 KRW/USD 환율이 세 번째 입력으로 필요하다.

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

### 1.2 컴포넌트 책임

| 컴포넌트 | 책임 | 동시성 모델 |
|----------|------|------------|
| 거래소 커넥터 (5개) | 각 거래소와의 지속적 WS 연결 유지 | 거래소당 1개 asyncio Task |
| KRW/USD 환율 제공자 | 영역 간 스프레드를 위한 실시간 환율 공급 | 업비트 커넥터와 공유(Primary) + 폴링 Task 1개(Fallback) |
| WebSocket 연결 관리자 | 생명주기 관리, 재연결, 하트비트 스케줄링 | 커넥터 Task들을 조율 |
| 데이터 정규화기 | 거래소별 형식을 공통 `TickerUpdate` 스키마로 변환 | 각 커넥터 Task 내 인라인 실행 |
| Price Store | (거래소, 심볼) 쌍별 최신 가격 저장; DB로 write-through | 스레드 안전 dict (`asyncio.Lock` 불필요 — 단일 스레드 이벤트 루프) |
| 스프레드 계산기 | 모든 가격 업데이트마다 10개 거래소 쌍의 스프레드 계산 | Price Store 쓰기에 의해 트리거됨 |
| 알림 엔진 | 스프레드를 임계값 대비 확인; 쿨다운 관리; Telegram 전달 | 스프레드 계산기에 의해 트리거됨 |
| FastAPI REST API | 이력 데이터, 설정 CRUD, health 엔드포인트 | Uvicorn ASGI 서버 |
| WebSocket 서버 | 실시간 가격 및 스프레드를 연결된 대시보드에 푸시 | FastAPI WebSocket 엔드포인트 |
| 데이터베이스 계층 | 가격 스냅샷, 스프레드 이력, 알림 설정, 알림 로그 영속화 | SQLAlchemy async + aiosqlite |
| 프론트엔드 | 대시보드 렌더링, 차트, 사용자 설정 UI | React 19 + Vite 개발 서버 |

---

## 2. 데이터 플로우 파이프라인

### 2.1 종단 간 데이터 플로우

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

### 2.2 파이프라인 단계 상세

**1단계 — 원시 메시지 수신**

각 거래소 커넥터는 WebSocket 연결로부터 JSON 메시지를 수신한다. 메시지 형식은 거래소마다 근본적으로 다르다:

- **빗썸/업비트**: `trade_price` (숫자), `timestamp` (정수 ms)
- **코인원**: `last` (문자열), `timestamp` (정수 ms)
- **Binance**: `c` (문자열, 단일 문자 키), `E` (정수 ms)
- **Bybit**: `lastPrice` (문자열), `ts` (정수 ms)

[trace:step-1:data-format] 단계 1 리서치에 따르면, 코인원, Binance, Bybit은 숫자 값을 JSON 문자열로 반환하는 반면, 빗썸과 업비트는 네이티브 숫자로 반환한다. 정규화기는 두 경우 모두 처리해야 한다.

**2단계 — 정규화**

각 커넥터는 거래소별 메시지를 공통 `TickerUpdate` dataclass로 변환한다:

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

**`float` 대신 `Decimal`을 사용하는 이유**: 금융 가격 비교에는 정확한 산술 연산이 필요하다. `float`의 0.01 KRW 반올림 오차는 무시할 수 있지만, 처음부터 `Decimal`을 사용하면 부동소수점 표현 버그의 전체 부류를 원천 차단할 수 있으며 이는 금융 소프트웨어의 표준 관행이다. 이 처리량(전체 초당 ~25회 업데이트)에서 성능 비용은 무의미하다.

**3단계 — Price Store 업데이트**

Price Store는 `(exchange, symbol)` → `TickerUpdate`로 키가 지정된 딕셔너리다. 매 업데이트마다:

1. 인메모리 항목을 교체한다
2. 비동기 DB 쓰기를 큐에 추가한다 (틱마다가 아닌 배치 처리 — 섹션 8 참조)
3. 이 거래소+심볼이 포함된 모든 쌍에 대해 스프레드 계산기를 트리거한다

**4단계 — 스프레드 계산**

스프레드 계산기는 관련된 모든 쌍의 스프레드를 계산한다. BTC와 같은 심볼의 경우:
- KRW 대 USDT 3쌍: (빗썸, 업비트, 코인원) x (Binance, Bybit) = 6개 김치 프리미엄 쌍
- 동일 KRW 3쌍: 빗썸-업비트, 빗썸-코인원, 업비트-코인원
- 동일 USDT 1쌍: Binance-Bybit
- **합계: 심볼당 10쌍**

각 스프레드 결과에는 데이터 만료 플래그가 포함된다 (섹션 5 참조).

**5단계 — 알림 확인 및 출력**

- 사용자가 설정한 임계값을 초과하는 스프레드는 알림 엔진을 트리거한다
- 모든 스프레드 업데이트는 WebSocket을 통해 연결된 대시보드 클라이언트에 브로드캐스트된다
- 가격 및 스프레드 스냅샷은 주기적으로 SQLite에 기록된다

### 2.3 타이밍 특성

| 단계 | 예상 레이턴시 | 비고 |
|------|-------------|------|
| WS 수신 → 정규화 | < 1 ms | 프로세스 내 문자열 파싱 |
| 정규화 → Price Store | < 0.1 ms | Dict 할당 |
| Price Store → 스프레드 계산 | < 0.5 ms | 10쌍 × 산술 연산 |
| 스프레드 계산 → WS 브로드캐스트 | < 1 ms | asyncio 큐 → 전송 |
| 스프레드 계산 → 알림 확인 | < 0.5 ms | 임계값 비교 |
| 알림 → Telegram 전달 | 100-500 ms | Telegram API까지의 네트워크 왕복 |
| Price Store → DB 쓰기 | 5-50 ms | 배치 비동기 SQLite 쓰기 |

**종단 간 레이턴시** (거래소 WS → 대시보드 업데이트): **< 5 ms** (거래소 및 브라우저와의 네트워크 전송 시간 제외).

---

## 3. WebSocket 연결 관리

### 3.1 연결 상태 머신

각 거래소 커넥터는 결정론적 상태 머신을 따른다:

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

**상태:**

| 상태 | 설명 | 동작 |
|------|------|------|
| `DISCONNECTED` | 활성 연결 없음 | 연결 시도 시작 |
| `CONNECTING` | TCP + TLS + WS 핸드셰이크 진행 중 | 10초 타임아웃 |
| `CONNECTED` | 핸드셰이크 완료, 아직 구독 전 | 즉시 구독 메시지 전송 |
| `SUBSCRIBING` | 구독 메시지 전송됨, 확인 대기 중 | 확인까지 5초 타임아웃 |
| `ACTIVE` | 실시간 데이터 수신 중 | 메시지 처리, 하트비트 전송 |
| `WAIT_RETRY` | 다음 재연결 시도까지 백오프 기간 | 지수 백오프 타이머 실행 중 |

### 3.2 재연결 전략

**지터를 적용한 지수 백오프:**

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

| 시도 횟수 | 기본 지연 | 지터 적용 범위 |
|----------|----------|--------------|
| 0 | 1s | 0.75s - 1.25s |
| 1 | 2s | 1.5s - 2.5s |
| 2 | 4s | 3.0s - 5.0s |
| 3 | 8s | 6.0s - 10.0s |
| 4 | 16s | 12.0s - 20.0s |
| 5 | 32s | 24.0s - 40.0s |
| 6+ | 60s | 45.0s - 75.0s |

**재연결 성공 시**: 시도 카운터를 0으로 리셋한다.

**지터가 중요한 이유**: 서버가 다운되어 5개 커넥터가 동시에 연결 해제되면, 지터가 없을 경우 동일한 순간에 재연결을 시도하게 되어 IP 기반 요청 빈도 제한을 트리거할 수 있다(특히 빗썸의 10 연결/초 제한과 업비트의 5 연결/초 제한).

### 3.3 거래소별 하트비트 설정

[trace:step-1:heartbeat-requirements] 단계 1 리서치에서 거래소마다 상이한 하트비트 요구사항을 확인했다. 연결 관리자는 이를 개별적으로 처리해야 한다:

| 거래소 | 하트비트 메커니즘 | 간격 | 구현 |
|--------|----------------|------|------|
| **빗썸** | WebSocket 프로토콜 수준 ping/pong (암묵적) | 서버 주도 | 서버 ping에 자동 응답 (`websockets` 라이브러리가 처리) |
| **업비트** | 암묵적 (빗썸과 동일 — 공유 API 설계) | 서버 주도 | 빗썸과 동일 — `websockets`가 pong 응답 처리 |
| **코인원** | 애플리케이션 수준 JSON ping: `{"request_type": "PING"}` | 25초마다 | 전용 asyncio task가 PING 전송; 30분 유휴 타임아웃 |
| **Binance** | WebSocket 프로토콜 수준 ping/pong | 서버 주도 | `websockets` 자동 응답; 추가로 23.5시간마다 재연결 (24시간 만료 전) |
| **Bybit** | 애플리케이션 수준 JSON ping: `{"op": "ping"}` | 20초마다 | 전용 asyncio task가 ping 전송; pong 응답 모니터링 |

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

### 3.4 연결 관리자 설계

`ConnectionManager`는 5개 거래소 커넥터와 FX 환율 제공자의 전체 생명주기를 소유한다. 자식 Task들을 생성하는 최상위 asyncio Task로 실행된다:

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

### 3.5 거래소별 구독 메시지

| 거래소 | 구독 형식 | 다중 심볼 지원 |
|--------|----------|--------------|
| **빗썸** | `[{"ticket": "uuid"}, {"type": "ticker", "codes": ["KRW-BTC", ...], "isOnlyRealtime": true}, {"format": "DEFAULT"}]` | 가능 — 하나의 메시지에 코드 배열 |
| **업비트** | `[{"ticket": "uuid"}, {"type": "ticker", "codes": ["KRW-BTC", ...]}, {"format": "DEFAULT"}]` | 가능 — 빗썸과 동일 |
| **코인원** | `{"request_type": "SUBSCRIBE", "channel": "TICKER", "topic": {"quote_currency": "KRW", "target_currency": "BTC"}}` | 불가 — 심볼당 하나의 메시지 |
| **Binance** | `{"method": "SUBSCRIBE", "params": ["btcusdt@ticker", "ethusdt@ticker"], "id": 1}` | 가능 — 스트림 이름 배열 |
| **Bybit** | `{"op": "subscribe", "args": ["tickers.BTCUSDT", "tickers.ETHUSDT"]}` | 가능 — 토픽 문자열 배열 |

---

## 4. 데이터 정규화 계층

### 4.1 정규화 전략

각 커넥터는 거래소별 JSON을 공통 `TickerUpdate` 스키마로 변환하는 `normalize()` 메서드를 구현한다. 정규화기는 별도의 공유 모듈이 아닌 **각 커넥터 내부에 내장**되어 있다. 이를 통해 거래소별 파싱 로직이 연결 로직과 같은 위치에 배치되어, 각 커넥터가 자체 완결적 단위가 된다.

### 4.2 거래소별 정규화 매핑

| 필드 | 빗썸 | 업비트 | 코인원 | Binance WS | Bybit WS |
|------|------|--------|--------|------------|----------|
| `price` | `trade_price` (숫자) | `trade_price` (숫자) | `data.last` (문자열→Decimal) | `c` (문자열→Decimal) | `data.lastPrice` (문자열→Decimal) |
| `symbol` | `code` → `"KRW-"` 제거 | `code` → `"KRW-"` 제거 | `data.target_currency` | `s` → `"USDT"` 제거 | `data.symbol` → `"USDT"` 제거 |
| `currency` | `"KRW"` (하드코딩) | `"KRW"` (하드코딩) | `"KRW"` (하드코딩) | `"USDT"` (하드코딩) | `"USDT"` (하드코딩) |
| `volume_24h` | `acc_trade_volume_24h` | `acc_trade_volume_24h` | `data.target_volume` (문자열) | `v` (문자열) | `data.volume24h` (문자열) |
| `timestamp_ms` | `timestamp` | `timestamp` | `data.timestamp` | `E` | `ts` (최상위) |
| `bid_price` | 티커 스트림에 없음 | 티커 스트림에 없음 | `data.best_bids[0].price` | `b` (문자열) | 티커 스트림에 없음 |
| `ask_price` | 티커 스트림에 없음 | 티커 스트림에 없음 | `data.best_asks[0].price` | `a` (문자열) | 티커 스트림에 없음 |

### 4.3 심볼 정규화

거래소마다 서로 다른 마켓 코드 규칙을 사용한다. 정규화기는 정규(canonical) 기본 심볼을 추출한다:

```python
SYMBOL_EXTRACTORS = {
    "bithumb": lambda code: code.replace("KRW-", ""),        # "KRW-BTC" → "BTC"
    "upbit":   lambda code: code.replace("KRW-", ""),         # "KRW-BTC" → "BTC"
    "coinone": lambda tc: tc.upper(),                         # "BTC" → "BTC"
    "binance": lambda s: s.replace("USDT", ""),               # "BTCUSDT" → "BTC"
    "bybit":   lambda s: s.replace("USDT", ""),               # "BTCUSDT" → "BTC"
}
```

**추적 심볼** (설정 가능, 기본값):

```python
DEFAULT_SYMBOLS = ["BTC", "ETH", "XRP", "SOL", "DOGE"]
```

이 목록은 REST API를 통해 런타임에 설정 가능하며 데이터베이스에 저장된다.

### 4.4 코인원 이중 모드 처리

코인원은 다른 4개 거래소에 비해 WebSocket 안정성이 낮아 특별한 처리가 필요하다. 코인원 커넥터는 **이중 모드 접근 방식**을 구현한다:

1. **Primary**: `wss://stream.coinone.co.kr`에 대한 WebSocket 연결
2. **Fallback**: WebSocket이 30초 이상 다운된 경우 `GET /public/v2/ticker_new/KRW/{symbol}`에 대한 2초 간격 REST 폴링

Fallback은 자동으로 작동하며 WebSocket이 재연결되면 자동으로 해제된다:

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

## 5. 스프레드 계산 엔진

### 5.1 스프레드 유형

시스템은 두 가지 유형의 스프레드를 계산한다:

**유형 1 — 김치 프리미엄 (교차 통화)**

KRW 표시 가격과 USDT 표시 가격을 실시간 환율을 사용해 비교한다:

```
kimchi_premium_pct = ((krw_price / usd_krw_rate) / usdt_price - 1) × 100
```

- 양수 = KRW 거래소가 프리미엄에 거래됨 (전형적인 "김치 프리미엄")
- 음수 = KRW 거래소가 할인에 거래됨

**유형 2 — 동일 통화 스프레드**

동일 통화 영역 내에서 가격을 비교한다:

```
spread_pct = (price_a / price_b - 1) × 100
```

FX 환산이 필요 없다. 부호는 어느 거래소가 더 비싼지를 나타낸다.

### 5.2 전체 스프레드 매트릭스

각 추적 심볼에 대해 10개 거래소 쌍이 계산된다:

| # | 거래소 A | 거래소 B | 유형 | 통화 변환 |
|---|---------|---------|------|----------|
| 1 | 빗썸 (KRW) | Binance (USDT) | 김치 프리미엄 | FX 환율을 통해 KRW → USD |
| 2 | 빗썸 (KRW) | Bybit (USDT) | 김치 프리미엄 | FX 환율을 통해 KRW → USD |
| 3 | 업비트 (KRW) | Binance (USDT) | 김치 프리미엄 | FX 환율을 통해 KRW → USD |
| 4 | 업비트 (KRW) | Bybit (USDT) | 김치 프리미엄 | FX 환율을 통해 KRW → USD |
| 5 | 코인원 (KRW) | Binance (USDT) | 김치 프리미엄 | FX 환율을 통해 KRW → USD |
| 6 | 코인원 (KRW) | Bybit (USDT) | 김치 프리미엄 | FX 환율을 통해 KRW → USD |
| 7 | 빗썸 (KRW) | 업비트 (KRW) | 동일 통화 | 없음 |
| 8 | 빗썸 (KRW) | 코인원 (KRW) | 동일 통화 | 없음 |
| 9 | 업비트 (KRW) | 코인원 (KRW) | 동일 통화 | 없음 |
| 10 | Binance (USDT) | Bybit (USDT) | 동일 통화 | 없음 |

### 5.3 KRW/USD 환율 전략

**Primary 소스**: 업비트 `KRW-USDT` WebSocket 티커

업비트 커넥터는 이미 WebSocket 연결을 유지하고 있다. 암호화폐 심볼에 추가로 `KRW-USDT`를 구독함으로써, 추가 비용 없이 1초 미만의 KRW/USDT 환율을 얻을 수 있다. USDT는 USD에 밀접하게 연동되어 있으므로(일반적으로 ±0.1% 이내), 한국 트레이더들이 실제로 사용하는 환율을 반영하는 시장 파생 환율을 제공한다.

**Fallback 소스**: ExchangeRate-API REST 폴링

업비트 KRW-USDT 피드가 불가용한 경우(예: 업비트 커넥터 연결 해제), 시스템은 ExchangeRate-API로 폴백한다:

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

### 5.4 데이터 만료 감지

스프레드 계산은 모든 입력이 신선할 때만 유효하다. 시스템은 가격 입력당 **5초 데이터 만료 임계값**을 적용한다:

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

**만료된 스프레드의 동작**:
- 만료된 스프레드는 여전히 계산되어 표시된다 (대시보드에 시각적 표시기 포함)
- 만료된 스프레드는 알림을 트리거**하지 않는다** (캐시된 가격으로 인한 오탐 방지)
- 대시보드는 만료 사유를 표시한다 (예: "코인원 12초 전 연결 해제")

### 5.5 업데이트 트리거

스프레드 계산기는 **반응형**으로 실행된다 — 입력이 변경될 때마다 트리거된다:

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

## 6. 알림 엔진

### 6.1 알림 설정

사용자는 Telegram 봇 또는 REST API를 통해 알림을 설정한다. 설정은 SQLite에 저장된다:

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

### 6.2 알림 로직

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

### 6.3 쿨다운 메커니즘

쌍별 쿨다운은 알림 스팸을 방지한다. 핵심은 쿨다운이 `(chat_id, exchange_a, exchange_b, symbol)` 범위로 지정된다는 것이다 — 사용자는 쿨다운 기간당 쌍별로 최대 하나의 알림을 받는다:

```python
def _in_cooldown(self, pair_key: str, cooldown_minutes: int) -> bool:
    last_sent = self._cooldowns.get(pair_key)
    if last_sent is None:
        return False
    elapsed = time.time() - last_sent
    return elapsed < (cooldown_minutes * 60)
```

**기본 쿨다운**: 사용자별 쌍당 5분. 1~60분으로 설정 가능.

### 6.4 Telegram 메시지 형식

```
🔔 Kimchi Premium Alert

BTC: Bithumb vs Binance
Spread: +3.42% (threshold: ±3.00%)

Bithumb: ₩88,200,000 KRW
Binance: $65,000.15 USDT
FX Rate: ₩1,320.50/USD (Upbit USDT)

⏰ 2026-02-28 14:32:05 KST
```

동일 통화 스프레드의 경우:

```
🔔 Spread Alert

ETH: Upbit vs Bithumb
Spread: +1.85% (threshold: ±1.50%)

Upbit:   ₩4,320,000 KRW
Bithumb: ₩4,241,500 KRW

⏰ 2026-02-28 14:32:05 KST
```

### 6.5 Telegram 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 알림을 위한 채팅 등록 |
| `/status` | 모든 추적 심볼의 현재 스프레드 표시 |
| `/alert set BTC 3.0` | BTC에 대해 3% 김치 프리미엄 알림 설정 |
| `/alert list` | 활성 알림 설정 목록 |
| `/alert remove <id>` | 알림 제거 |
| `/exchanges` | 5개 거래소의 연결 상태 표시 |
| `/help` | 명령어 참조 |

### 6.6 알림 이력 로깅

전송된 모든 알림은 `alert_history` 테이블에 기록된다:

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

## 7. REST API 및 WebSocket 서버

### 7.1 FastAPI 애플리케이션 구조

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

### 7.2 REST API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/health` | Health 체크 + 거래소 연결 상태 |
| `GET` | `/api/v1/prices` | 모든 거래소 및 심볼의 현재 가격 |
| `GET` | `/api/v1/prices/{symbol}` | 전 거래소에 걸친 특정 심볼의 가격 |
| `GET` | `/api/v1/spreads` | 현재 스프레드 매트릭스 (전체 쌍) |
| `GET` | `/api/v1/spreads/history` | 이력 스프레드 데이터 (쿼리 파라미터: 심볼, 거래소 쌍, 시간 범위) |
| `GET` | `/api/v1/exchanges` | 거래소 연결 상태 및 메타데이터 |
| `GET` | `/api/v1/alerts` | 알림 설정 목록 |
| `POST` | `/api/v1/alerts` | 새 알림 설정 생성 |
| `PUT` | `/api/v1/alerts/{id}` | 알림 설정 수정 |
| `DELETE` | `/api/v1/alerts/{id}` | 알림 설정 삭제 |
| `GET` | `/api/v1/alerts/history` | 알림 이력 로그 |
| `GET` | `/api/v1/symbols` | 추적 심볼 목록 |
| `PUT` | `/api/v1/symbols` | 추적 심볼 목록 수정 |
| `GET` | `/api/v1/fx-rate` | 현재 KRW/USD 환율 및 소스 |

### 7.3 WebSocket 서버 (대시보드 푸시)

서버는 대시보드를 위한 단일 WebSocket 엔드포인트를 노출한다:

```
WS /api/v1/ws
```

**메시지 프로토콜** (서버 → 클라이언트, JSON):

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

**클라이언트 → 서버 메시지**:

```json
{
  "type": "subscribe",
  "symbols": ["BTC", "ETH"]
}
```

**브로드캐스트 패턴**: 서버는 연결된 대시보드 클라이언트의 집합을 관리한다. 매 스프레드 업데이트마다 브로드캐스트 task가 모든 클라이언트를 순회하며 업데이트를 전송한다. 연결이 끊어진 클라이언트는 집합에서 제거된다.

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

## 8. 데이터베이스 계층

### 8.1 스키마 설계

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

### 8.2 쓰기 전략

**문제**: 5개 거래소 x N개 심볼 x 각각 ~1 업데이트/초에서, 매 틱을 단순히 SQLite에 삽입하면 초당 ~25회 쓰기가 발생한다. SQLite WAL 모드는 이를 쉽게 처리하지만, 모든 틱을 저장하는 것은 이력 분석에 불필요하고 디스크 공간을 낭비한다.

**해결책 — 계층별 쓰기 전략**:

| 계층 | 데이터 | 쓰기 빈도 | 보존 기간 |
|------|--------|----------|----------|
| 인메모리 (Price Store) | (거래소, 심볼)별 최신 가격 | 매 틱 | 현재 값만 |
| `price_snapshots` 테이블 | 주기적 스냅샷 | 10초마다 (설정 가능) | 30일 |
| `spread_records` 테이블 | 스프레드 스냅샷 | 10초마다 | 30일 |
| `alert_history` 테이블 | 알림 이벤트 | 알림 전송마다 | 무기한 |
| `fx_rate_history` 테이블 | FX 환율 변경 | 환율 변경 시 (중복 제거) | 30일 |

10초 스냅샷 간격은 차트 렌더링에 충분한 세분성(분당 6개 데이터 포인트)을 확보하면서도 쓰기 볼륨을 ~2.5회/초로 줄인다.

**배치 라이터 구현**:

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

### 8.3 데이터 보존

일일 정리 작업이 보존 기간을 초과한 레코드를 제거한다:

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

### 8.4 SQLAlchemy 비동기 설정

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

### 8.5 TimescaleDB로의 마이그레이션 경로

SQLAlchemy ORM 계층을 통해, 연결 문자열 변경과 스키마 마이그레이션 추가만으로 향후 PostgreSQL/TimescaleDB로 전환할 수 있다:

```python
# SQLite (current)
engine = create_async_engine("sqlite+aiosqlite:///data/arbitrage.db")

# PostgreSQL + TimescaleDB (future)
engine = create_async_engine("postgresql+asyncpg://user:pass@host/arbitrage")
```

TimescaleDB 고유 기능(hypertable, 연속 집계, 압축)은 추가 SQL 마이그레이션이 필요하지만 Python 코드 변경은 필요 없다.

---

## 9. 프론트엔드 아키텍처

### 9.1 기술 스택

| 계층 | 기술 | 버전 | 용도 |
|------|------|------|------|
| 프레임워크 | React | 19 | 컴포넌트 렌더링, WS 업데이트 자동 배치 |
| 빌드 | Vite | 6 | 빠른 HMR, TypeScript 컴파일 |
| 언어 | TypeScript | 5 | 타입 안전성 |
| 상태 관리 | Zustand | 5 | WS 데이터를 위한 경량 스토어 |
| 스타일링 | Tailwind CSS | 4 | 유틸리티 우선 CSS |
| 차트 (금융) | TradingView Lightweight Charts | 5 | 가격 캔들스틱/라인 차트 |
| 차트 (분석) | Recharts | 2 | 스프레드 트렌드 라인, 바 차트 |

### 9.2 애플리케이션 구조

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

### 9.3 WebSocket 클라이언트 (프론트엔드)

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

### 9.5 대시보드 레이아웃

대시보드는 다음과 같은 레이아웃의 싱글 페이지 애플리케이션이다:

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

## 10. 프로젝트 디렉터리 구조

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

### 10.1 디렉터리 구조의 설계 근거

**백엔드 `app/` 구성**: 백엔드는 `connectors/` (데이터 수집), `core/` (비즈니스 로직), `models/` (영속화), `api/` (프레젠테이션)이 명확히 분리된 **계층 아키텍처**를 따른다. 이를 통해 각 계층을 독립적으로 테스트할 수 있다.

**`schemas/`를 `models/`와 분리하는 이유**: SQLAlchemy 모델은 데이터베이스 테이블 구조를 정의한다. Pydantic 스키마는 API 요청/응답 형태를 정의한다. 이 둘은 종종 겹치지만 관심사가 다르다(ORM 관계 vs. JSON 직렬화). 분리함으로써 API 계약이 데이터베이스 스키마에 결합되는 것을 방지한다.

**`shared/` 디렉터리가 없는 이유**: TypeScript 프론트엔드와 Python 백엔드는 런타임에 코드를 공유하지 않는다. API 계약은 Pydantic 스키마(OpenAPI 문서를 생성)로 정의되고 TypeScript `types/index.ts`에서 소비된다. 언어 간 코드 공유는 필요하지 않다.

---

## 11. 에러 복구 및 복원력

### 11.1 거래소 WebSocket 연결 해제

**시나리오**: 거래소 WebSocket 연결이 끊어짐 (네트워크 오류, 서버 점검, 요청 빈도 제한).

**복구**:

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

**거래소별 특수 처리**:

| 거래소 | 특수 복구 동작 |
|--------|--------------|
| 빗썸 | 점검 일정 확인; 알려진 점검 시간대에는 백오프를 2배로 적용 |
| 업비트 | HTTP 418 수신 시, `Retry-After` 헤더를 준수 (요청 빈도 제한 남용에 대한 연장 차단) |
| 코인원 | close code 4290이면, IP당 단일 연결 규칙 준수; 병렬 연결 시도 금지 |
| Binance | 24시간 강제 연결 해제를 피하기 위해 23시간 30분에 사전 재연결 예약 |
| Bybit | 5분당 500+ 연결이 트리거되면, 최소 백오프를 30초로 증가 |

### 11.2 KRW/USD 환율 데이터 만료

**시나리오**: 두 환율 소스(업비트 KRW-USDT와 ExchangeRate-API) 모두 불가용.

**복구**:

1. `stale_fx` 플래그와 함께 마지막으로 알려진 환율을 계속 사용
2. 만료된 FX 환율로 계산된 모든 김치 프리미엄 스프레드는 `is_stale = true`로 표시
3. 대시보드에 경고 배너 표시: "FX 환율 만료 (마지막 업데이트: X분 전)"
4. 만료된 FX 스프레드에 대해서는 알림 미발생
5. 어느 소스든 복구되면 정상 운영이 자동으로 재개

**허용 가능한 만료 범위**: KRW/USD는 하루에 ~0.1% 변동한다. 1시간 만료된 환율은 최대 ~0.004% 오차를 발생시킨다. 시스템은 최대 **1시간**의 FX 만료를 허용한 후 스프레드를 만료로 표시한다. 1시간을 초과하면 모든 교차 통화 스프레드에 플래그가 지정된다.

### 11.3 데이터베이스 쓰기 실패

**시나리오**: SQLite 쓰기 실패 (디스크 풀, 파일 잠금 타임아웃, 손상).

**복구**:

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

**핵심 원칙**: 데이터베이스 쓰기 실패는 실시간 파이프라인에 절대 영향을 미치지 않는다. 가격, 스프레드, 알림은 인메모리 상태에서 계속 기능한다. 이력 데이터 영속화만 저하된다.

### 11.4 Telegram API 장애

**시나리오**: Telegram Bot API가 오류를 반환하거나 도달 불가.

**복구**:

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

**동작**: 실패한 Telegram 전달은 `alert_history`에 `telegram_delivered = false`로 기록된다. 알림은 재큐에 넣지 않는다 (재시도가 소진될 때까지 스프레드 조건이 더 이상 유효하지 않을 수 있으므로). 사용자는 대시보드의 알림 이력에서 미전달 알림을 확인할 수 있다.

### 11.5 복원력 요약

| 장애 | 영향 | 복구 시간 | 데이터 손실 |
|------|------|----------|------------|
| 단일 거래소 WS 연결 해제 | 1개 거래소 만료; 해당 스프레드 플래그 표시 | 1-60초 (백오프) | 없음 (다른 거래소 계속 작동) |
| 전체 거래소 WS 연결 해제 | 모든 가격 만료; 알림 없음 | 거래소당 1-60초 | 없음 (인메모리 상태 보존) |
| FX 환율 불가용 | 교차 통화 스프레드 만료; 동일 통화 스프레드는 영향 없음 | 소스 복구 시 자동 | 없음 |
| SQLite 쓰기 실패 | 이력 데이터 미기록; 실시간 파이프라인 영향 없음 | 다음 배치 시도 (10초) | 최대 10K까지 버퍼링된 레코드 |
| Telegram API 장애 | 알림 기록되나 미전달 | 최대 4회 재시도, ~2분 | 알림이 DB에 미전달로 표시 |
| 프로세스 크래시 | 전체 재시작 필요 | ~5초 (Uvicorn 재시작) | 인메모리 가격 손실; DB는 무사 |

---

## 12. 배포 아키텍처

### 12.1 단일 서버 배포

이 프로젝트는 포트폴리오 프로젝트로서 단일 서버 배포를 위해 설계되었다. 전체 시스템이 하나의 머신(개발자 PC, VPS 또는 Docker 호스트)에서 실행된다:

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

### 12.2 환경 변수

모든 시크릿과 설정은 환경 변수로 관리된다:

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

### 12.3 Docker Compose (선택 사항)

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

**백엔드 Dockerfile** (개념적):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app/ app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**프론트엔드 Dockerfile** (개념적):

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

### 12.4 개발 워크플로우

```bash
# Terminal 1: Backend
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev  # Vite dev server on port 5173, proxies /api to :8000
```

`vite.config.ts`의 Vite 프록시 설정:

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

## 13. 설계 결정 및 트레이드오프

### DD-1: 단일 프로세스 vs. 다중 프로세스 아키텍처

**결정**: 모든 백엔드 컴포넌트에 단일 asyncio 프로세스 사용.

**고려된 대안**:
- 커넥터, 스프레드 엔진, API 서버를 별도 프로세스로 분리 (Redis pub/sub 사용)
- 메시지 큐잉을 이용한 워커 풀 (RabbitMQ/Redis)

**트레이드오프**: 단일 프로세스는 IPC 복잡성, shared-nothing 동기화 문제, Redis 의존성을 제거한다. 대가는 어떤 컴포넌트의 크래시든 전체 프로세스를 중단시킨다는 점이다. 5개 거래소를 모니터링하고 1-10명의 대시보드 사용자를 가진 포트폴리오 프로젝트에서 이것은 올바른 트레이드오프다. 시스템은 전체 초당 ~25개 메시지를 처리하며 — asyncio 용량에 비해 몇 자릿수 이하이다.

**마이그레이션 경로**: 시스템이 다중 프로세스 확장이 필요해지면, `PriceStore` 인터페이스와 `SpreadCalculator`의 구독 패턴이 이미 충분히 분리되어 있어 그 사이에 Redis pub/sub를 삽입할 수 있다.

### DD-2: 인메모리 Price Store vs. 데이터베이스 우선

**결정**: 인메모리 dict을 주 가격 저장소로, 데이터베이스는 보조 주기적 스냅샷으로 사용.

**근거**: 스프레드 계산기는 최신 가격에 밀리초 이하의 접근이 필요하다. 매 틱마다 SQLite에서 읽으면 읽기당 5-50ms의 레이턴시가 추가되고 불필요한 I/O가 발생한다. 인메모리 dict은 O(1) 접근을 제공한다. 데이터베이스 쓰기는 이력 분석 용도로만 10초 간격으로 배치 처리된다.

**리스크**: 프로세스 크래시 시 인메모리 가격이 손실된다. 거래소 WebSocket이 재연결 즉시 가격을 다시 공급하므로(활성 시장에서 일반적으로 1-2초 이내) 이는 수용 가능하다.

### DD-3: 가격 연산에 Decimal vs. Float

**결정**: 모든 가격 및 스프레드 계산에 `decimal.Decimal` 사용.

**트레이드오프**: `Decimal`은 산술 연산에서 `float`보다 ~10배 느리다. 초당 ~25회 업데이트에 각 10개 스프레드 계산이면, 초당 ~250회의 Decimal 연산에 해당한다 — 보통의 하드웨어에서도 아주 빠르다. 장점은 금융 비교에서 부동소수점 표현 오차를 제거하는 정확한 산술 연산이다.

### DD-4: 업비트 KRW-USDT를 Primary FX 환율로 사용

**결정**: 업비트의 `KRW-USDT` 티커(이미 WebSocket으로 구독 중)를 Primary KRW/USD 환율로, ExchangeRate-API를 Fallback으로 사용.

**트레이드오프**: USDT는 정확히 USD가 아니다 — Tether는 간혹 소폭의 프리미엄이나 디스카운트(±0.1%)로 거래된다. 그러나 업비트의 KRW-USDT 환율은 **한국 트레이더들이 실제로 경험하는 전환율**을 반영하므로, 공식 은행 환율보다 김치 프리미엄 계산에 더 정확하다. ExchangeRate-API Fallback은 업비트가 연결 해제될 경우의 안전망을 제공한다.

### DD-5: 거래소별 커넥터 vs. 통합 라이브러리 (ccxt)

**결정**: `websockets` 라이브러리를 사용한 5개의 수동 거래소별 커넥터.

[trace:step-2:websocket-client-recommendation] 단계 2 분석에서 `websockets 14.x`와 거래소별 커넥터가 더 많은 초기 코드를 대가로 재연결, 하트비트, 파싱에 대한 완전한 제어를 제공함을 확인했다. 대안(ccxt)은 코드를 줄이지만 거래소별 재연결 전략을 추상화하며 코인원 WebSocket을 지원하지 않는다.

**트레이드오프**: 더 많은 코드(커넥터당 ~200-300줄)를 작성해야 하지만 에러 처리, 하트비트 타이밍, 메시지 파싱에 대한 완전한 제어가 가능하다. 각 커넥터는 mock WebSocket 서버로 독립적으로 테스트할 수 있다.

### DD-6: 주기적 DB 스냅샷 vs. 매-틱 쓰기

**결정**: 매 틱이 아닌 10초마다 가격 및 스프레드 스냅샷을 SQLite에 기록.

**트레이드오프**: 10초 세분성은 데이터베이스가 10초 미만의 가격 움직임을 재구성할 수 없음을 의미한다. 모니터링 대시보드(트레이딩 봇이 아님)에서 이 세분성은 충분하다. 장점은 쓰기 볼륨을 ~25/초에서 ~2.5/초로 줄여 SQLite WAL 모드를 쾌적하게 유지하고 데이터베이스 파일 수명을 연장한다는 것이다.

### DD-7: Telegram 전용 알림 (브라우저 푸시나 이메일 없음)

**결정**: Telegram을 유일한 알림 전달 채널로 사용.

**근거**: Telegram은 한국 암호화폐 커뮤니티에서 지배적인 커뮤니케이션 플랫폼이다. 브라우저 푸시 알림은 서비스 워커와 HTTPS가 필요하다(로컬 개발에 복잡). 이메일 전달은 SMTP 설정이 필요하고 레이턴시가 높다. Telegram은 풍부한 포맷팅을 지원하는 간단한 `bot.send_message()` 호출로 즉각적이고 안정적인 전달을 제공한다.

### DD-8: SQLite WAL 모드 vs. PostgreSQL

**결정**: 초기 배포에 SQLite WAL 모드 사용; 아키텍처는 PostgreSQL 마이그레이션을 지원.

**트레이드오프**: SQLite는 제로 인프라(데이터베이스 서버 불필요)가 필요하며 단일 사용자 포트폴리오 프로젝트에 완벽하다. 제한은 단일 라이터 동시성 — 한 번에 하나의 쓰기 트랜잭션만 가능하다는 점이다. 10초마다 배치 쓰기를 하면 이것은 병목이 되지 않는다. SQLAlchemy async ORM 계층 덕분에 PostgreSQL/TimescaleDB로의 마이그레이션은 연결 문자열 변경과 스키마 마이그레이션만 필요하다.

### DD-9: Tailwind CSS 4 vs. 컴포넌트 라이브러리

**결정**: 미리 만들어진 컴포넌트 라이브러리(MUI, Ant Design) 대신 Tailwind CSS 4 유틸리티 클래스 사용.

**트레이드오프**: Tailwind는 더 많은 마크업 작성이 필요하지만 더 작은 번들 크기를 생산하고 컴포넌트 라이브러리의 "모든 앱이 똑같이 보이는" 문제를 피한다. 커스텀 스프레드 매트릭스 레이아웃과 차트 통합이 있는 대시보드에서, 유틸리티 우선 CSS는 의견이 강한 컴포넌트 라이브러리보다 더 많은 레이아웃 유연성을 제공한다.

### DD-10: 프론트엔드 상태 관리에 Zustand vs. Redux/Context

**결정**: 모든 프론트엔드 상태 관리에 Zustand 5 사용.

**근거**: Zustand 스토어는 React 컴포넌트 컨텍스트 없이 WebSocket 콜백에서 직접 업데이트할 수 있다. WebSocket `onmessage` 핸들러는 React의 렌더링 사이클 밖에서 실행되므로 이것은 매우 중요하다. Zustand의 `getState()` 메서드는 Redux의 `dispatch()` 패턴이 외부 이벤트 소스에 대해 제공할 수 없는 동기적 접근을 제공한다. 또한 스토어 크기가 ~1KB(Redux Toolkit의 ~12KB 대비)이다.

---

## 부록 A: 추적 심볼 지원 범위

모든 심볼이 5개 거래소 전부에 상장되어 있지는 않다. 시스템은 부분적 지원을 처리해야 한다:

| 심볼 | 빗썸 | 업비트 | 코인원 | Binance | Bybit |
|------|------|--------|--------|---------|-------|
| BTC | Yes | Yes | Yes | Yes | Yes |
| ETH | Yes | Yes | Yes | Yes | Yes |
| XRP | Yes | Yes | Yes | Yes | Yes |
| SOL | Yes | Yes | Yes | Yes | Yes |
| DOGE | Yes | Yes | Yes | Yes | Yes |

특정 거래소에 상장되지 않은 심볼의 경우, 해당 거래소-쌍 스프레드는 단순히 계산되지 않는다. 스프레드 매트릭스는 실제 데이터 가용성에 따라 동적으로 조정된다.

## 부록 B: 예상 리소스 요구사항

| 리소스 | 예상치 | 비고 |
|--------|--------|------|
| RAM | ~50-100 MB | Python 프로세스 + 인메모리 Price Store |
| CPU | 1코어의 < 5% | 산술 스프레드 계산은 미미 |
| 디스크 (DB) | ~500 MB/월 | 10초 스냅샷 간격, 30일 보존 기준 |
| 네트워크 (아웃바운드) | ~1 MB/시간 | 티커 데이터를 수신하는 5개 WS 연결 |
| 네트워크 (인바운드) | ~0.5 MB/시간 | 대시보드 WS 브로드캐스트 (1-10 클라이언트) |
| WS 연결 (아웃바운드) | 6개 지속 연결 | 5개 거래소 + 1개 Telegram 롱 폴링 |
| WS 연결 (인바운드) | 1-10 | 대시보드 클라이언트 |
