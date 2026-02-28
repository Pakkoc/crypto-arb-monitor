# Crypto Arbitrage Monitor

5개 한국 및 글로벌 거래소에서 BTC, ETH 가격을 실시간으로 추적하고, 교차 통화(KRW/USD) 김치 프리미엄 스프레드와 동일 통화 스프레드를 계산하며, 스프레드가 설정 가능한 임계값을 초과할 때 Telegram 알림을 전송하는 실시간 암호화폐 차익거래 모니터링 대시보드이다.

[trace:step-4:architecture-overview]

## 아키텍처 개요

이 시스템은 FastAPI + asyncio 기반의 **단일 프로세스 비동기 아키텍처**(DD-1)를 따른다. 모든 거래소 커넥터, 스프레드 계산기, 알림 엔진, WebSocket 브로드캐스트가 하나의 프로세스 안에서 동시 asyncio 태스크로 실행된다 — 외부 메시지 브로커나 워커 프로세스가 필요 없다.

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Server                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Exchange WebSocket Connectors                │   │
│  │  Bithumb · Upbit · Coinone · Binance · Bybit             │   │
│  │  (6-state FSM: IDLE→CONNECTING→CONNECTED→SUBSCRIBING     │   │
│  │   →STREAMING→RECONNECTING)                                │   │
│  └────────────────────────┬─────────────────────────────────┘   │
│                           │ TickerUpdate                        │
│                           ▼                                     │
│  ┌────────────────────────────────────────┐                     │
│  │            PriceStore                   │                     │
│  │  In-memory cache + 10s DB snapshots     │                     │
│  └────────┬───────────────┬───────────────┘                     │
│           │               │                                     │
│           ▼               ▼                                     │
│  ┌────────────────┐ ┌──────────────────┐                        │
│  │ SpreadCalculator│ │  WS Broadcaster  │──→ Dashboard clients   │
│  │  10 pairs × 2   │ │  (max 20)       │                        │
│  │  symbols        │ └──────────────────┘                        │
│  └────────┬───────┘                                             │
│           │                                                     │
│           ▼                                                     │
│  ┌────────────────┐    ┌──────────────┐                         │
│  │  AlertEngine    │───→│ Telegram Bot │                         │
│  │  3-tier severity│    │ (aiogram 3)  │                         │
│  └────────────────┘    └──────────────┘                         │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SQLite + WAL mode (aiosqlite)                            │   │
│  │  Tables: price_snapshots, spread_records, alert_configs,  │   │
│  │          alert_history, exchanges, tracked_symbols, ...   │   │
│  │  30-day retention policy                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite)                         │
│                                                                 │
│  WebSocket (/api/v1/ws) ←──→ Real-time prices, spreads, alerts  │
│  REST API  (/api/v1/*)  ←──→ CRUD alerts, history, health       │
│                                                                 │
│  Zustand stores · TanStack Query · Tailwind v4 · Recharts       │
└─────────────────────────────────────────────────────────────────┘
```

### 주요 설계 결정

| ID   | 결정 | 근거 |
|------|------|------|
| DD-1 | 단일 프로세스 asyncio | 최소한의 운영 복잡도; 5개 WS 피드 + 스프레드 계산이 하나의 이벤트 루프에 적합 |
| DD-2 | 공개 WebSocket 피드만 사용 | 가격 데이터에 API 키 불필요; 더 높은 요청 빈도 제한을 위해 선택적으로 키 사용 가능 |
| DD-3 | 6상태 커넥터 유한 상태 머신 | 지수 백오프를 통한 결정론적 재연결(1초 → 60초 상한) |
| DD-4 | 이중 통화 스프레드 매트릭스 | KRW 거래소 3곳 × USD 거래소 2곳 = 김치 프리미엄 6쌍 + 동일 통화 4쌍 |
| DD-5 | 3단계 알림 심각도 | INFO >= 1%, WARNING >= 2%, CRITICAL >= 3% (설정 가능) |
| DD-6 | SQLite WAL + 30일 데이터 보존 | 단일 라이터 비동기; 10초 간격 스냅샷 |

### 스프레드 계산

[trace:step-4:spread-formulas]

**김치 프리미엄** (교차 통화, KRW 대 USD):
```
spread_pct = (price_KRW / (price_USDT * fx_rate) - 1) * 100
```

**동일 통화 스프레드**:
```
spread_pct = (price_a / price_b - 1) * 100
```

환율(KRW/USD)은 Upbit의 USDT/KRW 티커에서 실시간으로 산출되며, Upbit 환율 데이터가 만료되면 ExchangeRate-API를 폴백으로 사용한다.

## 사전 요구 사항

- **Python** 3.12+ (pip 포함)
- **Node.js** 18+ (npm 포함)
- **Git**

외부 데이터베이스나 메시지 브로커가 필요 없다. SQLite를 영속화에 사용하며, 최초 실행 시 자동으로 생성된다.

## 설치

```bash
# Clone the repository
git clone https://github.com/your-username/crypto-arb-monitor.git
cd crypto-arb-monitor

# ── Backend ──────────────────────────────────────────────────────
cd src/backend

# Create and activate virtual environment
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env as needed (see Configuration section below)

# ── Frontend ─────────────────────────────────────────────────────
cd ../frontend
npm install
```

## 설정

모든 백엔드 설정은 환경 변수 또는 `src/backend/.env` 파일을 통해 관리된다. 전체 참조는 `src/backend/.env.example`을 확인한다.

### 필수 설정

없음. 애플리케이션은 별도 설정 없이 합리적인 기본값으로 실행된다. 모든 거래소 커넥터는 API 키가 필요 없는 **공개 WebSocket 피드**를 사용한다.

### 선택 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 서버 바인드 주소 |
| `PORT` | `8000` | 서버 포트 |
| `DEBUG` | `false` | 디버그 로깅 및 SQLAlchemy echo 활성화 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/arb_monitor.db` | 데이터베이스 연결 문자열 |
| `TELEGRAM_BOT_TOKEN` | _(비어 있음)_ | @BotFather에서 발급받은 Telegram Bot API 토큰; 비워두면 비활성화 |
| `EXCHANGERATE_API_KEY` | _(비어 있음)_ | KRW/USD 폴백용 ExchangeRate-API 키 |
| `INFO_THRESHOLD_PCT` | `1.0` | INFO 심각도 알림 임계값 (%) |
| `WARNING_THRESHOLD_PCT` | `2.0` | WARNING 심각도 알림 임계값 (%) |
| `CRITICAL_THRESHOLD_PCT` | `3.0` | CRITICAL 심각도 알림 임계값 (%) |
| `STALENESS_THRESHOLD_SECONDS` | `5` | 가격 데이터가 만료로 표시되기까지의 시간(초) |

거래소 API 키(`BITHUMB_API_KEY`, `UPBIT_ACCESS_KEY`, `BINANCE_API_KEY` 등)는 선택 사항이며, 더 높은 요청 빈도 제한이 적용되는 인증된 엔드포인트에서만 필요하다.

## 실행

### 개발 모드

```bash
# Terminal 1 — Backend (from src/backend/)
cd src/backend
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (from src/frontend/)
cd src/frontend
npm run dev
```

Vite 개발 서버는 `http://localhost:5173`에서 시작되며, 모든 `/api` 요청을 `http://localhost:8000`의 백엔드로 프록시한다.

### 프로덕션 빌드

```bash
# Build the frontend
cd src/frontend
npm run build
# Output is in src/frontend/dist/

# Run the backend (serve frontend static files separately or via reverse proxy)
cd src/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 사용 가이드

### 대시보드

브라우저에서 `http://localhost:5173`을 연다. 대시보드는 WebSocket을 통해 백엔드에 연결되어 다음 정보를 표시한다:

- **거래소 가격 카드** — 각 거래소의 실시간 BTC/ETH 가격과 매수/매도가, 거래량, 데이터 만료 표시
- **스프레드 매트릭스** — 10개 거래소 쌍의 스프레드가 실시간으로 갱신되며, 크기에 따라 색상 구분
- **거래소 상태 바** — 각 거래소의 연결 상태(STREAMING/RECONNECTING/DISCONNECTED)
- **환율** — 현재 KRW/USD 환율과 출처 표시

### 알림

알림 설정 페이지로 이동하여 Telegram 알림을 설정한다:

1. 스프레드 임계값 백분율을 설정한다 (예: 3.0%)
2. 방향을 선택한다: ABOVE (양의 스프레드만), BELOW (음의 스프레드), 또는 BOTH
3. 선택적으로 특정 심볼이나 거래소 쌍으로 필터링한다
4. 알림 과다 발송을 방지하기 위한 쿨다운 기간을 설정한다

알림은 세 단계의 심각도로 분류된다: INFO (>= 1%), WARNING (>= 2%), CRITICAL (>= 3%).

### Telegram 봇

`TELEGRAM_BOT_TOKEN`이 설정되어 있으면 봇은 다음을 지원한다:

- `/start` — 알림을 받을 채팅을 등록
- `/status` — 현재 거래소 연결 상태 및 최신 스프레드 확인

## API 레퍼런스

[trace:step-5:api-endpoints]

모든 REST 엔드포인트는 `/api/v1` 하위에 있다. WebSocket 엔드포인트는 `/api/v1/ws`이다.

### REST 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/health` | 서버 상태, 거래소 상태, DB 통계 |
| `GET` | `/api/v1/prices` | 모든 거래소의 현재 가격 |
| `GET` | `/api/v1/prices/{symbol}` | 특정 심볼의 가격 |
| `GET` | `/api/v1/prices/history` | 과거 가격 스냅샷 |
| `GET` | `/api/v1/spreads` | 현재 스프레드 매트릭스 |
| `GET` | `/api/v1/spreads/history` | 과거 스프레드 기록 |
| `GET` | `/api/v1/exchanges` | 거래소 연결 상태 |
| `GET` | `/api/v1/alerts` | 알림 설정 목록 |
| `POST` | `/api/v1/alerts` | 새 알림 규칙 생성 |
| `PUT` | `/api/v1/alerts/{id}` | 알림 규칙 수정 |
| `DELETE` | `/api/v1/alerts/{id}` | 알림 규칙 삭제 |
| `GET` | `/api/v1/alerts/{id}/history` | 알림 발동 이력 |
| `GET` | `/api/v1/symbols` | 추적 중인 심볼 |
| `GET` | `/api/v1/fx-rate` | 현재 환율 정보 |
| `GET` | `/api/v1/preferences` | 사용자 환경 설정 |
| `PUT` | `/api/v1/preferences` | 환경 설정 업데이트 |

### WebSocket 프로토콜

1. `/api/v1/ws`에 **연결**한다 (최대 동시 접속 20개)
2. 사용 가능한 심볼 및 거래소 정보가 포함된 `welcome` 메시지를 수신한다
3. 원하는 심볼과 채널(`prices`, `spreads`, `alerts`, `exchange_status`)로 `subscribe`를 전송한다
4. `subscribed` 확인 메시지를 수신한다
5. 현재 상태(전체 가격, 스프레드, 거래소 상태, 환율)가 포함된 `snapshot`을 수신한다
6. 실시간 `price_update` 및 `spread_update` 푸시를 수신한다
7. 알림 조건이 충족되면 `alert_triggered`를 수신한다
8. 30초마다 `heartbeat`를 수신하며, `pong`으로 응답한다

모든 숫자 값(가격, 스프레드, 임계값)은 정밀도 보존을 위해 **문자열**(Decimal-as-string)로 직렬화된다.

## 프로젝트 구조

```
crypto-arb-monitor/
├── src/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── main.py                 # FastAPI app + lifespan startup/shutdown
│   │   │   ├── config.py               # pydantic-settings configuration
│   │   │   ├── database.py             # SQLAlchemy async engine + session factory
│   │   │   ├── api/                    # REST API route handlers
│   │   │   │   ├── router.py           # Aggregates all sub-routers under /api/v1
│   │   │   │   ├── health.py           # GET /health
│   │   │   │   ├── prices.py           # Price endpoints
│   │   │   │   ├── spreads.py          # Spread endpoints
│   │   │   │   ├── alerts.py           # Alert CRUD + symbols/fx-rate/preferences
│   │   │   │   └── exchanges.py        # Exchange status endpoint
│   │   │   ├── connectors/             # Exchange WebSocket connectors
│   │   │   │   ├── base.py             # Abstract BaseConnector (6-state FSM)
│   │   │   │   ├── bithumb.py          # Bithumb WS connector
│   │   │   │   ├── upbit.py            # Upbit WS connector
│   │   │   │   ├── coinone.py          # Coinone WS connector
│   │   │   │   ├── binance.py          # Binance WS connector
│   │   │   │   └── bybit.py            # Bybit WS connector
│   │   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── schemas/                # Pydantic request/response schemas
│   │   │   ├── services/               # Business logic services
│   │   │   │   ├── exchange_manager.py # Manages all 5 connectors
│   │   │   │   ├── price_store.py      # In-memory price cache + DB snapshots
│   │   │   │   ├── spread_calculator.py# Spread computation engine
│   │   │   │   ├── alert_engine.py     # Alert evaluation + Telegram + WS
│   │   │   │   └── telegram_bot.py     # Telegram bot (aiogram 3)
│   │   │   ├── utils/
│   │   │   │   └── enums.py            # All enums + constants
│   │   │   └── ws/
│   │   │       └── handler.py          # WebSocket endpoint + ConnectionManager
│   │   ├── data/                       # SQLite database (auto-created)
│   │   ├── .env.example                # Environment variable reference
│   │   └── requirements.txt            # Python dependencies
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx                 # Root component with router
│       │   ├── main.tsx                # React entry point
│       │   ├── index.css               # Tailwind v4 dark theme
│       │   ├── components/             # Reusable UI components
│       │   │   ├── Dashboard.tsx       # Main dashboard layout
│       │   │   ├── SpreadMatrix.tsx    # Spread comparison matrix
│       │   │   ├── ExchangeStatusBar.tsx
│       │   │   └── ExchangePriceCard.tsx
│       │   ├── pages/                  # Route pages
│       │   │   ├── DashboardPage.tsx
│       │   │   └── AlertSettingsPage.tsx
│       │   ├── hooks/                  # Custom React hooks
│       │   │   ├── useWebSocket.ts     # WS connection + message dispatch
│       │   │   └── useAlerts.ts        # Alert CRUD (TanStack Query)
│       │   ├── stores/                 # Zustand state stores
│       │   │   ├── priceStore.ts       # Prices, spreads, FX, exchange status
│       │   │   └── alertStore.ts       # Alert configs + recent triggers
│       │   ├── lib/                    # Utilities
│       │   │   ├── api.ts              # Typed REST API client
│       │   │   └── format.ts           # Formatting helpers
│       │   └── types/                  # TypeScript type definitions
│       │       ├── index.ts            # All interfaces
│       │       └── enums.ts            # Enum constants (matches Python)
│       ├── package.json
│       ├── vite.config.ts              # Vite config with API proxy
│       └── tailwind.config.ts
└── tests/
    └── test_integration.py             # Integration test suite
```

## 기술 스택

### 백엔드
- **Python 3.11+** (asyncio)
- **FastAPI** — HTTP + WebSocket 서버
- **SQLAlchemy 2.0** — aiosqlite 기반 비동기 ORM
- **Pydantic v2** — 설정 + 스키마 유효성 검사
- **aiogram 3** — Telegram 봇 프레임워크
- **websockets** — 거래소 WebSocket 연결

### 프론트엔드
- **React 19** — UI 프레임워크
- **TypeScript 5.7** — 타입 안전성
- **Vite 6** — 빌드 도구 + 개발 서버
- **Tailwind CSS v4** — 유틸리티 우선 스타일링 (다크 테마)
- **Zustand 5** — 클라이언트 상태 관리
- **TanStack Query 5** — 서버 상태 + 캐싱
- **Recharts** — 가격/스프레드 이력 차트
- **Lightweight Charts 5** — TradingView 스타일 캔들스틱 차트

## 라이선스

이 프로젝트는 교육 및 포트폴리오 목적으로 제작되었다.
