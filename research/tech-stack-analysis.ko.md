# 기술 스택 분석 — 암호화폐 차익거래(Crypto Arbitrage) 모니터

**조사 날짜:** 2026-02-27
**범위:** 백엔드 프레임워크, 프론트엔드 프레임워크, 데이터베이스, Telegram 봇, KRW/USD 환율 API, 실시간 5개 거래소 암호화폐 차익거래 모니터 기존 프로젝트 분석
**목적:** 2단계 산출물 — 기술 스택 선정(3단계) 및 시스템 아키텍처 설계(4단계)의 기초 자료

---

## 요약 (Executive Summary)

이 시스템은 WebSocket을 통해 5개 거래소(Bithumb, Upbit, Coinone, Binance, Bybit)를 동시 모니터링하고, KRW/USD 환율을 적용한 스프레드를 계산하여 PC 웹 대시보드와 Telegram 알림으로 결과를 전달한다.

**권장 스택:**

| 레이어 | 권장 사항 | 근거 |
|-------|----------|------|
| 백엔드 | **FastAPI + asyncio** (Python 3.12) | 5개 WebSocket 동시 연결에 asyncio가 최적합; Python 생태계가 암호화폐 툴링(ccxt, cryptofeed)을 지배; 모든 백엔드 로직을 단일 언어로 구현 |
| 프론트엔드 | **React + Vite** | 차트 생태계 최강(TradingView Lightweight Charts); 최대 인재풀 및 라이브러리 생태계; Vite는 Next.js SSR 오버헤드 없이 빠른 개발 반복 제공 |
| 시계열 DB | **SQLite + WAL 모드** (선택적 TimescaleDB 마이그레이션 경로 포함) | 단일 사용자 포트폴리오 프로젝트에 제로 설정; WAL 모드로 동시 쓰기 처리; 규모 확장 시 TimescaleDB로 전환 |
| 알림 설정 DB | **SQLite** (동일 파일, 별도 테이블) | 관계형, 임베디드, 무운영(zero-ops); 사용자 설정 CRUD에 최적 |
| Telegram | **aiogram 3.x** | 네이티브 asyncio; 스레드풀 오버헤드 없음; FastAPI 이벤트 루프에 마찰 없이 통합 |
| KRW/USD 환율 | **ExchangeRate-API (무료 플랜)** + Upbit USD 폴백(fallback) | 신뢰성 높음, 오픈 접근 엔드포인트에 API 키 불필요, 시간당 업데이트로 스프레드 정규화에 충분 |
| 거래소 WS 클라이언트 | **websockets 14.x** (직접 구현, 거래소별) | 다중 거래소 정규화에서 ccxt보다 통제력 우수; 표준화가 통제력을 상회할 경우 ccxt.pro 유료 업그레이드 가능 |

**핵심 원칙:** 백엔드 전체에 Python async를 적용함으로써 스레드풀 복잡도를 제거한다. 5개 거래소 WebSocket 클라이언트, 스프레드 엔진, 알림 엔진, REST API 서버가 모두 동일한 asyncio 이벤트 루프에서 실행된다 — 프로세스 간 메시지 전달이 필요 없다.

---

## 1. 백엔드 프레임워크

### 1.1 평가 기준

이 시스템에서 백엔드 프레임워크 선정은 세 가지 제약 조건이 지배한다:

1. **동시성 모델**: 5개 이상의 장기 아웃바운드 WebSocket 연결(거래소 클라이언트)과 N개의 인바운드 WebSocket 연결(대시보드 클라이언트)을 1초 미만의 레이턴시(latency)로 동시에 유지해야 한다.
2. **생태계 적합성**: 거래소 API 클라이언트 라이브러리(ccxt, cryptofeed), Telegram 봇 라이브러리, 데이터 처리 라이브러리(pydantic, pandas)는 압도적으로 Python 우선이다. Node.js나 Go를 선택하면 이 생태계를 포기하게 된다.
3. **개발 속도**: 포트폴리오 프로젝트이므로 이 규모에서는 원시 처리량보다 유지보수성과 디버깅 용이성이 더 중요하다.

### 1.2 Python 옵션

#### 옵션 A: FastAPI + asyncio + Uvicorn

**버전 (2025-2026):** FastAPI 0.115.x, Uvicorn 0.32.x (Linux/macOS에서 uvloop 0.21.x 포함)

**아키텍처 적합성:**
FastAPI는 Starlette 기반의 ASGI 프레임워크다. 아웃바운드 WebSocket 클라이언트(거래소에 *연결*하는 측)와 인바운드 WebSocket 서버(대시보드에 *서비스*하는 측) 모두 동일한 asyncio 이벤트 루프에 공존할 수 있다. 각 거래소 커넥터는 asyncio Task로, 스프레드 엔진은 별도 Task로 실행되며, REST API와 WebSocket 서버는 Uvicorn이 서빙한다. 스레드 없음, 멀티프로세싱 없음, IPC 없음.

**WebSocket 처리:**
- 인바운드(대시보드): Starlette의 ASGI 레이어를 통한 네이티브 `WebSocket` 지원. 문서화된 벤치마크: DigitalOcean 드롭렛 단일 인스턴스에서 동시 WebSocket 연결 45,000개 이상. 브로드캐스트 시나리오(모든 대시보드 클라이언트에 가격 업데이트)의 경우, 공유 퍼블리셔와 클라이언트별 asyncio 큐를 사용하는 패턴을 적용한다.
- 아웃바운드(거래소 커넥터): `websockets` 라이브러리(또는 `aiohttp` WebSocket 클라이언트)를 동일 이벤트 루프 내 asyncio Task로 직접 실행한다.
- 실증 성능: 프로덕션 배포에서 Redis Pub/Sub 기반으로 초당 WebSocket 메시지 250,000건 처리. 이 프로젝트(5개 거래소, 대시보드 사용자 1-10명)에서는 인메모리 브로드캐스트로 충분하며 Redis가 필요 없다.

**장점:**
- 자동 OpenAPI/Swagger 문서 생성(5단계 API 설계에 유용)
- 서브밀리초 오버헤드의 요청/응답 유효성 검사를 위한 Pydantic v2
- 네이티브 async: 거래소 커넥터에 `asyncio.run_in_executor` 불필요
- 방대한 Python 생태계: `ccxt`(4,000+ 스타), `cryptofeed`(40개 이상 거래소 WebSocket 정규화), `pandas`, `pydantic`
- 활발한 커뮤니티: GitHub 스타 약 80,000개(가장 빠르게 성장하는 Python 웹 프레임워크)
- 전체적 타입 힌트 = IDE 지원 + 런타임 유효성 검사

**단점:**
- Python GIL이 CPU 집약 연산의 진정한 병렬성을 제한하나, 스프레드 계산은 CPU 집약적이지 않은 산술 연산이므로 문제 없음
- 동일 연결 수에서 Go보다 메모리 사용량이 약간 높음
- 컴파일 언어보다 콜드 스타트가 느리나 장기 실행 서비스에서는 무관

**결론:** 최적 선택. async 네이티브 아키텍처와 Python 생태계 정합성이 명확한 선택 근거를 제공한다.

---

#### 옵션 B: Django Channels

**버전 (2025-2026):** Django 5.x + Channels 4.x

**아키텍처 적합성:**
Django Channels는 Django의 HTTP/2 모델에 ASGI를 통한 WebSocket 지원을 확장한다. 채널 레이어(Redis 기반 또는 인메모리)를 사용해 컨슈머 간 메시지를 라우팅한다.

**장점:**
- Django ORM은 관계형 데이터에 대해 성숙하고 잘 문서화되어 있음
- 채널 레이어가 커스텀 코드 없이 내장 pub/sub 제공
- 엔터프라이즈 규모에서 수백만 동시 연결을 처리하는 실전 검증된 프레임워크

**단점:**
- 이 사용 사례에 과도: Django ORM, admin, 인증, 세션 미들웨어는 불필요한 복잡성
- 채널 레이어 아키텍처(인메모리도 포함)가 직접 asyncio 큐 대비 간접성을 추가
- 설정 복잡성: `CHANNEL_LAYERS` 설정, 컨슈머 라우팅, ASGI 애플리케이션 구성
- FastAPI보다 느린 시작 속도와 높은 기본 메모리 사용량
- Django의 동기 우선 ORM은 Channels와 함께 사용하더라도 명시적 `database_sync_to_async` 래퍼 필요
- 엔드포인트당 더 많은 보일러플레이트 코드

**결론:** 탈락. 단일 개발자 포트폴리오 프로젝트에 과도한 설계다. 채널 레이어 추상화는 이 규모에서 상응하는 이점 없이 복잡성만 추가한다.

---

#### 옵션 C: aiohttp (프레임워크로 사용)

**버전 (2025-2026):** aiohttp 3.11.x

**아키텍처 적합성:**
aiohttp는 HTTP 클라이언트와 서버 라이브러리를 겸하는 라이브러리다. FastAPI 등장 이전의 사실상 표준(de-facto) asyncio HTTP 라이브러리였다.

**장점:**
- 극도로 성숙한 WebSocket 클라이언트 구현 — 아웃바운드 연결에서 `websockets` 라이브러리보다 빠른 경우가 많음(인용된 벤치마크: aiohttp WebSocket 클라이언트가 처리량에서 `websockets`를 상회)
- HTTP 서버와 WebSocket 클라이언트 모두 단일 의존성으로 해결
- 연결 풀링에 대한 저수준 제어

**단점:**
- 자동 API 문서 없음(Pydantic 통합 없음, OpenAPI 없음)
- FastAPI 데코레이터 대비 더 장황한 요청/응답 처리
- 현대 Python 개발에서 FastAPI 대비 작은 생태계
- 기본적으로 낮은 타입 안전성
- 커뮤니티 모멘텀이 FastAPI로 이동; 2025년 기준 튜토리얼이 적음

**결론:** FastAPI 앱 내에서 WebSocket *클라이언트* 라이브러리로 유용하다(아웃바운드 거래소 연결용). 주요 서버 프레임워크로는 권장하지 않는다.

**하이브리드 참고:** 최적 아키텍처는 서버 프레임워크로 FastAPI를 사용하고, 아웃바운드 거래소 WebSocket 연결에 `aiohttp.ClientSession`(또는 `websockets` 라이브러리)을 사용하는 방식이다. 두 라이브러리 모두 동일한 이벤트 루프에서 공존한다.

---

### 1.3 Node.js 옵션

#### 옵션 D: NestJS

**버전 (2025-2026):** NestJS 10.x + `@nestjs/websockets` + Socket.IO 또는 ws 어댑터

**아키텍처 적합성:**
NestJS는 Angular에서 영감을 받은 모듈 시스템을 갖춘 독자적 Node.js 프레임워크다. `@WebSocketGateway` 데코레이터를 통해 WebSocket 지원이 일급 기능으로 제공된다.

**장점:**
- TypeScript 전면 적용; 완전한 타입 안전성
- Socket.IO 폴백을 갖춘 내장 WebSocket 게이트웨이(구형 브라우저 지원)
- 의존성 주입(DI)으로 대규모 코드베이스 테스트 가능
- 엔터프라이즈 백엔드 패턴에 강력한 생태계

**단점:**
- ccxt 동등성 없음: Node.js ccxt는 동작하지만 Python ccxt가 더 성숙한 async 지원과 더 많은 스타를 보유. 결정적 차이: Bithumb과 Coinone에 공식 Node.js SDK가 없으며 Python 라이브러리가 커뮤니티 표준임
- Node.js 단일 스레드 이벤트 루프는 I/O에 탁월하지만 CPU 집약 연산에서 Python과 동일한 한계; 5개 거래소 WebSocket 연결에서 의미 있는 차이 없음
- TypeScript는 컴파일 단계를 추가; 데이터 분석 툴(pandas, numpy) 필요 시 이중 언어 스택
- 포트폴리오 프로젝트에 과도한 모듈 시스템

**결론:** 탈락. 암호화폐 툴링(ccxt, cryptofeed, python-telegram-bot/aiogram, 스프레드 데이터 분석용 pandas)에서 Python 생태계 우위가 결정적이다. Node.js를 선택하면 Python에 이미 존재하는 거래소 특화 라이브러리를 재구현하거나 래핑해야 한다.

---

#### 옵션 E: Fastify

**버전 (2025-2026):** Fastify 5.x + `@fastify/websocket`

**장점:**
- 벤치마크에서 Node.js 최고 속도 HTTP 프레임워크(70,000+ req/s vs Express의 45,000)
- JSON 스키마 유효성 검사 내장
- 경량이며 확장 가능

**단점:**
- 암호화폐 특화 Python 라이브러리에서 NestJS와 동일한 생태계 격차
- WebSocket 지원이 플러그인 방식으로 제공되어 코어가 아닌 점에서 NestJS보다 통합성 낮음
- 최소한의 구조; NestJS 대비 아키텍처 결정을 더 많이 직접 해야 함

**결론:** NestJS와 동일한 Python 생태계 이유로 탈락. 순수 API 서비스라면 Fastify가 매력적이지만, Python 라이브러리가 결정적인 암호화폐 모니터에는 부적합하다.

---

### 1.4 Go 옵션

#### 옵션 F: Go + Gin/Fiber

**버전 (2025-2026):** Go 1.23, Gin 1.10.x / Fiber 3.x

**아키텍처 적합성:**
Go의 고루틴(goroutine)은 최소한의 메모리 공간(고루틴당 ~4KB vs Python asyncio Task 오버헤드)으로 동시 WebSocket 연결을 처리한다. Go는 서브밀리초 레이턴시가 필요한 프로덕션 HFT(고빈도 거래) 시스템에서 사용된다.

**장점:**
- 최고 원시 성능: Fiber가 벤치마크에서 300,000+ req/s 처리; 고루틴 동시성 모델은 5개 WebSocket 연결에 탁월
- 컴파일 바이너리: 즉각적인 콜드 스타트, 최소 메모리
- 연결별 네이티브 고루틴 패턴은 단순하고 강건
- 강력한 WebSocket 라이브러리: `gorilla/websocket`(GitHub 스타 19,000개)

**단점:**
- 결정적: Go에 성숙한 ccxt 동등품 없음. `go-ccxt` 포크가 존재하지만 불완전하고 비유지보수 상태. 거래소별 WebSocket 정규화를 처음부터 구현해야 함
- Go에 aiogram 동등품 없음; Telegram 봇 라이브러리(`telebot`, `telegram-bot-api`)가 Python 대응물보다 미성숙
- Go는 Python 지배적인 도메인을 대상으로 하는 포트폴리오 프로젝트에 적합한 언어가 아님
- 장황한 에러 처리, SQLAlchemy만큼 성숙한 제네릭 기반 ORM 없음

**결론:** 탈락. 성능 우위는 실재하지만 이 규모(5개 거래소 연결)에서는 무관하다. 누락된 생태계(ccxt 없음, cryptofeed 없음, aiogram 없음)가 상당한 구현 리스크를 초래한다.

---

### 1.5 백엔드 권장 사항

**FastAPI + asyncio + Uvicorn (Python 3.12)**

근거:
1. Python의 asyncio 모델은 스레드나 프로세스 없이 5개 동시 아웃바운드 WebSocket 연결과 N개 인바운드 연결을 처리한다
2. Python은 암호화폐 툴링의 공통 언어다: ccxt(200개 이상 거래소), cryptofeed(40개 이상 거래소 WebSocket 정규화), aiogram, pandas 모두 Python 우선
3. FastAPI의 Pydantic v2 통합으로 요청/응답 타입을 한 번 정의하면 API 문서와 공유된다
4. 문서화된 프로덕션 성능은 이 프로젝트 요구 사항을 몇 자릿수 이상 상회한다

---

## 2. 프론트엔드 프레임워크

### 2.1 평가 기준

1. **실시간 데이터 처리**: 거래소별 1-5Hz 속도로 WebSocket 메시지가 도착할 때 프레임워크가 얼마나 효율적으로 업데이트하는가?
2. **차트/그래프 라이브러리 가용성**: 금융 가격 차트, 스프레드 추세선, 다중 거래소 비교 뷰
3. **개발자 경험**: 실시간 데이터 상태 관리, TypeScript 지원, 빌드 툴링
4. **번들 크기**: 대시보드 로딩 시간에 영향

### 2.2 옵션 A: React + Vite (TypeScript)

**버전 (2025-2026):** React 19.x, Vite 6.x, TypeScript 5.x

**실시간 데이터 처리:**
React의 재조정기(reconciler)는 상태 업데이트를 일괄 처리한다. React 19는 모든 업데이트(비동기 콜백 및 WebSocket 이벤트 핸들러 내부 포함)에 대한 자동 일괄 처리를 도입했으며, 이는 고빈도 가격 업데이트에 이상적이다. 패턴은 다음과 같다: WebSocket 메시지 → `useState` 세터 → 일괄 리렌더링. 거래소 5개에서 초당 1-2 틱의 경우, React는 메모이제이션 없이도 이를 문제없이 처리한다.

**사용 가능한 차트 라이브러리:**
- **TradingView Lightweight Charts 5.x** (Apache 2.0): 금융 데이터 전용으로 설계됨. 수천 개의 바와 초당 여러 번의 실시간 틱 업데이트 처리. 네이티브 캔들스틱, 라인, 히스토그램. GitHub 스타 12,000개 이상. React 래퍼 제공.
- **Recharts 2.x**: D3 기반, React 컴포넌트 API. 스프레드 추세선 및 비OHLCV 차트에 적합.
- **Apache ECharts 5.x + echarts-for-react**: GPU 가속 Canvas/WebGL, 수백만 데이터 포인트 처리. 이 프로젝트에는 과도하지만 가격 히스토리가 커질 경우 탁월.
- **Victory, Nivo**: 잘 유지되는 대안 React 차트 라이브러리

**장점:**
- 최대 생태계: REST 데이터 페칭을 위한 `react-query`(TanStack Query), 경량 상태 관리를 위한 `zustand` 또는 `jotai`(이 사용 사례에서 Redux보다 우수), 라우팅을 위한 `react-router-dom`
- 최고의 차트 라이브러리 지원: TradingView Lightweight Charts에 React 전용 공식 튜토리얼과 래퍼 제공
- 프론트엔드 채용 공고의 52%(Stack Overflow 2024); 최대 인재풀
- TypeScript 통합이 성숙하고 잘 문서화됨
- Vite로 빠른 개발 반복을 위한 100ms 미만 HMR(Hot Module Replacement)
- SSR 오버헤드 없음(대시보드는 SEO 불필요; Vite SPA가 적합)

**단점:**
- 가상 DOM이 Svelte의 컴파일 방식 대비 런타임 오버헤드 추가(React 번들: 156KB vs Svelte 47KB)
- `useEffect` + WebSocket 설정에 신중한 클린업 필요(React에만 국한된 문제가 아니며 규율이 필요)
- 내장 상태 관리 없음 — zustand/jotai/redux 선택 필요(유연성 측면에서는 장점이지만 초보자에게는 단점)

**결론:** 권장. 차트 라이브러리 생태계(특히 TradingView Lightweight Charts)와 React 19의 WebSocket 업데이트 자동 일괄 처리가 대시보드 사용 사례에서 가장 강력한 선택이다.

---

### 2.3 옵션 B: Vue 3 + Vite (TypeScript)

**버전 (2025-2026):** Vue 3.5.x, Vite 6.x, Pinia 3.x (상태 관리)

**실시간 데이터 처리:**
Vue 3의 Composition API의 `ref()`와 리액티브 스토어(Pinia)는 라이브 데이터에 적합하다. Pinia 스토어는 WebSocket 이벤트 핸들러에서 직접 업데이트할 수 있다. 리액티비티 시스템이 세밀하게 작동하여 변경된 `ref`를 사용하는 컴포넌트만 리렌더링된다.

**사용 가능한 차트 라이브러리:**
- `vue-chartjs`(Chart.js의 Vue 래퍼): 유지보수되고 있으나 Chart.js는 SVG 기반으로 고빈도 업데이트에서 Canvas보다 느림
- `vue-echarts`(ECharts 래퍼): 뛰어난 성능
- TradingView Lightweight Charts: 공식 Vue 래퍼 없음; `onMounted`/`onUnmounted` 생명주기 훅으로 수동 통합 필요 — 보일러플레이트 증가

**장점:**
- Composition API가 실시간 데이터에 자연스럽게 맞음(리액티브 스토어, 계산된 속성)
- React보다 기본 번들 크기 작음
- Pinia는 Vue 팀이 공식 권장; 훌륭한 TypeScript 지원
- 좋은 문서

**단점:**
- React보다 작은 취업 시장(채용 공고 약 절반)
- TradingView Lightweight Charts에 공식 Vue 래퍼 없음 — 수동 캔버스 관리 필요
- `vue-chartjs`는 실시간 금융 데이터 성능에서 React + Lightweight Charts에 뒤처짐
- Vue 생태계의 npm 패키지 수가 React보다 적음

**결론:** 실행 가능하지만 권장하지 않음. TradingView Lightweight Charts의 공식 Vue 래퍼 부재는 금융 대시보드에서 의미 있는 마찰 요소다. React의 차트 생태계가 결정적 차별점이다.

---

### 2.4 옵션 C: Svelte 5 / SvelteKit

**버전 (2025-2026):** Svelte 5.x (Runes API), SvelteKit 2.x

**실시간 데이터 처리:**
Svelte 5의 Runes API(`$state`, `$derived`)는 리액티비티를 컴파일 단계에서 제거한다 — 가상 DOM 없음, 재조정기 오버헤드 없음. WebSocket 메시지가 `$state`를 직접 업데이트하여 정확한 DOM 변경을 유발한다. 고빈도 가격 업데이트에서 이론적으로 Svelte가 가장 효율적인 접근 방식이다.

**벤치마크:**
- 번들 크기: Svelte 5 런타임 47KB vs React 19의 156KB
- 초기 렌더링: Svelte 5가 벤치마크에서 React 19보다 60% 빠른 렌더링
- 실시간 대시보드 벤치마크(5,000행 테이블 + WebSocket + 차트): Svelte가 프레임 시간에서 React보다 ~30% 성능 우수

**사용 가능한 차트 라이브러리:**
- `svelte-lightweight-charts`(TradingView Lightweight Charts의 커뮤니티 래퍼): 존재하지만 공식이 아닌 커뮤니티 유지보수
- `layerchart`: D3 통합의 Svelte 네이티브 차트 라이브러리, 2024년 v1.0 출시
- `svelte-chartjs`를 통한 Chart.js: 동작하지만 SVG 성능 한계 동일

**장점:**
- 고빈도 DOM 업데이트에서 최고 원시 렌더링 성능
- 최소 번들 크기
- SvelteKit의 네이티브 WebSocket 지원이 2024년 도입(Node.js 어댑터 훅 통해)
- 스토어 시스템이 WebSocket 데이터 스트림과 자연스럽게 통합
- 진정으로 우아한 리액티브 문법 — React 훅보다 보일러플레이트 적음

**단점:**
- Svelte는 ~900개 채용 공고 vs React의 110,000개(Stack Overflow 2024) — 가장 작은 커뮤니티
- TradingView Lightweight Charts Vue/Svelte 래퍼는 커뮤니티 유지보수; React 래퍼는 공식 문서화
- 더 작은 npm 생태계 — admin/대시보드 UI용 사전 구축 UI 컴포넌트 라이브러리 적음
- SvelteKit WebSocket 지원은 신규이며 React + Vite 솔루션보다 실전 검증이 덜 됨
- 성능 우위는 실재하지만 사람이 인식하는 새로고침 속도에서 5개 거래소 데이터 5Hz 업데이트에는 감지 불가

**결론:** 포트폴리오 프로젝트에 권장하지 않음. 성능 우위는 실재하지만 5Hz 업데이트 빈도에 사용자 1-10명 환경에서는 무관하다. 더 작은 생태계와 커뮤니티 유지보수 차트 래퍼가 피할 수 있는 리스크를 초래한다.

---

### 2.5 프론트엔드 권장 사항

**React 19 + Vite 6 + TypeScript + TradingView Lightweight Charts**

상태 관리: **Zustand 5.x** (경량, 보일러플레이트 없음, WebSocket 콜백에서 직접 사용 가능)
차트 라이브러리: **TradingView Lightweight Charts 5.x** (주요) + **Recharts 2.x** (스프레드 히스토리)

---

## 3. 데이터베이스

### 3.1 요구 사항 분석

이 시스템은 두 가지 독립적인 저장 범주를 가진다:

| 범주 | 접근 패턴 | 용량 | 특성 |
|------|----------|------|------|
| 가격 스냅샷 / 스프레드 기록 | 쓰기: 5개 거래소 × N 틱/초; 읽기: 차트용 히스토리 조회 | 거래소당 1Hz에서 분당 ~500행 | 시계열; 추가 전용 쓰기; 시간 범위 쿼리 |
| 알림 설정 / 사용자 설정 | 사용자 액션 시 읽기/쓰기 | ~10-100행 | 관계형; 낮은 용량; CRUD |

### 3.2 옵션 A: SQLite (WAL 모드)

**버전:** SQLite 3.47.x (`sqlite3` 표준 라이브러리로 Python에 번들 포함)

**시계열 적합성:**
WAL(Write-Ahead Logging) 모드의 SQLite는 단일 쓰기 작업이 행을 추가하는 동안 동시 읽기를 지원한다. 거래소 5개에서 각 1Hz(분당 300행)의 경우, SQLite WAL 모드가 쓰기 속도를 충분히 처리한다.

**벤치마크 참고:** SQLite는 파일당 하루 ~100,000회 미만의 쓰기 처리량을 "적절한 사용 사례"로 공식 문서화하고 있다 — 이 프로젝트는 5개 거래소 1Hz 기준 최대 하루 ~432,000행을 생성하여 한계에 근접하지만 초과하지는 않는다. 5분 캔들 집계 테이블(암호화폐 시스템에서 일반적)을 사용하면 실제 행 수는 5 × 288 캔들/일 = 1,440행/일로 한계 내에 충분히 들어온다.

**장점:**
- 제로 설정: 파일 기반, 서버 프로세스 없음, 파일 경로 이외의 연결 문자열 없음
- `sqlite3`는 Python 표준 라이브러리 — 기본 사용에 추가 의존성 없음
- `aiosqlite`로 이벤트 루프를 차단하지 않는 async SQLite 접근 제공
- 단일 파일: 백업, 버전 관리, 이전이 용이
- 뛰어난 Python 생태계: SQLAlchemy 2.x async가 SQLite 지원; 마이그레이션을 위한 `alembic`
- 스프레드 이동 평균에 유용한 윈도우 함수를 포함한 완전한 SQL 지원

**단점:**
- 네이티브 시계열 압축 또는 연속 집계 없음(TimescaleDB와 달리)
- 쓰기 잠금이 데이터베이스 파일 단위(WAL 모드가 완화하지만 완전히 제거하지는 않음)
- 다중 프로세스 배포로 확장 시 부적합
- 내장 데이터 보존 정책 없음(수동 정리 구현 필요)

**결론:** 이 프로젝트 범위에 권장. 포트폴리오 프로젝트에서 단순성 장점이 결정적이다.

---

### 3.3 옵션 B: PostgreSQL + TimescaleDB

**버전 (2025-2026):** PostgreSQL 17.x + TimescaleDB 2.17.x

**시계열 적합성:**
TimescaleDB의 `hypertable` 기능은 시계열 데이터를 시간 간격별로 자동 파티셔닝한다. 연속 집계가 OHLCV 캔들을 미리 계산한다. 압축으로 과거 가격 데이터 저장 공간이 90% 이상 감소한다.

**벤치마크 비교 (ClickHouse vs TimescaleDB vs InfluxDB, 2025):**
TimescaleDB는 복잡한 쿼리에서 InfluxDB를 크게 상회한다(수초 vs 수십 초의 차이). 쓰기 집중 수집에서는 InfluxDB가 더 빠르고, 복잡한 쿼리 성능에서는 TimescaleDB가 우수하다.

**장점:**
- 완전한 SQL + 시계열 확장: `time_bucket()`, 연속 집계, 압축
- 암호화폐 거래소에서 실전 검증(실제 거래 플랫폼의 틱 캡처에 사용됨)
- 필요 시 수평 확장
- `asyncpg`로 고성능 async PostgreSQL 클라이언트 제공

**단점:**
- 실행 중인 PostgreSQL 서버 필요: Docker 또는 네이티브 설치
- 단일 사용자 포트폴리오 프로젝트에 상당한 운영 오버헤드
- TimescaleDB 확장은 PostgreSQL을 요구 — 의존성 체인 추가
- SQLAlchemy + TimescaleDB는 ORM을 우회하는 Timescale 특화 쿼리 구문 필요

**결론:** 프로젝트 확장 시 마이그레이션 대상. 초기 개발에 권장하지 않음. 아키텍처는 SQLAlchemy ORM 레이어를 사용해야 하므로 SQLite에서 PostgreSQL/TimescaleDB로 전환 시 연결 문자열 변경과 스키마 마이그레이션만 필요하다.

---

### 3.4 옵션 C: InfluxDB

**버전 (2025-2026):** InfluxDB 3.x (Cloud-Native, OSS)

**시계열 적합성:**
InfluxDB는 시계열 메트릭 전용으로 설계되었다. 쓰기 처리량이 최고 수준이다. Flux 쿼리 언어는 시계열 변환에 강력하다.

**장점:**
- 추가 전용 시계열 데이터에서 최고 쓰기 처리량
- 내장 데이터 보존 정책(버킷별 TTL)
- 수치 시계열 네이티브 압축
- 대시보드를 위한 네이티브 Grafana 통합(커스텀 프론트엔드 대신 Grafana 사용 시)

**단점:**
- Line Protocol 쓰기 문법이 비표준; `influxdb-client-python` 라이브러리 필요
- 알림 설정을 위한 관계형 테이블 없음 — 사용자 설정을 위한 두 번째 데이터베이스(PostgreSQL 또는 SQLite) 필요
- Flux 쿼리 언어는 가파른 학습 곡선을 가지며 v3에서 InfluxQL로 대체 중
- 5개 거래소 모니터링에 과도한 설계
- InfluxDB v3이 클라우드 네이티브 아키텍처로 이동; OSS 버전은 기능 축소

**결론:** 탈락. 관계형 데이터(알림 설정)를 위한 두 번째 데이터베이스 요구 사항이 InfluxDB를 어색한 선택으로 만든다. SQLite는 시계열과 관계형 데이터를 하나의 파일에서 모두 처리한다.

---

### 3.5 옵션 D: Redis

**역할:** 캐싱 / Pub/Sub, 주 스토리지 아님

Redis는 이 프로젝트의 주 데이터베이스가 아니지만 특정 역할이 있다: 백엔드가 여러 FastAPI 워커로 확장되는 경우, Redis Pub/Sub가 워커 간 WebSocket 가격 업데이트 브로드캐스트 채널을 제공한다. 단일 워커 배포(이 포트폴리오 프로젝트에서 예상되는 경우)에서는 인메모리 asyncio 큐로 충분하며 Redis는 불필요한 오버헤드다.

**결론:** 선택적 인프라. 미래 확장 경로로 아키텍처에 포함하되, 초기 배포에는 필요하지 않다.

---

### 3.6 데이터베이스 권장 사항

**SQLite 3.47+ WAL 모드** + SQLAlchemy 2.x async + aiosqlite

- **스키마**: `price_snapshots`, `spread_records`, `alert_configs`, `alert_history`, `exchanges`, `trading_pairs` 별도 테이블을 가진 단일 SQLite 파일
- **마이그레이션 전략**: 스키마 마이그레이션에 Alembic 사용
- **마이그레이션 경로**: SQLAlchemy ORM + asyncio 방언으로 PostgreSQL/TimescaleDB 전환 시 연결 문자열 변경만 필요

---

## 4. Telegram 봇 통합

### 4.1 라이브러리 비교

#### 옵션 A: aiogram 3.x

**버전 (2025-2026):** aiogram 3.25.x (Telegram Bot API 9.2 지원)

**아키텍처 적합성:**
aiogram은 처음부터 asyncio와 aiohttp 기반으로 구축되었다. 디스패처(`Dispatcher`)와 봇(`Bot`) 인스턴스가 FastAPI의 asyncio 이벤트 루프에 자연스럽게 통합된다. 스프레드 엔진의 알림 트리거가 `bot.send_message()`를 `await` 표현식으로 직접 호출할 수 있다.

**폴링 vs Webhook:**
- 폴링: `await dp.start_polling(bot)` — FastAPI와 동일한 이벤트 루프에서 롱 폴링(long-polling) 시작. 단순하지만 네트워크 연결이 하나 더 추가됨.
- Webhook: Telegram이 호출하는 FastAPI POST 엔드포인트에서 `await dp.feed_update(bot, update)` 호출. 공개 HTTPS URL 필요 — 터널(ngrok) 없이는 로컬 개발에 비실용적.

**장점:**
- 완전 async: `asyncio.run_in_executor` 래퍼 불필요
- 부하 하에서 낮은 레이턴시(v20 이전 python-telegram-bot의 동기 방식과 달리 논블로킹)
- 활발한 유지보수: Telegram Bot API 9.2 출시 수일 내 지원
- 다단계 봇 대화(/settings 플로우)를 위한 유한 상태 머신(FSM) 지원
- 로깅, 에러 처리를 위한 미들웨어 시스템

**단점:**
- 가파른 학습 곡선: asyncio 친숙도 전제
- 튜토리얼 측면에서 python-telegram-bot보다 작은 커뮤니티

---

#### 옵션 B: python-telegram-bot 21.x

**버전 (2025-2026):** python-telegram-bot 21.x

**아키텍처 적합성:**
python-telegram-bot은 v13까지 동기 방식이었으나 v20+에서 asyncio 기반으로 완전히 재구축되었다. v21은 2024년까지의 Telegram Bot API 기능을 지원한다.

**장점:**
- 더 큰 커뮤니티; Stack Overflow 답변과 튜토리얼이 더 많음
- 고수준 `Application` 클래스가 폴링 생명주기를 자동으로 처리
- 폴링과 webhook 모두 동등하게 지원

**단점:**
- asyncio 통합이 aiogram보다 덜 원활 — `Application.run_polling()`이 별도 스레드 컨텍스트에서 차단되어 FastAPI 이벤트 루프와 연결하려면 `asyncio.ensure_future()` 필요
- 단순한 발사 후 망각(fire-and-forget) 알림 전달에 약간 높은 오버헤드

---

#### 옵션 C: pyTelegramBotAPI (telebot) 4.x

**버전 (2025-2026):** pyTelegramBotAPI 4.x

**아키텍처 적합성:**
telebot은 기본적으로 동기 방식이며 `asyncio_helper` 모듈이 async 지원을 제공하지만 핵심 설계가 아니다.

**장점:**
- 가장 단순한 API: async 의례 없이 `bot.send_message(chat_id, text)`
- 프로토타이핑 가장 빠름

**단점:**
- 동기 호출이 `asyncio.run_in_executor`로 래핑하지 않으면 이벤트 루프를 차단
- 프로덕션 async 애플리케이션에 권장하지 않음

**결론:** async FastAPI 통합에 탈락.

---

### 4.2 폴링 vs Webhook 결정

| 방식 | 최적 상황 | 단점 |
|------|---------|------|
| 롱 폴링(Long Polling) | 개발; 공개 URL 불필요 | Telegram으로 추가 지속 HTTP 연결 하나 |
| Webhook | 공개 HTTPS 서버가 있는 프로덕션 | 도메인 + SSL 인증서 필요; 로컬 개발에 비실용적 |

**권장 사항:** 이 프로젝트에 롱 폴링. 시스템이 개발자의 PC(또는 도메인 없는 단순 VPS)에서 실행된다. 폴링은 ~하나의 HTTP/2 롱 폴 연결을 추가하며 5개 거래소 WebSocket 연결 옆에서는 무시할 수 있는 수준이다.

### 4.3 Telegram 권장 사항

FastAPI asyncio 라이프스팬에 통합된 롱 폴링 방식의 **aiogram 3.25.x**

통합 패턴:
```python
# FastAPI lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(dp.start_polling(bot))  # runs alongside FastAPI
    yield
    await bot.session.close()
```

---

## 5. KRW/USD 환율

### 5.1 요구 사항 분석

김치 프리미엄(Kimchi Premium) 계산에는 실시간 KRW/USD 환율이 필요하다:

```
kimchi_premium_pct = ((krw_price / krw_usd_rate) - usdt_price) / usdt_price × 100
```

필요 업데이트 빈도: 거래소 WebSocket 틱은 1-5초마다 도착한다. 환율은 천천히 변동한다(USD/KRW는 하루에 ~0.1% 변동). 정확한 프리미엄 계산에는 분당 1회 업데이트로 충분하다.

### 5.2 옵션 A: ExchangeRate-API (오픈 액세스)

**URL:** `https://open.er-api.com/v6/latest/USD`

**가격:** 무료, 오픈 액세스 엔드포인트에 API 키 불필요
**업데이트 빈도:** 일 1회(KRW/USD에 충분)
**신뢰성:** 문서화된 SLA: "dead simple and extremely reliable"
**요청 빈도 제한:** 오픈 액세스 시 24시간당 1회; 무료 등록 키 사용 시 시간당 1회

**장점:**
- 기본 사용에 API 키 불필요
- KRW 지원
- 간단한 JSON 응답: `{ "rates": { "KRW": 1370.5, ... } }`

**단점:**
- 오픈 액세스는 24시간당 1회 업데이트
- 무료 등록 키 사용 시: 시간당 1회

**결론:** 주요 소스. 무료 등록 키로 시간당 업데이트가 충분히 유용하다.

---

### 5.3 옵션 B: Fixer.io

**가격:** 무료 플랜 사용 가능; 무료 등급에서 월 100회 요청(심각하게 제한적)
**업데이트 빈도:** 유료 플랜에서 60초마다; 무료에서 하루 1회

**단점:**
- 무료 등급: 월 100회 요청 — 모니터링 서비스에는 지나치게 제한적
- 유용한 업데이트 빈도를 위해 유료 플랜 필요

**결론:** 무료 등급 제한으로 탈락.

---

### 5.4 옵션 C: Upbit USDT/KRW 실시간 환율

Upbit은 `KRW-USDT` 페어(USD에 연동된 테더)를 상장하고 있다. 실시간 현물 가격이 서브초 업데이트로 시장 파생 KRW/USD 환율을 제공한다 — 이미 이 시스템이 어차피 구축하는 Upbit WebSocket 연결에서 가져올 수 있다.

**장점:**
- 추가 API 호출 불필요
- 서브초 업데이트 빈도
- 한국 시장 참여자들이 실제로 사용하는 거래 환율 반영
- 무료

**단점:**
- USDT ≠ 정확한 USD(테더는 때때로 디페그(depeg) 발생); 소규모 프리미엄/디스카운트 유입
- USDT 페어의 Upbit 유동성에 의존

**결론:** 활성 모니터링 중 주요 환율 소스로 권장. Upbit USDT/KRW 피드 사용 불가 시 ExchangeRate-API를 폴백으로 사용.

---

### 5.5 옵션 D: Binance USDT/KRW (KRWUSDT 페어를 통해)

Binance는 대부분의 사용자에게 KRW 표시 페어를 상장하지 않는다. 해당 없음.

---

### 5.6 KRW/USD 권장 사항

**주요:** Upbit `KRW-USDT` WebSocket 틱(이미 연결됨; 추가 요청 없음)
**폴백:** 무료 등록 키로 ExchangeRate-API (`https://v6.exchangerate-api.com/v6/{KEY}/latest/USD`), 분당 1회 폴링

---

## 6. 거래소 WebSocket 클라이언트 라이브러리

### 6.1 옵션 A: websockets 14.x (직접 구현, 거래소별)

**버전 (2025-2026):** websockets 14.x

**아키텍처:**
각 거래소는 영구 WebSocket 연결을 가진 전용 asyncio Task를 갖는다. 거래소별 JSON 정규화는 각 커넥터 모듈에서 구현된다. 이를 통해 재연결 로직, 하트비트(Heartbeat) 처리, 추출할 정확한 데이터 필드에 대한 완전한 제어권을 갖는다.

**장점:**
- 메시지 파싱 및 정규화에 대한 완전한 제어
- 거래소별 재연결 전략을 독립적으로 튜닝 가능
- 라이선스 제약 없음(ccxt.pro WebSocket은 LGPL 라이선스, websockets는 BSD)
- 단순한 디버깅: 단일 라이브러리, 표준 asyncio 패턴
- websockets 14.x에는 고처리량 JSON 파싱 경로를 위한 C 확장 포함

**단점:**
- 거래소별 정규화를 수동으로 구현해야 함(5개 거래소별 커넥터)
- 초기에 작성해야 할 코드가 더 많음

**결론:** 이 프로젝트에 권장. 거래소별 정규화는 범위가 정해진 작업(5개 커넥터)이며, 재연결과 파싱에 대한 완전한 제어가 가치 있다.

---

### 6.2 옵션 B: cryptofeed 3.x

**버전:** cryptofeed ~3.x

**아키텍처:**
cryptofeed는 암호화폐 거래소 전용 WebSocket 데이터 피드 라이브러리다. `FeedHandler` 객체가 여러 거래소 연결을 관리하고 데이터를 표준 콜백으로 정규화한다.

**거래소 지원:** 40개 이상의 거래소 포함 Bithumb, Upbit, Binance, Bybit (2025년 기준 Coinone은 지원 목록에 없음)

**장점:**
- 커뮤니티가 사전 구축하고 유지보수하는 거래소 커넥터
- 정규화된 콜백: `async def ticker(t: Ticker, receipt_timestamp: float): ...`
- 재연결, 하트비트, 백프레셔(backpressure)를 자동으로 처리

**단점:**
- Coinone이 미지원 — 어차피 커스텀 커넥터 필요
- 라이브러리 오버헤드: FeedHandler가 자체 asyncio 루프에서 실행되어 `asyncio.gather` 또는 스레드 조율 필요
- 커스텀 메시지 처리에 유연성 낮음
- 커뮤니티 유지보수; 거래소 지원이 API 변경에 뒤처질 수 있음

**결론:** 5개 거래소 중 4개(Bithumb, Upbit, Binance, Bybit)에 실행 가능. Coinone이 커스텀 커넥터를 필요로 하므로 단독 솔루션으로는 불가능. Coinone 격차와 낮은 유연성으로 인해 주요 접근 방식으로 권장하지 않음.

---

### 6.3 옵션 C: ccxt.pro (유료 WebSocket API)

**버전 (2025-2026):** ccxt 4.4.x (기본, 무료); ccxt.pro (WebSocket, 2024년부터 ccxt에 포함 — 현재 가격 확인 필요)

**상태 (2025):** ccxt 문서는 WebSocket API가 이제 기본 ccxt 패키지에 포함되어 있다고 명시(이전에는 ccxt.pro가 유료 구독). 사용 전 현재 라이선스 확인 필요.

**거래소 지원:** 5개 거래소 모두 지원(Bithumb, Upbit, Coinone, Binance, Bybit)

**장점:**
- 단일 라이브러리로 5개 거래소 모두 지원
- `watch_ticker()`, `watch_order_book()` 메서드로 정규화된 데이터 제공
- Python 암호화폐 커뮤니티에서 광범위하게 사용됨

**단점:**
- 추상화 레이어가 거래소별 최적화를 제한
- 과거 가격 혼란(pro vs 무료)이 장기 유지보수 리스크를 만듦
- 재연결 전략에 대한 제어력 낮음

**결론:** 현재 버전에서 ccxt WebSocket이 무료로 확인되면 평가할 가치 있음. ccxt.pro WebSocket이 현재 무료라면, 4개 표준 거래소에 ccxt를 사용하고 Coinone을 수동으로 구현. 최종 결정은 현재 ccxt 문서를 기반으로 구현 시점에 내려야 한다.

---

### 6.4 WebSocket 클라이언트 권장 사항

**주요:** 거래소별 asyncio Task 커넥터를 사용하는 `websockets 14.x`

**근거:** 완전한 제어, BSD 라이선스, Coinone 지원 격차 없음, 그리고 구현 비용(5개 거래소 커넥터)은 1단계 API 조사에서 범위가 정해지고 충분히 이해된 작업이다.

---

## 7. 기존 프로젝트 분석

### 7.1 프로젝트 1: crypto-arbitrage-framework (hzjken)

**리포지토리:** `github.com/hzjken/crypto-arbitrage-framework`
**스택:** Python + ccxt + docplex (IBM CPLEX 솔버)
**아키텍처 패턴:** 세 컴포넌트 — PathOptimizer(LP 솔버) → AmtOptimizer → TradeExecutor(멀티스레드)
**WebSocket 접근 방식:** ccxt를 통한 REST 폴링; WebSocket 스트리밍 없음
**알림 메커니즘:** 없음; 실행 중심

**교훈:**
1. ccxt가 다중 거래소 포트폴리오 프로젝트에서 거래소 API 차이를 효과적으로 추상화
2. 거래 실행에 멀티스레딩 사용(여기서는 해당 없음 — 모니터링만)
3. WebSocket 없음 = 폴링 레이턴시; 이 설계는 서브초 레이턴시가 중요한 실시간 스프레드 모니터링에 부적합
4. 경로 최적화를 위한 선형 프로그래밍은 삼각 차익거래에는 영리하지만 단순 김치 프리미엄 모니터에는 과도하게 복잡

**추출된 아키텍처 패턴:** 거래소 추상화 레이어로서의 ccxt; 이 프로젝트가 커넥터를 수동으로 구현하더라도 중앙 집계자를 가진 거래소별 모듈형 커넥터가 올바른 패턴이다.

---

### 7.2 프로젝트 2: realtime_crypto_arbitrage_bot (ehgp)

**리포지토리:** `github.com/ehgp/realtime_crypto_arbitrage_bot`
**스택:** Python + ccxt + Redis/RabbitMQ(메시지 브로커) + Pandas/NumPy
**아키텍처 패턴:** 프로듀서 → 메시지 큐 → 컨슈머 패턴
**WebSocket 접근 방식:** ccxt WebSocket watch 메서드
**알림 메커니즘:** 설정 임계값과 알림 전달

**교훈:**
1. 거래소 커넥터와 스프레드 계산기 사이의 메시지 큐(Redis/RabbitMQ)는 복원력을 추가하지만 복잡성도 추가 — 5개 거래소 단일 사용자 모니터에서는 직접 asyncio 큐가 더 단순하고 충분
2. 스프레드 계산에 Pandas는 편리하지만 의존성 무게를 도입; 단순 산술(김치 프리미엄 = (KRW 가격 / 환율) - USDT 가격)에서는 순수 Python 산술이 더 빠르고 pandas import 오버헤드를 피함
3. ccxt WebSocket watch 메서드는 작동하지만 거래소별 재연결 전략을 추상화 — 거래소 API가 변경될 때 우려 사항
4. 프로듀서(거래소 커넥터) → 공유 상태 → 컨슈머(스프레드 계산기)의 아키텍처가 정확히 맞다. 공유 상태가 메시지 큐인지 asyncio 큐인지는 규모에 따라 결정됨

**추출된 아키텍처 패턴:** 관심사 분리 — 거래소 데이터 수집, 정규화, 스프레드 계산, 알림 확인, 알림 전달이 별도 모듈이다. 이 모듈형 분리가 시스템을 테스트 가능하고 유지보수 가능하게 만든다.

---

### 7.3 프로젝트 3: albertoecf/crypto_arbitrage (엔터프라이즈 패턴)

**리포지토리:** `github.com/albertoecf/crypto_arbitrage`
**스택:** Python + ccxt + Kafka + Pandas
**아키텍처 패턴:** 엔터프라이즈 메시징 — market_data 큐 → arbitrage_detection → trade_orders 큐 → trade_execution
**WebSocket 접근 방식:** ccxt + Kafka 프로듀서

**교훈:**
1. Kafka는 고처리량 트레이딩 시스템에 가치 있지만 5개 거래소 모니터링 서비스에는 극도로 과도 — Docker/ZooKeeper/Kafka 운영 오버헤드 추가
2. 3단계 파이프라인 패턴(데이터 수집 → 분석 → 액션)은 올바르며 단순한 형태로 보존해야 한다: Kafka 대신 asyncio 큐, 동일한 논리적 분리
3. Python + ccxt가 이 도메인의 커뮤니티 표준 스택; 패턴이 프로젝트 후 프로젝트에 반복적으로 등장

**추출된 아키텍처 패턴:** 데이터 수집 → 분석 → 액션 파이프라인이 보편적이다. 이 프로젝트: 거래소 WebSocket Task → asyncio 내부 큐 → 스프레드 엔진 → 알림 엔진 → Telegram/WebSocket 브로드캐스트.

---

### 7.4 아키텍처 패턴 종합

분석된 모든 프로젝트에서 일관된 아키텍처가 도출된다:

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

REST API는 동일한 SQLite 스토리지 위에서 히스토리 데이터와 알림 설정 CRUD를 제공한다.

---

## 8. 최종 권장 스택

### 전체 스택

| 컴포넌트 | 기술 | 버전 | 근거 |
|---------|------|------|------|
| **언어** | Python | 3.12 | 생태계, asyncio 성숙도, 타입 힌트 |
| **백엔드 프레임워크** | FastAPI | 0.115.x | Async 네이티브, OpenAPI 문서, Pydantic v2 |
| **ASGI 서버** | Uvicorn + uvloop | 0.32.x | 프로덕션 ASGI 서버; Linux에서 uvloop으로 2배 처리량 |
| **거래소 WS 클라이언트** | websockets | 14.x | BSD, 완전한 제어, asyncio 네이티브 |
| **HTTP 클라이언트** | httpx | 0.27.x | REST 스냅샷 + KRW 환율 폴링을 위한 async HTTP |
| **데이터 유효성 검사** | Pydantic | v2.x | 요청/응답 타입, 런타임 유효성 검사 |
| **ORM** | SQLAlchemy | 2.x (async) | Async ORM, SQLite→PostgreSQL 쉬운 마이그레이션 |
| **DB 마이그레이션** | Alembic | 1.14.x | 스키마 버전 관리 |
| **데이터베이스** | SQLite 3.47+ (WAL) | — | 제로 설정, 단일 사용자, 동시 읽기를 위한 WAL |
| **Async DB 클라이언트** | aiosqlite | 0.20.x | asyncio 이벤트 루프에서 논블로킹 SQLite |
| **Telegram 봇** | aiogram | 3.25.x | 네이티브 asyncio, Telegram Bot API 9.2 |
| **KRW/USD 환율** | Upbit USDT/KRW WS (주요) + ExchangeRate-API (폴백) | — | 기존 연결의 실시간 데이터 |
| **프론트엔드 프레임워크** | React | 19.x | 생태계, TradingView Lightweight Charts 지원 |
| **빌드 툴** | Vite | 6.x | 빠른 HMR, SPA(SSR 불필요) |
| **언어 (FE)** | TypeScript | 5.x | 타입 안전성, API 계약 공유 |
| **상태 관리** | Zustand | 5.x | 최소 보일러플레이트, WS 콜백에서 동작 |
| **차트 (가격)** | TradingView Lightweight Charts | 5.x | 금융 등급, 실시간 틱, Apache 2.0 |
| **차트 (스프레드)** | Recharts | 2.x | 스프레드 추세선, React 네이티브 API |
| **스타일링** | Tailwind CSS | 4.x | 유틸리티 우선, 최소 CSS 오버헤드 |
| **API 클라이언트 (FE)** | TanStack Query (React Query) | 5.x | 캐싱을 포함한 REST 데이터 페칭 |
| **린팅/포맷** | ESLint 9 + Prettier 3 (FE) / Ruff 0.8 (BE) | — | 코드 품질 |
| **테스팅 (BE)** | pytest + pytest-asyncio | — | Async 테스트 지원 |

### 의존성 요약 (백엔드, 주요 패키지)

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

### 의존성 요약 (프론트엔드, 주요 패키지)

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

## 9. 리스크 분석

| 리스크 | 발생 확률 | 영향 | 완화 방안 |
|--------|---------|------|----------|
| Bithumb API 변경(v1 마이그레이션) | 중간 | 높음 | 폴백 감지를 포함한 v1 API 기반으로 Bithumb 커넥터 구현 |
| Coinone WebSocket 불안정(구형 API) | 중간 | 중간 | WebSocket 저하 시 Coinone 폴링 폴백 |
| USDT 디페그(Upbit KRW/USDT 환율) | 낮음 | 중간 | USDT 1% 편차 임계값에서 ExchangeRate-API 폴백 |
| 높은 부하에서 SQLite 쓰기 잠금 | 낮음 | 낮음 | WAL 모드; 틱당 1회 쓰기로 처리량 제한 |
| aiogram/FastAPI 이벤트 루프 충돌 | 낮음 | 중간 | aiogram 초기화에 FastAPI lifespan 컨텍스트 사용 |
| ccxt WebSocket 라이선스 변경 | 낮음 | 낮음 | `websockets`를 직접 사용; ccxt는 선택적 개선 사항만 |

---

## 10. 출처

- FastAPI WebSocket 벤치마크: [blog.poespas.me](https://blog.poespas.me/posts/2025/03/05/fastapi-websockets-asynchronous-tasks/), [Medium (250k msg/s)](https://medium.com/@bhagyarana80/the-fastapi-stack-that-handled-250-000-websocket-messages-per-second-77c15339e31c)
- FastAPI 45k 동시 WebSocket: [Medium](https://medium.com/@ar.aldhafeeri11/part-1-fastapi-45k-concurrent-websocket-on-single-digitalocean-droplet-1e4fce4c5a64)
- 프레임워크 비교: [FastAPI vs NestJS](https://slashdot.org/software/comparison/FastAPI-vs-NestJS/)
- React vs Vue vs Svelte 2025: [jsgurujobs.com](https://jsgurujobs.com/blog/svelte-5-vs-react-19-vs-vue-4-the-2025-framework-war-nobody-expected-performance-benchmarks), [Medium](https://medium.com/@jessicajournal/react-vs-vue-vs-svelte-the-ultimate-2025-frontend-performance-comparison-5b5ce68614e2)
- Vite vs Next.js: [strapi.io](https://strapi.io/blog/vite-vs-nextjs-2025-developer-framework-comparison)
- TimescaleDB vs InfluxDB: [sanj.dev](https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison), [Timescale](https://www.timescale.com/blog/timescaledb-vs-influxdb-for-time-series-data-timescale-influx-sql-nosql-36489299877)
- aiogram vs python-telegram-bot: [restack.io](https://www.restack.io/p/best-telegram-bot-frameworks-ai-answer-python-telegram-bot-vs-aiogram-cat-ai), [piptrends.com](https://piptrends.com/compare/python-telegram-bot-vs-aiogram)
- ExchangeRate-API: [exchangerate-api.com](https://www.exchangerate-api.com/docs/free)
- cryptofeed 라이브러리: [github.com/bmoscon/cryptofeed](https://github.com/bmoscon/cryptofeed)
- ccxt 라이브러리: [github.com/ccxt/ccxt](https://github.com/ccxt/ccxt)
- websockets 라이브러리: [websockets.readthedocs.io](https://websockets.readthedocs.io/)
- SQLite vs PostgreSQL: [betterstack.com](https://betterstack.com/community/guides/databases/postgresql-vs-sqlite/), [sqlite.org](https://sqlite.org/whentouse.html)
- TradingView Lightweight Charts: [tradingview.github.io/lightweight-charts](https://tradingview.github.io/lightweight-charts/)
- 기존 프로젝트: [hzjken/crypto-arbitrage-framework](https://github.com/hzjken/crypto-arbitrage-framework), [albertoecf/crypto_arbitrage](https://github.com/albertoecf/crypto_arbitrage), [ehgp/realtime_crypto_arbitrage_bot](https://ehgp.github.io/realtime_crypto_arbitrage_bot/getting_started.html)
- Go 프레임워크 비교: [buanacoding.com](https://www.buanacoding.com/2025/09/fiber-vs-gin-vs-echo-golang-framework-comparison-2025.html)
- Redis WebSocket 확장: [itnext.io](https://itnext.io/scalable-real-time-apps-with-python-and-redis-exploring-asyncio-fastapi-and-pub-sub-79b56a9d2b94)
