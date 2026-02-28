# 거래소 API 분석 — 암호화폐 차익거래 모니터

**조사 일자:** 2026-02-27
**범위:** 5개 거래소(Bithumb, Upbit, Coinone, Binance, Bybit)의 실시간 가격 데이터 수집
**목적:** Step 1 산출물 — 시스템 아키텍처 및 커넥터 구현의 기반

---

## 요약(Executive Summary)

이 문서는 5개 대상 거래소 전체를 상세히 다룬다. KRW로 가격을 표시하는 국내 거래소 3곳(Bithumb, Upbit, Coinone)과 USDT로 가격을 표시하는 해외 거래소 2곳(Binance, Bybit)이다. 핵심 아키텍처 과제는 국내·해외 가격이 서로 다른 통화로 표시된다는 점으로, 의미 있는 스프레드 비교를 위해서는 실시간 KRW/USD 환율을 세 번째 데이터 소스로 확보해야 한다.

**주요 발견 사항:**

1. **5개 거래소 모두 무료 공개 WebSocket 스트림을 제공한다** — 티커(ticker) 및 호가창(orderbook) 데이터에 API 키가 필요 없다. 레이턴시(latency)와 요청 빈도 제한(rate limit) 측면에서 REST 폴링보다 WebSocket이 강력히 권장된다.
2. **Bithumb은 중요한 API 전환을 거쳤다.** 레거시 REST/WebSocket API(`api.bithumb.com/public/`, `pubwss.bithumb.com`)는 여전히 운영 중이지만, 현재 공식 API는 REST에서 `/v1/` 경로 접두사를, WebSocket에서는 `wss://ws-api.bithumb.com/websocket/v1`을 사용한다. 신규 엔드포인트는 Upbit와 동일한 마켓 코드 형식(`KRW-BTC`)을 사용하며, 이는 통합 설계를 시사한다.
3. **Upbit와 Bithumb v2는 거의 동일한 REST 응답 스키마를 공유한다.** 두 거래소 모두 `trade_price`, `acc_trade_volume`, `timestamp`와 `KRW-BTC` 마켓 코드 관례를 사용하므로 정규화가 단순해진다.
4. **Coinone은 별도의 REST API를 사용한다.** `api.coinone.co.kr/public/v2/`에서 snake_case 필드명과 경로 파라미터로 `quote_currency`/`target_currency`를 구분하는 방식이다.
5. **Binance의 WebSocket은 스트림 프로토콜에서 단일 문자 약식 필드명을 사용한다** (`c`, `h`, `l`, `v` 등). REST API는 전체 영문 필드명을 사용한다. 파서는 두 스키마를 모두 처리해야 한다.
6. **Bybit는 5개 거래소 중 가장 높은 빈도인 50ms 단위로 스팟 티커 스트림을 제공하며,** WebSocket 활동은 REST 요청 빈도 제한에 포함되지 않는다.
7. **KRW/USD 환율 변환**에는 ExchangeRate-API(공개 접근)와 Binance가 제공하는 USDTKRW 가격이 모두 유효한 선택지이며, 각각 서로 다른 트레이드오프가 있다(섹션 8에서 논의).

---

## 1. Bithumb

**유형:** 국내 거래소
**기준 통화:** KRW
**마켓 코드 형식:** `KRW-BTC`, `KRW-ETH` 등

### 1.1 REST API 엔드포인트

**Base URL:** `https://api.bithumb.com`

> 참고: Bithumb은 두 개의 활성 API 인터페이스를 유지한다. 레거시 API는 `/public/` 경로 접두사와 `{SYMBOL}_{QUOTE}` 형식(예: `/public/ticker/BTC_KRW`)을 사용한다. 현재 API는 `/v1/` 경로 접두사와 마켓 코드(`KRW-BTC`)를 사용한다. 이 문서는 현재 `/v1/` API를 주요 구현 대상으로 삼으며, 레거시 경로는 관련 있는 경우에만 언급한다. Bithumb은 공식 문서에서 시맨틱 버전 레이블을 사용하지 않으며, `/v1/` 경로 접두사가 유일한 버전 식별자다.

#### 티커 엔드포인트 (현재 /v1/ API)

```
GET https://api.bithumb.com/v1/ticker
```

**쿼리 파라미터:**

| 파라미터  | 타입   | 필수 여부 | 설명                                              |
|-----------|--------|-----------|---------------------------------------------------|
| `markets` | string | Yes       | 쉼표 구분 마켓 코드 목록, 예: `KRW-BTC,KRW-ETH`  |

**요청 예시:**
```
GET https://api.bithumb.com/v1/ticker?markets=KRW-BTC
```

**응답 예시:**
```json
[
  {
    "market": "KRW-BTC",
    "trade_date": "20180418",
    "trade_time": "102340",
    "trade_date_kst": "20180418",
    "trade_time_kst": "192340",
    "trade_timestamp": 1524047020000,
    "opening_price": 8450000,
    "high_price": 8679000,
    "low_price": 8445000,
    "trade_price": 8621000,
    "prev_closing_price": 8450000,
    "change": "RISE",
    "change_price": 171000,
    "change_rate": 0.0202366864,
    "signed_change_price": 171000,
    "signed_change_rate": 0.0202366864,
    "trade_volume": 0.02467802,
    "acc_trade_price": 108024804862.58,
    "acc_trade_price_24h": 232702901371.09,
    "acc_trade_volume": 12603.53386105,
    "acc_trade_volume_24h": 27181.31137002,
    "highest_52_week_price": 28885000,
    "highest_52_week_date": "2018-01-06",
    "lowest_52_week_price": 4175000,
    "lowest_52_week_date": "2017-09-25",
    "timestamp": 1524047026072
  }
]
```

**핵심 가격 필드:** `trade_price` (정수, KRW)
**타임스탬프 필드:** `timestamp` (Unix ms)

#### 호가창 엔드포인트 (현재 /v1/ API)

```
GET https://api.bithumb.com/v1/orderbook
```

**쿼리 파라미터:**

| 파라미터  | 타입            | 필수 여부 | 설명                              |
|-----------|-----------------|-----------|-----------------------------------|
| `markets` | array of string | Yes       | 마켓 코드 목록, 예: `KRW-BTC`    |

**응답 예시:**
```json
[
  {
    "market": "KRW-BTC",
    "timestamp": 1529910247984,
    "total_ask_size": 8.83621228,
    "total_bid_size": 2.43976741,
    "orderbook_units": [
      {
        "ask_price": 6956000,
        "bid_price": 6954000,
        "ask_size": 0.24078656,
        "bid_size": 0.00718341
      }
    ]
  }
]
```

#### 마켓 코드 (현재 /v1/ API)

```
GET https://api.bithumb.com/v1/market/all
```

지원되는 모든 마켓 코드를 반환한다. 사용 가능한 KRW 거래쌍을 열거할 때 활용한다.

### 1.2 WebSocket 스트리밍

**WebSocket URL:** `wss://ws-api.bithumb.com/websocket/v1`
**프라이빗 URL:** `wss://ws-api.bithumb.com/websocket/v1/private`

#### 구독 메시지 형식

```json
[
  {
    "ticket": "unique-connection-id"
  },
  {
    "type": "ticker",
    "codes": ["KRW-BTC", "KRW-ETH"],
    "isOnlySnapshot": false,
    "isOnlyRealtime": true
  },
  {
    "format": "DEFAULT"
  }
]
```

**파라미터:**

| 필드              | 타입    | 설명                                                |
|-------------------|---------|-----------------------------------------------------|
| `ticket`          | string  | 이 연결의 고유 식별자                               |
| `type`            | string  | `ticker`, `trade`, 또는 `orderbook`                |
| `codes`           | array   | 마켓 코드 목록 (대문자 필수)                        |
| `isOnlySnapshot`  | boolean | true이면 초기 스냅샷만 수신                         |
| `isOnlyRealtime`  | boolean | true이면 실시간 업데이트만 수신                     |
| `format`          | string  | `DEFAULT` 또는 `SIMPLE`                             |

#### 티커 스트림 응답

```json
{
  "type": "ticker",
  "code": "KRW-BTC",
  "trade_price": 493100,
  "opening_price": 484500,
  "high_price": 493100,
  "low_price": 472500,
  "prev_closing_price": 484500,
  "change": "RISE",
  "change_price": 8600,
  "signed_change_price": 8600,
  "change_rate": 0.01775026,
  "trade_volume": 1.2567,
  "acc_trade_volume": 225.622,
  "timestamp": 1725927377931,
  "stream_type": "REALTIME"
}
```

**참고:** 레거시 WebSocket 엔드포인트 `wss://pubwss.bithumb.com/pub/ws`는 다른 구독 형식으로 여전히 운영 중이다:
```json
{"type": "ticker", "symbols": ["BTC_KRW"], "tickTypes": ["MID"]}
```
신규 구현에서는 이 엔드포인트 사용을 피해야 한다.

### 1.3 인증

| 엔드포인트 유형     | API 키 필요 여부 | 인증 방식                                               |
|---------------------|------------------|---------------------------------------------------------|
| 공개 REST           | 아니오           | 없음                                                    |
| 공개 WebSocket      | 아니오           | 없음                                                    |
| 프라이빗 REST       | 예               | HMAC-SHA512, `Api-Key`, `Api-Sign`, `Api-Nonce` 헤더 사용 |
| 프라이빗 WebSocket  | 예               | 연결 후 토큰 기반 인증                                  |

프라이빗 REST 인증 요구 사항:
- `Api-Key`: 발급된 API 키
- `Api-Sign`: 비밀 키로 `{endpoint}\0{body}\0{nonce}`를 HMAC-SHA512 서명한 값
- `Api-Nonce`: 현재 Unix 타임스탬프 (밀리초)

### 1.4 요청 빈도 제한

| 리소스                   | 제한                                                           |
|--------------------------|----------------------------------------------------------------|
| WebSocket 연결           | IP당 초당 10회 연결 요청                                       |
| WebSocket 메시지 (송신)  | 초당 5회, 분당 100회 (2025년 12월 기준)                        |
| REST API (공개)          | 명시적으로 공개되지 않음; 커뮤니티 보고에 따르면 초당 ~10회 전후로 쓰로틀링 발생 |
| REST 요청 빈도 제한 헤더 | `X-RateLimit-Remaining`, `X-RateLimit-Burst-Capacity`, `X-RateLimit-Replenish-Rate` |

**권고 사항:** 실시간 가격 데이터는 WebSocket을 사용하라. REST 폴링은 공개 엔드포인트 기준 초당 5회를 초과하지 않아야 한다.

### 1.5 데이터 형식

| 필드                    | 타입    | 설명                          |
|-------------------------|---------|-------------------------------|
| `market`                | string  | 마켓 코드 (`KRW-BTC`)         |
| `trade_price`           | number  | 최근 체결 가격 (KRW)          |
| `trade_volume`          | number  | 최근 거래량 (BTC)             |
| `timestamp`             | integer | Unix ms 타임스탬프            |
| `change`                | string  | `RISE`, `FALL`, 또는 `EVEN`  |
| `acc_trade_volume_24h`  | number  | 24시간 누적 거래량            |

### 1.6 알려진 한계

- **API 버전 분리:** Bithumb은 두 개의 서로 다른 API 인터페이스(레거시 `/public/`와 현재 `/v1/`)를 운영한다. 서드파티 라이브러리는 레거시 API를 대상으로 하는 경우가 많다. 라이브러리 사용 전 어느 API 인터페이스를 지원하는지 반드시 확인하라.
- **KRW 정수 가격:** 모든 KRW 가격은 정수로 반환된다(소수점 없음). BTC 수량 필드는 소수점 이하 최대 8자리까지 표현된다.
- **WebSocket 재연결:** 현재 `/v1/` WebSocket은 서버 측에서 자동 재연결 메커니즘을 구현하지 않는다. 클라이언트가 연결 끊김을 감지하고 재구독해야 한다.
- **점검 시간:** Bithumb은 월 1회 정도 점검을 예약한다. 점검 중 1~2시간 동안 서비스를 이용할 수 없을 수 있다.

---

## 2. Upbit

**유형:** 국내 거래소
**기준 통화:** KRW
**마켓 코드 형식:** `KRW-BTC`, `KRW-ETH` 등

### 2.1 REST API 엔드포인트

**Base URL:** `https://api.upbit.com` (국내)
**글로벌/지역별 URL:** `https://sg-api.upbit.com`, `https://id-api.upbit.com`, `https://th-api.upbit.com`

한국 시장 차익거래 모니터에는 `https://api.upbit.com`을 사용한다.

#### 티커 엔드포인트

```
GET https://api.upbit.com/v1/ticker
```

**쿼리 파라미터:**

| 파라미터  | 타입   | 필수 여부 | 설명                                                  |
|-----------|--------|-----------|-------------------------------------------------------|
| `markets` | string | Yes       | 쉼표 구분 마켓 코드 목록, 예: `KRW-BTC,KRW-ETH`      |

**요청 예시:**
```
GET https://api.upbit.com/v1/ticker?markets=KRW-BTC
```

**응답 예시:**
```json
[
  {
    "market": "KRW-BTC",
    "trade_date": "20180418",
    "trade_time": "102340",
    "trade_date_kst": "20180418",
    "trade_time_kst": "192340",
    "trade_timestamp": 1524047020000,
    "opening_price": 8200000,
    "high_price": 8679000,
    "low_price": 8100000,
    "trade_price": 8550000,
    "prev_closing_price": 8200000,
    "change": "RISE",
    "change_price": 350000,
    "change_rate": 0.04268292,
    "signed_change_price": 350000,
    "signed_change_rate": 0.04268292,
    "trade_volume": 0.12345678,
    "acc_trade_price": 150000000000.0,
    "acc_trade_price_24h": 300000000000.0,
    "acc_trade_volume": 18000.5,
    "acc_trade_volume_24h": 36000.1,
    "highest_52_week_price": 85000000,
    "highest_52_week_date": "2024-03-15",
    "lowest_52_week_price": 35000000,
    "lowest_52_week_date": "2023-09-11",
    "timestamp": 1524047026072
  }
]
```

**핵심 가격 필드:** `trade_price` (number, KRW)
**타임스탬프 필드:** `timestamp` (Unix ms) 및 `trade_timestamp` (정확한 체결 시각, Unix ms)

#### 호가창 엔드포인트

```
GET https://api.upbit.com/v1/orderbook
```

**쿼리 파라미터:**

| 파라미터  | 타입   | 필수 여부 | 설명                           |
|-----------|--------|-----------|--------------------------------|
| `markets` | string | Yes       | 마켓 코드 목록, 예: `KRW-BTC` |

**응답 예시:**
```json
[
  {
    "market": "KRW-BTC",
    "timestamp": 1529910247984,
    "total_ask_size": 15.72,
    "total_bid_size": 8.34,
    "orderbook_units": [
      {
        "ask_price": 8560000,
        "bid_price": 8550000,
        "ask_size": 0.5,
        "bid_size": 1.2
      }
    ]
  }
]
```

#### 마켓 코드

```
GET https://api.upbit.com/v1/market/all?isDetails=false
```

### 2.2 WebSocket 스트리밍

**WebSocket URL:** `wss://api.upbit.com/websocket/v1`
**프라이빗 URL:** `wss://api.upbit.com/websocket/v1/private`

#### 구독 메시지 형식

```json
[
  {"ticket": "unique-uuid-here"},
  {"type": "ticker", "codes": ["KRW-BTC", "KRW-ETH"]},
  {"format": "DEFAULT"}
]
```

단일 구독에서 여러 데이터 유형을 조합할 수 있다:
```json
[
  {"ticket": "my-connection-001"},
  {"type": "ticker", "codes": ["KRW-BTC"]},
  {"type": "orderbook", "codes": ["KRW-BTC"]},
  {"format": "DEFAULT"}
]
```

| 필드     | 타입   | 설명                                                |
|----------|--------|-----------------------------------------------------|
| `ticket` | string | 고유 연결 식별자 (임의 문자열 또는 UUID)            |
| `type`   | string | `ticker`, `trade`, 또는 `orderbook`                |
| `codes`  | array  | 마켓 코드 — 대문자 필수                             |
| `format` | string | `DEFAULT` (전체 필드) 또는 `SIMPLE` (축약)          |

**스냅샷 제어:**
- `"isOnlySnapshot": true` — 초기 스냅샷만 수신, 실시간 스트림 없음
- `"isOnlyRealtime": true` — 스냅샷 건너뛰고 실시간 업데이트만 수신

#### 티커 스트림 응답

```json
{
  "type": "ticker",
  "code": "KRW-BTC",
  "opening_price": 8200000.0,
  "high_price": 8679000.0,
  "low_price": 8100000.0,
  "trade_price": 8550000.0,
  "prev_closing_price": 8200000.0,
  "change": "RISE",
  "change_price": 350000.0,
  "signed_change_price": 350000.0,
  "change_rate": 0.04268292,
  "signed_change_rate": 0.04268292,
  "trade_volume": 0.12345678,
  "acc_trade_volume": 18000.5,
  "acc_trade_price": 150000000000.0,
  "trade_date": "20180418",
  "trade_time": "102340",
  "trade_timestamp": 1524047020000,
  "acc_trade_volume_24h": 36000.1,
  "acc_trade_price_24h": 300000000000.0,
  "timestamp": 1524047026072,
  "stream_type": "REALTIME"
}
```

### 2.3 인증

| 엔드포인트 유형       | API 키 필요 여부 | 인증 방식                                                |
|-----------------------|------------------|----------------------------------------------------------|
| 시세 조회 REST        | 아니오           | 없음 — 모든 시장 데이터 엔드포인트 공개                  |
| 시세 조회 WebSocket   | 아니오           | 없음                                                     |
| 거래소 REST           | 예               | `Authorization: Bearer {JWT}` 헤더의 JWT 토큰            |
| 거래소 WebSocket      | 예               | 연결 후 `Authorization` 헤더에 JWT 토큰 전달             |

**중요:** Upbit 시세 조회 API(티커, 호가창, 캔들, 거래 내역)는 인증이 필요 없다. 계좌 수준의 작업(주문, 잔고)에만 API 키가 필요하다.

### 2.4 요청 빈도 제한

| 리소스 / 그룹                              | 제한                              |
|--------------------------------------------|-----------------------------------|
| 시세 조회 API (티커, 호가창, 캔들, 거래)   | IP당 초당 10회                    |
| 거래소 API (주문, 계좌)                    | API 키당 초당 30회                |
| 주문 생성                                  | API 키당 초당 8회                 |
| WebSocket 연결                             | 초당 신규 5회                     |
| WebSocket 메시지                           | 초당 5회, 분당 100회              |

**응답 헤더:** `Remaining-Req: group=market; min=600; sec=9`
- `sec` = 현재 1초 윈도우 내 남은 요청 수
- `min` = 현재 1분 윈도우 내 남은 요청 수

제한 초과 시 **HTTP 429** 반환; 반복 위반 시 **HTTP 418** 반환(응답에 차단 기간 포함).

### 2.5 데이터 형식

| 필드                   | 타입    | 설명                              |
|------------------------|---------|-----------------------------------|
| `code`                 | string  | 마켓 코드 (`KRW-BTC`)             |
| `trade_price`          | number  | 최근 체결 가격 (KRW)              |
| `trade_volume`         | number  | 최근 거래량 (BTC)                 |
| `timestamp`            | integer | 서버 타임스탬프 (Unix ms)         |
| `trade_timestamp`      | integer | 정확한 체결 타임스탬프 (Unix ms)  |
| `acc_trade_volume_24h` | number  | 24시간 누적 거래량                |
| `change`               | string  | `RISE`, `FALL`, 또는 `EVEN`      |
| `stream_type`          | string  | `SNAPSHOT` 또는 `REALTIME`        |

### 2.6 알려진 한계

- **초당 10회 상한:** 시세 조회 엔드포인트는 엄격하게 적용된다. 동일 IP에서 여러 폴링 스레드를 동시에 실행하면 모든 엔드포인트 합산으로 이 한계에 금방 도달한다.
- **WebSocket 초당 5회 제한:** 이 제한은 서버로 보내는 구독 메시지에 적용되며, 수신 메시지에는 적용되지 않는다. 일단 구독하면 들어오는 스트림 데이터는 제한이 없다.
- **JWT 만료:** 거래소 API JWT 토큰은 만료된다. 장기 실행 세션에는 토큰 갱신 로직이 필요하다.
- **Upbit 보안 사고:** Upbit는 2019년 11월 중대한 보안 사고를 겪었다(ETH 342,000개 탈취, 당시 약 4,900만 달러 상당). 사고 이후 보안 강화 조치와 콜드 월렛 정책이 도입됐다. 이후 대형 보안 사고는 발생하지 않았지만, 보안 강화와 관련된 API 정책 변경을 지속적으로 모니터링해야 한다.

---

## 3. Coinone

**유형:** 국내 거래소
**기준 통화:** KRW
**마켓 코드 형식:** 경로 파라미터로 `quote_currency=KRW`, `target_currency=BTC` 사용

### 3.1 REST API 엔드포인트

**Base URL:** `https://api.coinone.co.kr`

#### 티커 엔드포인트 — 단일 심볼

```
GET https://api.coinone.co.kr/public/v2/ticker_new/{quote_currency}/{target_currency}
```

**경로 파라미터:**

| 파라미터          | 타입   | 필수 여부 | 설명                        |
|-------------------|--------|-----------|-----------------------------|
| `quote_currency`  | string | Yes       | 마켓 기준 통화: `KRW`       |
| `target_currency` | string | Yes       | 코인 심볼: `BTC`            |

**쿼리 파라미터:**

| 파라미터          | 타입    | 필수 여부 | 설명                                      |
|-------------------|---------|-----------|-------------------------------------------|
| `additional_data` | boolean | No        | 전일 데이터 포함 여부 (기본값: false)     |

**요청 예시:**
```
GET https://api.coinone.co.kr/public/v2/ticker_new/KRW/BTC
```

**응답 예시:**
```json
{
  "result": "success",
  "error_code": "0",
  "server_time": 1416895635000,
  "tickers": [
    {
      "quote_currency": "KRW",
      "target_currency": "BTC",
      "timestamp": 1499341142000,
      "high": "3845000.0",
      "low": "3819000.0",
      "first": "3825000.0",
      "last": "3833000.0",
      "quote_volume": "10000.0",
      "target_volume": "163.3828",
      "best_asks": [{"price": "1200.0", "qty": "1.234"}],
      "best_bids": [{"price": "1000.0", "qty": "0.123"}],
      "id": "1499341142000001"
    }
  ]
}
```

#### 티커 엔드포인트 — 전체 심볼

```
GET https://api.coinone.co.kr/public/v2/ticker_new/{quote_currency}
```

단일 호출로 KRW 기준 모든 티커를 반환한다(`tickers` 배열에 전체 자산 포함).

**요청 예시:**
```
GET https://api.coinone.co.kr/public/v2/ticker_new/KRW
```

#### 호가창 엔드포인트

```
GET https://api.coinone.co.kr/public/v2/orderbook/{quote_currency}/{target_currency}
```

**쿼리 파라미터:**

| 파라미터           | 타입    | 필수 여부 | 설명                                         |
|--------------------|---------|-----------|----------------------------------------------|
| `size`             | integer | No        | 호가 깊이: 5, 10, 15, 또는 20 (기본값: 15)   |
| `order_book_unit`  | number  | No        | 집계 단위 (기본값: 0.0, 집계 없음)           |

**응답 예시:**
```json
{
  "result": "success",
  "error_code": "0",
  "timestamp": 1644488410702,
  "id": "1644488410702001",
  "quote_currency": "KRW",
  "target_currency": "BTC",
  "order_book_unit": "1000.0",
  "bids": [
    {"price": "75862000", "qty": "0.5"}
  ],
  "asks": [
    {"price": "75863000", "qty": "22.5"}
  ]
}
```

### 3.2 WebSocket 스트리밍

**WebSocket URL:** `wss://stream.coinone.co.kr`

공개 WebSocket은 인증이 필요 없다.

#### 구독 메시지 형식

```json
{
  "request_type": "SUBSCRIBE",
  "channel": "TICKER",
  "topic": {
    "quote_currency": "KRW",
    "target_currency": "BTC"
  },
  "format": "DEFAULT"
}
```

| 필드           | 타입   | 설명                                           |
|----------------|--------|------------------------------------------------|
| `request_type` | string | `SUBSCRIBE` 또는 `UNSUBSCRIBE` (대문자 필수)   |
| `channel`      | string | `TICKER`, `ORDERBOOK`, 또는 `TRADE`            |
| `topic`        | object | `quote_currency` + `target_currency` 필드      |
| `format`       | string | `DEFAULT` (전체 필드) 또는 `SHORT` (축약)      |

#### 티커 스트림 응답

```json
{
  "response_type": "TICKER",
  "data": {
    "quote_currency": "KRW",
    "target_currency": "BTC",
    "timestamp": 1499341142000,
    "high": "3845000.0",
    "low": "3819000.0",
    "first": "3825000.0",
    "last": "3833000.0",
    "quote_volume": "10000.0",
    "target_volume": "163.3828",
    "best_asks": [{"price": "1200.0", "qty": "1.234"}],
    "best_bids": [{"price": "1000.0", "qty": "0.123"}],
    "id": "1499341142000001"
  }
}
```

#### 호가창 스트림 응답

```json
{
  "response_type": "DATA",
  "channel": "ORDERBOOK",
  "data": {
    "quote_currency": "KRW",
    "target_currency": "BTC",
    "timestamp": 1693560155038,
    "id": "1693560155038001",
    "asks": [{"price": "75863000", "qty": "22.5"}],
    "bids": [{"price": "75862000", "qty": "0.5"}]
  }
}
```

**동작:** 구독 시 초기 스냅샷이 전달된다. 이후 메시지는 호가창이 변경될 때만 전송되는 증분 업데이트다.

#### 하트비트(Heartbeat)

서버는 PING 없이 30분간 유휴 상태인 연결을 종료한다. 25초마다 PING을 전송하라:
```json
{"request_type": "PING"}
```

### 3.3 인증

| 엔드포인트 유형        | API 키 필요 여부 | 인증 방식                                                           |
|------------------------|------------------|--------------------------------------------------------------------|
| 공개 REST (v2)         | 아니오           | 없음                                                               |
| 공개 WebSocket         | 아니오           | 없음                                                               |
| 프라이빗 REST (v2)     | 예               | `X-COINONE-PAYLOAD` (base64 JSON) + `X-COINONE-SIGNATURE` (HMAC-SHA512) 헤더 |
| 프라이빗 REST (v2.1)   | 예               | UUID v4 nonce (재전송 공격 방지)                                   |

### 3.4 요청 빈도 제한

| 리소스                  | 제한                                               |
|-------------------------|----------------------------------------------------|
| WebSocket 연결          | IP당 최대 20개 (초과 시 4290 클로즈 코드 발생)     |
| WebSocket 유휴 타임아웃 | PING 없이 30분                                     |
| REST API (공개)         | 명시적으로 공개되지 않음; 보수적 추정: ~초당 10회  |

**참고:** Coinone은 공식 문서에서 구체적인 REST 요청 빈도 제한 수치를 공개하지 않는다. "API 요청건수 제한 안내"로만 언급되며 구체적인 수치는 없다. 보수적인 재시도 및 지수 백오프(backoff) 전략을 구현해야 한다.

### 3.5 데이터 형식

| 필드              | 타입    | 설명                              |
|-------------------|---------|-----------------------------------|
| `target_currency` | string  | 코인 심볼 (`BTC`)                 |
| `quote_currency`  | string  | 마켓 통화 (`KRW`)                 |
| `last`            | string  | 최근 체결 가격 (KRW, 문자열)      |
| `high`            | string  | 24시간 최고가 (KRW, 문자열)       |
| `low`             | string  | 24시간 최저가 (KRW, 문자열)       |
| `first`           | string  | 시가 (KRW, 문자열)                |
| `target_volume`   | string  | 24시간 거래량 (BTC, 문자열)       |
| `quote_volume`    | string  | 24시간 KRW 거래대금 (문자열)      |
| `timestamp`       | integer | Unix ms 타임스탬프                |

**중요:** Bithumb, Upbit와 달리 Coinone 응답의 모든 숫자 값은 **문자열**로 반환된다. 산술 연산 전에 `float()` 또는 `Decimal()`로 파싱해야 한다.

### 3.6 알려진 한계

- **문자열 인코딩 숫자:** 모든 가격 및 거래량 필드가 JSON 문자열이다. 산술 연산 전에 타입 변환이 필요하다.
- **WebSocket 재연결:** Coinone은 자동 재연결을 지원하지 않는다. 연결이 끊기면 클라이언트가 다시 구독해야 한다.
- **IP당 20연결 제한:** 같은 IP에서 개발 인스턴스를 여러 개 실행하면 테스트 중에 이 제한에 금방 도달할 수 있다.
- **부분 호가창 업데이트:** 호가창 WebSocket은 전체 호가창이 아닌 변경된 호가 레벨만 전달한다. 클라이언트가 로컬에서 호가창 상태를 유지해야 한다.
- **API 버전 차이:** v2.0은 camelCase 응답을 사용하고, v2.1은 요청과 응답 모두 snake_case를 사용한다. 신규 구현에서는 현재 버전인 v2를 사용해야 한다.

---

## 4. Binance

**유형:** 해외 거래소
**기준 통화:** USDT
**마켓 코드 형식:** `BTCUSDT`, `ETHUSDT` (구분자 없음)

### 4.1 REST API 엔드포인트

**Base URL:**
- 기본: `https://api.binance.com`
- 대체: `https://api-gcp.binance.com`, `https://api1.binance.com` – `https://api4.binance.com`
- 시장 데이터 전용 (거래 불가): `https://data-api.binance.vision`

#### 티커 가격 엔드포인트 (경량)

```
GET https://api.binance.com/api/v3/ticker/price
```

**쿼리 파라미터:**

| 파라미터  | 타입   | 필수 여부 | 설명                                                  |
|-----------|--------|-----------|-------------------------------------------------------|
| `symbol`  | string | No        | 단일 심볼, 예: `BTCUSDT`; 전체 심볼은 생략            |
| `symbols` | string | No        | JSON 배열 문자열, 예: `["BTCUSDT","ETHUSDT"]`         |

**요청 가중치:** 단일 심볼 2, 전체 심볼 4, 복수 심볼 4

**요청 예시:**
```
GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
```

**응답 예시 (단일):**
```json
{
  "symbol": "BTCUSDT",
  "price": "92450.15000000"
}
```

**응답 예시 (복수):**
```json
[
  {"symbol": "BTCUSDT", "price": "92450.15000000"},
  {"symbol": "ETHUSDT", "price": "3215.82000000"}
]
```

#### 24시간 롤링 통계

```
GET https://api.binance.com/api/v3/ticker/24hr
```

**쿼리 파라미터:**

| 파라미터  | 타입   | 필수 여부 | 설명                              |
|-----------|--------|-----------|-----------------------------------|
| `symbol`  | string | No        | 단일 심볼                         |
| `symbols` | string | No        | 심볼 JSON 배열                    |
| `type`    | string | No        | `FULL` (기본값) 또는 `MINI`       |

**요청 가중치:**
- 1~20개 심볼: 2
- 21~100개 심볼: 40
- 101개 이상 또는 전체 심볼: 80

**응답 예시 (FULL 타입):**
```json
{
  "symbol": "BTCUSDT",
  "priceChange": "-94.99999800",
  "priceChangePercent": "-95.960",
  "weightedAvgPrice": "0.29628482",
  "prevClosePrice": "0.10002000",
  "lastPrice": "92450.15000000",
  "lastQty": "0.00045000",
  "bidPrice": "92450.00000000",
  "bidQty": "1.50000000",
  "askPrice": "92451.00000000",
  "askQty": "0.80000000",
  "openPrice": "91000.00000000",
  "highPrice": "93500.00000000",
  "lowPrice": "90800.00000000",
  "volume": "18000.50000000",
  "quoteVolume": "1654792000.00000000",
  "openTime": 1499783499040,
  "closeTime": 1499869899040,
  "firstId": 28385,
  "lastId": 28460,
  "count": 76
}
```

#### 호가창 엔드포인트

```
GET https://api.binance.com/api/v3/depth
```

**쿼리 파라미터:**

| 파라미터  | 타입    | 필수 여부 | 설명                                                    |
|-----------|---------|-----------|---------------------------------------------------------|
| `symbol`  | string  | Yes       | 마켓 심볼, 예: `BTCUSDT`                               |
| `limit`   | integer | No        | 호가 깊이: 5, 10, 20, 50, 100 (기본값), 500, 1000, 5000 |

**limit 값별 요청 가중치:** 1~100 → 5; 101~500 → 25; 501~1000 → 50; 1001~5000 → 250

**응답 예시:**
```json
{
  "lastUpdateId": 1027024,
  "bids": [
    ["92450.00000000", "1.50000000"]
  ],
  "asks": [
    ["92451.00000000", "0.80000000"]
  ]
}
```

### 4.2 WebSocket 스트리밍

**WebSocket Base URL:**
- `wss://stream.binance.com:9443`
- `wss://stream.binance.com:443`

#### 연결 방식

**단일 스트림:**
```
wss://stream.binance.com:9443/ws/btcusdt@ticker
```

**복합 스트림:**
```
wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker
```

**동적 구독 (연결 후):**
```json
{
  "method": "SUBSCRIBE",
  "params": ["btcusdt@ticker", "ethusdt@ticker"],
  "id": 1
}
```

#### 개별 심볼 티커 스트림

**스트림 이름:** `{symbol}@ticker` (소문자 심볼)

**예시:** `wss://stream.binance.com:9443/ws/btcusdt@ticker`

**스트림 응답:**
```json
{
  "e": "24hrTicker",
  "E": 1672515782136,
  "s": "BTCUSDT",
  "p": "-200.50000000",
  "P": "-0.217",
  "w": "92500.00000000",
  "x": "92650.00000000",
  "c": "92450.15000000",
  "Q": "0.00045000",
  "b": "92450.00000000",
  "B": "1.50000000",
  "a": "92451.00000000",
  "A": "0.80000000",
  "o": "92650.00000000",
  "h": "93500.00000000",
  "l": "90800.00000000",
  "v": "18000.50000000",
  "q": "1654792000.00000000",
  "O": 1672429382000,
  "C": 1672515782000,
  "F": 1250000,
  "L": 1268150,
  "n": 18151
}
```

**필드 범례:**

| 필드 | 설명                                |
|------|-------------------------------------|
| `e`  | 이벤트 타입 (`24hrTicker`)          |
| `E`  | 이벤트 시각 (Unix ms)               |
| `s`  | 심볼                                |
| `p`  | 가격 변동 (절대값)                  |
| `P`  | 가격 변동률                         |
| `w`  | 가중 평균 가격                      |
| `x`  | 24시간 윈도우 이전 첫 체결 가격     |
| `c`  | 최근 가격 (현재 가격)               |
| `Q`  | 최근 거래량                         |
| `b`  | 최우선 매수 호가                    |
| `B`  | 최우선 매수 수량                    |
| `a`  | 최우선 매도 호가                    |
| `A`  | 최우선 매도 수량                    |
| `o`  | 시가 (24시간 윈도우 시작)           |
| `h`  | 고가 (24시간)                       |
| `l`  | 저가 (24시간)                       |
| `v`  | 기준 자산 총 거래량 (24시간)        |
| `q`  | 견적 자산 총 거래대금 (24시간)      |
| `O`  | 통계 시작 시각                      |
| `C`  | 통계 종료 시각                      |
| `F`  | 첫 번째 거래 ID                     |
| `L`  | 마지막 거래 ID                      |
| `n`  | 거래 건수                           |

**핵심 가격 필드:** `c` (최근 가격, USDT)

#### 미니 티커 (경량 대안)

스트림: `btcusdt@miniTicker`

포함 필드: `e`, `E`, `s`, `c` (종가), `o` (시가), `h` (고가), `l` (저가), `v` (거래량), `q` (거래대금)

**지원 중단 공지:** `!ticker@arr` (전체 마켓 티커) 스트림은 2025년 11월 14일부로 지원 중단되었다. 개별 심볼에는 `{symbol}@ticker`를, 전체 심볼에는 `!miniTicker@arr`를 사용하라.

### 4.3 인증

| 엔드포인트 유형    | API 키 필요 여부 | 인증 방식                                                          |
|--------------------|------------------|--------------------------------------------------------------------|
| 공개 REST          | 아니오           | 없음 — 시장 데이터 엔드포인트 공개                                 |
| 공개 WebSocket     | 아니오           | 없음                                                               |
| 프라이빗 REST      | 예               | `X-MBX-APIKEY` 헤더 + 쿼리 문자열의 HMAC-SHA256 서명              |
| 프라이빗 WebSocket | 예               | `/api/v3/userDataStream` 엔드포인트에서 `listenKey` 발급 후 사용  |

### 4.4 요청 빈도 제한

**REST API (IP당):**

| 제한 유형        | 제한                              |
|------------------|-----------------------------------|
| REQUEST_WEIGHT   | 분당 6,000 가중치 단위            |
| RAW_REQUESTS     | 5분당 61,000회                    |

**응답 헤더:**
- `X-MBX-USED-WEIGHT-1M`: 현재 분에서 사용한 가중치

**WebSocket 연결 제한:**

| 제한 유형                   | 제한                               |
|-----------------------------|-------------------------------------|
| 연결당 수신 메시지          | 초당 5회                            |
| 연결당 스트림 수            | 최대 1,024개                        |
| IP당 신규 연결 (5분)        | 300회                               |
| 연결 유지 시간              | 24시간 (이후 재연결 필요)           |

**주요 엔드포인트 가중치:**
- `GET /api/v3/ticker/price` (단일): 가중치 2
- `GET /api/v3/ticker/price` (전체): 가중치 4
- `GET /api/v3/ticker/24hr` (단일): 가중치 2
- `GET /api/v3/ticker/24hr` (전체 심볼): 가중치 80
- `GET /api/v3/depth` (limit 100): 가중치 5

요청 빈도 제한 초과 시 **HTTP 429** 반환; 반복 위반 시 IP 차단 기간이 2분에서 최대 3일까지 증가한다.

### 4.5 데이터 형식

| 필드       | REST 필드명    | WS 필드 | 타입    | 설명                   |
|------------|----------------|---------|---------|------------------------|
| 심볼       | `symbol`       | `s`     | string  | `BTCUSDT`              |
| 최근 가격  | `lastPrice`    | `c`     | string  | 현재 가격 (USDT)       |
| 24시간 고가 | `highPrice`   | `h`     | string  | 24시간 최고가          |
| 24시간 저가 | `lowPrice`    | `l`     | string  | 24시간 최저가          |
| 24시간 거래량 | `volume`    | `v`     | string  | 기준 자산 거래량       |
| 거래대금   | `quoteVolume`  | `q`     | string  | 견적 (USDT) 거래대금   |
| 타임스탬프 | `closeTime`    | `C`     | integer | Unix ms                |

**중요:** Binance 응답의 모든 숫자 값은 **JSON 문자열**이다(예: `"92450.15000000"`). 산술 연산 전에 `float()`로 파싱해야 한다.

### 4.6 알려진 한계

- **WS 필드명 약식 표기:** 티커 스트림은 REST 필드명(`lastPrice`, `highPrice`, `lowPrice`)과 다른 단일 문자 약식 필드명(`c`, `h`, `l` 등)을 사용한다. 정규화 로직은 두 스키마를 모두 처리해야 한다.
- **24시간 롤링 윈도우:** 티커 통계는 UTC 일일 초기화 방식이 아닌 24시간 롤링 윈도우를 사용한다. 이는 거래량 및 가격 변동 계산에 영향을 미친다.
- **WebSocket 24시간 만료:** WebSocket 연결은 24시간 후 자동으로 종료된다. 자동 재연결 기능을 구현해야 한다.
- **지역 제한:** Binance는 미국, 캐나다 온타리오 주, 그 외 여러 지역에서 이용이 불가하다. KRW 시장을 대상으로 하는 차익거래 모니터에는 영향이 없지만, 해당 지역에서 VPN을 사용하는 경우 공개 시장 데이터에는 `data-api.binance.vision`을 사용해야 할 수 있다.
- **`!ticker@arr` 지원 중단:** 전체 마켓 티커 스트림은 지원이 중단되었다. 사용하지 말 것.

---

## 5. Bybit

**유형:** 해외 거래소
**기준 통화:** USDT
**마켓 코드 형식:** `BTCUSDT`, `ETHUSDT` (구분자 없음)

### 5.1 REST API 엔드포인트

**Base URL:** `https://api.bybit.com`
**테스트넷:** `https://api-testnet.bybit.com`

모든 엔드포인트는 `/v5/` 접두사를 사용한다(V5는 2023년부터 현재 프로덕션 API).

#### 티커 엔드포인트

```
GET https://api.bybit.com/v5/market/tickers
```

**쿼리 파라미터:**

| 파라미터   | 타입   | 필수 여부 | 설명                                           |
|------------|--------|-----------|------------------------------------------------|
| `category` | string | Yes       | `spot`, `linear`, `inverse`, 또는 `option`     |
| `symbol`   | string | No        | 심볼, 예: `BTCUSDT`; 전체 심볼은 생략          |

**요청 예시:**
```
GET https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT
```

**응답 예시:**
```json
{
  "retCode": 0,
  "retMsg": "OK",
  "result": {
    "category": "spot",
    "list": [
      {
        "symbol": "BTCUSDT",
        "bid1Price": "92440.00",
        "bid1Size": "2.00000000",
        "ask1Price": "92451.00",
        "ask1Size": "1.86217200",
        "lastPrice": "92450.15",
        "prevPrice24h": "91000.00",
        "price24hPcnt": "0.0159",
        "highPrice24h": "93500.00",
        "lowPrice24h": "90800.00",
        "turnover24h": "1654792000.00000000",
        "volume24h": "18000.50000000",
        "usdIndexPrice": "92448.5000000"
      }
    ]
  },
  "retExtInfo": {},
  "time": 1673859087947
}
```

**핵심 가격 필드:** `lastPrice` (string, USDT)
**타임스탬프 필드:** `time` (최상위, Unix ms)

#### 호가창 엔드포인트

```
GET https://api.bybit.com/v5/market/orderbook
```

**쿼리 파라미터:**

| 파라미터   | 타입    | 필수 여부 | 설명                                         |
|------------|---------|-----------|----------------------------------------------|
| `category` | string  | Yes       | `spot`, `linear`, `inverse`, `option`        |
| `symbol`   | string  | Yes       | 심볼, 예: `BTCUSDT`                          |
| `limit`    | integer | No        | 호가 깊이: 1~50 (스팟 기본값 1), 최대 200    |

**응답 예시:**
```json
{
  "retCode": 0,
  "retMsg": "OK",
  "result": {
    "s": "BTCUSDT",
    "b": [["92440.00", "2.00000000"]],
    "a": [["92451.00", "1.86217200"]],
    "ts": 1673859087947,
    "u": 18012
  },
  "retExtInfo": {},
  "time": 1673859087947
}
```

### 5.2 WebSocket 스트리밍

**WebSocket URL (스팟 — 메인넷):** `wss://stream.bybit.com/v5/public/spot`
**WebSocket URL (테스트넷):** `wss://stream-testnet.bybit.com/v5/public/spot`
**선물(USDT 무기한):** `wss://stream.bybit.com/v5/public/linear`

공개 WebSocket 토픽은 인증이 필요 없다.

#### 구독 메시지 형식

```json
{
  "op": "subscribe",
  "args": ["tickers.BTCUSDT"]
}
```

단일 메시지에 여러 구독 포함:
```json
{
  "req_id": "my-sub-001",
  "op": "subscribe",
  "args": ["tickers.BTCUSDT", "tickers.ETHUSDT"]
}
```

| 필드     | 타입   | 설명                                          |
|----------|--------|-----------------------------------------------|
| `op`     | string | `subscribe` 또는 `unsubscribe`                |
| `args`   | array  | 토픽 문자열 목록                              |
| `req_id` | string | 요청 식별용 선택적 ID (상관 관계 추적용)      |

#### 티커 스트림 응답

**토픽:** `tickers.{SYMBOL}`
**푸시 빈도:** 50ms마다 (5개 거래소 중 가장 빠름)
**데이터 유형:** 스냅샷만 (스팟 티커의 경우 델타 업데이트 없음)

```json
{
  "topic": "tickers.BTCUSDT",
  "ts": 1673853746003,
  "type": "snapshot",
  "cs": 2588407389,
  "data": {
    "symbol": "BTCUSDT",
    "lastPrice": "92450.15",
    "highPrice24h": "93500.00",
    "lowPrice24h": "90800.00",
    "prevPrice24h": "91000.00",
    "volume24h": "18000.50000000",
    "turnover24h": "1654792000.00000000",
    "price24hPcnt": "0.0159",
    "usdIndexPrice": "92448.5000000"
  }
}
```

**필드 설명:**

| 필드             | 설명                              |
|------------------|-----------------------------------|
| `topic`          | 스트림 토픽 식별자                |
| `ts`             | 서버 타임스탬프 (Unix ms)         |
| `type`           | 스팟 티커는 항상 `snapshot`       |
| `cs`             | 크로스 시퀀스 번호                |
| `symbol`         | 거래쌍                            |
| `lastPrice`      | 현재 가격 (USDT)                  |
| `highPrice24h`   | 24시간 최고가                     |
| `lowPrice24h`    | 24시간 최저가                     |
| `prevPrice24h`   | 24시간 전 가격                    |
| `volume24h`      | 24시간 기준 자산 거래량           |
| `turnover24h`    | 24시간 견적 (USDT) 거래대금       |
| `price24hPcnt`   | 24시간 가격 변동률                |
| `usdIndexPrice`  | USD 인덱스 가격                   |

#### 하트비트(Heartbeat) / Ping-Pong

연결 유지를 위해 20초마다 전송:
```json
{"req_id": "heartbeat-001", "op": "ping"}
```

서버 응답:
```json
{"success": true, "ret_msg": "pong", "conn_id": "abc123", "op": "ping"}
```

### 5.3 인증

| 엔드포인트 유형    | API 키 필요 여부 | 인증 방식                                                          |
|--------------------|------------------|--------------------------------------------------------------------|
| 공개 REST          | 아니오           | 없음                                                               |
| 공개 WebSocket     | 아니오           | 없음                                                               |
| 프라이빗 REST      | 예               | `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP`, `X-BAPI-SIGN` 헤더 + HMAC-SHA256 |
| 프라이빗 WebSocket | 예               | 연결 후 API 키 + 서명이 담긴 인증 메시지 전송                      |

### 5.4 요청 빈도 제한

**REST API (IP당):**

| 리소스              | 제한                       |
|---------------------|----------------------------|
| HTTP 요청           | 5초 윈도우당 600회         |
| 위반 시 IP 차단     | 10분 차단                  |

**REST API (UID당 — 주문/거래 엔드포인트):**

| 엔드포인트 유형               | 제한                   |
|-------------------------------|------------------------|
| 주문 생성/수정/취소           | 초당 10~20회           |
| 주문 내역 조회                | 초당 50회              |
| 포지션 조회                   | 초당 50회              |

**WebSocket 연결 제한:**

| 리소스                     | 제한                              |
|----------------------------|-----------------------------------|
| 신규 연결 (5분)            | 5분 윈도우당 최대 500회           |
| IP당 총 연결 수            | 1,000개 (마켓 유형별로 산정)      |
| 구독 메시지당 args 수      | 최대 10개                         |
| args 문자열 길이           | 최대 21,000자                     |

**중요:** WebSocket 요청은 REST 요청 빈도 제한에 **포함되지 않는다.** Bybit는 REST 소진을 방지하기 위해 시장 데이터에 WebSocket을 명시적으로 권장한다.

**응답 헤더:**
- `X-Bapi-Limit-Status`: 남은 요청 횟수
- `X-Bapi-Limit`: 현재 제한값
- `X-Bapi-Limit-Reset-Timestamp`: 제한 초기화 시각

### 5.5 데이터 형식

| 필드           | 타입    | 설명                              |
|----------------|---------|-----------------------------------|
| `symbol`       | string  | `BTCUSDT`                         |
| `lastPrice`    | string  | 현재 가격 (USDT)                  |
| `highPrice24h` | string  | 24시간 최고가 (USDT)              |
| `lowPrice24h`  | string  | 24시간 최저가 (USDT)              |
| `volume24h`    | string  | 기준 자산 거래량 (BTC)            |
| `turnover24h`  | string  | 견적 거래대금 (USDT)              |
| `ts`           | integer | 서버 타임스탬프 (Unix ms)         |

**중요:** Binance와 마찬가지로 모든 숫자 값이 **문자열**로 반환된다. 산술 연산 전에 `float()`로 파싱해야 한다.

### 5.6 알려진 한계

- **스팟 티커는 스냅샷 전용:** 델타 업데이트를 지원하는 파생상품 마켓과 달리, 스팟 티커 WebSocket은 50ms마다 전체 스냅샷을 전달한다. 대역폭은 더 필요하지만 처리는 단순하다.
- **50ms 푸시 빈도:** 이 프로젝트의 5개 거래소 중 가장 빠르지만, 실시간 체결 대비 최대 50ms의 지연이 발생한다.
- **5분당 500회 연결 제한:** 고빈도 재연결(예: 테스트 중)은 이 제한에 금방 도달할 수 있다.
- **공개 시장 데이터에 지역 제한 없음:** Bybit는 글로벌로 운영되며, 공개 WebSocket 스트림은 어느 지역에서도 VPN 없이 접근 가능하다.

---

## 6. 거래소 비교 매트릭스

| 특성                        | Bithumb (v2)               | Upbit                      | Coinone                    | Binance                    | Bybit                      |
|-----------------------------|----------------------------|----------------------------|----------------------------|----------------------------|----------------------------|
| **기준 통화**               | KRW                        | KRW                        | KRW                        | USDT                       | USDT                       |
| **마켓 코드 형식**          | `KRW-BTC`                  | `KRW-BTC`                  | 경로: `KRW/BTC`            | `BTCUSDT`                  | `BTCUSDT`                  |
| **REST Base URL**           | api.bithumb.com/v1/        | api.upbit.com/v1/          | api.coinone.co.kr/public/v2/ | api.binance.com/api/v3/   | api.bybit.com/v5/          |
| **WebSocket URL**           | ws-api.bithumb.com/websocket/v1 | api.upbit.com/websocket/v1 | stream.coinone.co.kr | stream.binance.com:9443/ws/ | stream.bybit.com/v5/public/spot |
| **공개 데이터 인증**        | 없음                       | 없음                       | 없음                       | 없음                       | 없음                       |
| **REST 요청 빈도 제한**     | ~초당 10회 (미공개)        | IP당 초당 10회             | 미공개                     | 분당 6,000 가중치          | 5초당 600회                |
| **WS 연결 제한**            | IP당 초당 10회 신규 연결   | 초당 5회 신규              | IP당 총 20개               | IP당 5분당 300회           | 5분당 500회                |
| **WS 메시지 제한**          | 초당 5회, 분당 100회       | 초당 5회, 분당 100회       | 미공개                     | 연결당 초당 5회            | REST 제한에 미포함         |
| **티커 푸시 빈도**          | 실시간 (이벤트 기반)       | 실시간 (이벤트 기반)       | 변경 시                    | 1초 (롤링 통계)            | 50ms                       |
| **JSON 숫자 타입**          | number                     | number                     | **string**                 | **string**                 | **string**                 |
| **구독 형식**               | ticket 포함 JSON 배열      | ticket 포함 JSON 배열      | 단일 JSON 객체             | op/params 포함 JSON 객체   | op/args 포함 JSON 객체     |
| **하트비트 필요 여부**      | 예 (암묵적)                | 암묵적                     | 예 (25초마다 PING)         | Ping 암묵적                | 예 (20초마다 PING)         |
| **가격 필드명 (티커)**      | `trade_price`              | `trade_price`              | `last`                     | `c` (WS), `lastPrice` (REST) | `lastPrice`              |
| **거래량 필드 (24시간)**    | `acc_trade_volume_24h`     | `acc_trade_volume_24h`     | `target_volume`            | `v` (WS), `volume` (REST)  | `volume24h`                |
| **타임스탬프 필드**         | `timestamp`                | `timestamp`                | `timestamp`                | `E` (WS), `closeTime` (REST) | `ts`                     |

---

## 7. 김치 프리미엄 계산 방법론

"김치 프리미엄(Kimchi Premium)"은 암호화폐가 국내 거래소(KRW 기준)에서 해외 거래소(USDT 기준) 대비 얼마나 높은 가격에 거래되는지를 나타내는 백분율 프리미엄이다. 이는 한국의 자본 규제, 규제 환경, 수요·공급 불균형에서 비롯된다.

### 7.1 계산식

```
kimchi_premium_pct = ((krw_price / usd_krw_rate) / usdt_price - 1) × 100
```

각 변수:
- `krw_price` = 국내 거래소의 최근 체결 가격 (KRW), 예: Bithumb BTC 가격
- `usd_krw_rate` = 현재 USD 1달러당 KRW 환율 (예: 1,320.50 KRW/USD)
- `usdt_price` = 해외 거래소의 최근 체결 가격 (USDT), 예: Binance BTC 가격
- 이 계산식은 KRW 가격을 USD 등가로 변환한 후 비교한다

**예시:**
```
Bithumb BTC:  88,200,000 KRW
Binance BTC:  65,000 USDT ≈ 65,000 USD (USDT ≈ USD 가정)
KRW/USD 환율: 1,350 KRW per USD

Bithumb 기준 BTC의 USD 환산: 88,200,000 / 1,350 = 65,333.33 USD
김치 프리미엄: (65,333.33 / 65,000 - 1) × 100 = +0.51%
```

### 7.2 단순화 가정

**USDT ≈ USD (1:1 페그 가정):**
테더(Tether, USDT)는 USD 대비 소프트 페그를 유지하며, 통상 USD의 ±0.1% 범위 내에서 거래된다. 실시간 차익거래 모니터링에서는 1 USDT = 1 USD로 취급하는 것이 일반적이다. 더 정밀한 계산이 필요하다면 Binance의 `USDTUSD` 거래쌍이나 법정화폐 USD 기준과의 USDT 가격 비교를 통한 실시간 USDT/USD 디페그(depeg) 확인을 추가할 수 있으나, 미미한 이점에 비해 복잡도가 크게 증가한다.

### 7.3 구현 아키텍처

```python
class KimchiSpreadCalculator:
    def calculate_spread(
        self,
        krw_price: float,       # from Bithumb/Upbit/Coinone WebSocket
        usdt_price: float,      # from Binance/Bybit WebSocket
        usd_krw_rate: float,    # from KRW/USD data source (updated every 60s)
    ) -> float:
        """
        Returns kimchi premium as a percentage.
        Positive = domestic premium (KRW exchanges higher).
        Negative = international discount (KRW exchanges cheaper).
        """
        krw_price_in_usd = krw_price / usd_krw_rate
        spread_pct = (krw_price_in_usd / usdt_price - 1) * 100
        return spread_pct
```

### 7.4 동일 통화 내 거래소 간 스프레드

같은 통화권 내 거래쌍(예: Bithumb vs Upbit)에서는 FX 변환이 필요 없다:

```
spread_pct = (price_a / price_b - 1) × 100
```

이는 더 단순한 계산이므로 김치 프리미엄 지표와 별도로 추적해야 한다.

### 7.5 데이터 신선도 고려 사항

스프레드 계산은 두 가격 입력값이 모두 최신일 때만 유효하다. 데이터 만료 임계값을 구현해야 한다:

```python
MAX_PRICE_AGE_MS = 5000  # 5 seconds

def is_valid_for_spread(price_a_ts: int, price_b_ts: int) -> bool:
    now_ms = int(time.time() * 1000)
    return (
        (now_ms - price_a_ts) < MAX_PRICE_AGE_MS and
        (now_ms - price_b_ts) < MAX_PRICE_AGE_MS
    )
```

어느 한 거래소의 가격이 만료된 경우(예: WebSocket 연결 끊김), 오래된 가격으로 스프레드를 계산해 표시하는 대신 계산을 억제하고 알림을 발생시켜야 한다.

---

## 8. KRW/USD 환율 API 권고 사항

KRW 가격을 USD 등가로 변환하려면 신뢰할 수 있는 KRW/USD 환율 소스가 필요하다. 아래 세 가지 옵션을 평가한다.

### 8.1 옵션 A — ExchangeRate-API (권장)

**제공자:** ExchangeRate-API (exchangerate-api.com)
**무료 티어 엔드포인트:** `https://v6.exchangerate-api.com/v6/{API_KEY}/latest/USD`
**공개 접근 (키 불필요):** `https://open.er-api.com/v6/latest/USD`

**요청 예시 (공개 접근, 키 불필요):**
```
GET https://open.er-api.com/v6/latest/USD
```

**응답 예시 (축약):**
```json
{
  "result": "success",
  "base_code": "USD",
  "time_last_update_unix": 1706227200,
  "time_next_update_unix": 1706313600,
  "rates": {
    "USD": 1,
    "KRW": 1320.5,
    "EUR": 0.925
  }
}
```

**KRW 환율 추출:** `response["rates"]["KRW"]`
**업데이트 빈도:** 24시간마다 (공개 접근) / 매 시간 (키 발급 무료 티어)

| 티어           | 요청 빈도 제한          | 업데이트 빈도 | 비용       |
|----------------|-------------------------|---------------|------------|
| 공개 접근      | 명시적 제한 없음        | 24시간        | 무료       |
| 무료 (API 키)  | 월 1,500회              | 1시간         | 무료       |
| 스타터         | 월 30,000회             | 1분           | ~월 $5     |

**권고 사항:** 실시간 차익거래 모니터에서는 24시간마다 업데이트되는 **공개 접근** 엔드포인트로도 충분하다. KRW/USD는 일반적으로 하루에 1% 미만으로 완만하게 움직이기 때문이다. 환율을 캐시한 뒤 이 엔드포인트에 대해 60초마다 갱신하면 된다. 실제 환율 데이터는 어차피 24시간에 한 번만 변경된다.

KRW 변동성이 높은 시기에 더 높은 정확도가 필요하다면(예: 프로덕션 환경) 분 단위 업데이트를 위해 스타터 플랜으로 업그레이드하는 것을 고려하라.

### 8.2 옵션 B — Binance USDT/KRW 거래쌍

Binance는 대부분의 지역에서 KRW 거래쌍을 직접 제공하지 않는다. 일부 간접적인 방법이 있다:

- **Binance P2P 마켓**은 KRW 환율을 표시하지만, 구조화된 형태의 공개 API로는 제공되지 않는다.
- **USDKRW 합성 환율**은 한국 시장의 Binance BUSD 또는 USDC 거래쌍에서 계산할 수 있지만, 여러 엔드포인트를 교차 참조해야 한다.

**평가:** 권장하지 않는다. Binance에서 KRW/USD 환율을 제공하는 깔끔하고 안정적인 API 엔드포인트가 존재하지 않는다.

### 8.3 옵션 C — 한국은행 API (한국은행 경제통계시스템)

한국은행은 ECOS API를 통해 공식 환율 데이터를 제공한다:

**엔드포인트:** `https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/1/1/064Y001/D/{YYYYMMDD}/{YYYYMMDD}/0000001`

**등록:** 필수 — ecos.bok.or.kr에서 무료 API 키 발급
**업데이트 빈도:** 일 1회 (공식 고시환율)
**데이터:** 공식 일일 USD/KRW 기준 환율 (고시환율)

**평가:** 일일 정산 및 감사 추적에는 적합하지만, 하루에 한 번 업데이트되는 특성상 실시간 스프레드 모니터링에는 적합하지 않다. ExchangeRate-API 값에 대한 검증 수단으로 활용하되 주요 소스로는 사용하지 말 것.

### 8.4 최종 권고

| 시나리오                             | 권장 소스                       |
|--------------------------------------|---------------------------------|
| 실시간 차익거래 (기본)               | ExchangeRate-API 공개 접근      |
| 고변동성 구간 / 프로덕션             | ExchangeRate-API 무료 키 티어   |
| 일일 감사 / 정산                     | 한국은행 ECOS API               |

**구현 패턴:**

```python
class FxRateProvider:
    OPEN_ENDPOINT = "https://open.er-api.com/v6/latest/USD"
    CACHE_TTL_SECONDS = 60   # refresh every 60s; data updates every 24h

    def __init__(self):
        self._rate: float = None
        self._last_fetch: float = 0.0

    async def get_usd_krw(self) -> float:
        now = time.time()
        if self._rate is None or (now - self._last_fetch) > self.CACHE_TTL_SECONDS:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.OPEN_ENDPOINT) as resp:
                    data = await resp.json()
                    self._rate = data["rates"]["KRW"]
                    self._last_fetch = now
        return self._rate
```

---

## 9. 에러 처리 및 복원력 참고 사항

### 9.1 공통 WebSocket 장애 패턴

| 거래소   | 알려진 장애 패턴                                    | 권장 처리 방법                                        |
|----------|-----------------------------------------------------|-------------------------------------------------------|
| Bithumb  | 서버 측 점검으로 인한 연결 끊김                     | 지수 백오프 재연결 (2초 → 64초)                       |
| Upbit    | 지속적인 요청 빈도 제한 남용 시 418 응답            | `Retry-After` 헤더 준수; 모든 요청 일시 중지          |
| Coinone  | 같은 IP에서 20개 이상 연결 시 4290 클로즈 코드 발생 | 코드에서 IP당 단일 연결 강제화                        |
| Binance  | 24시간 WebSocket 만료                               | 매일 재연결 예약; `/ws/` ping 프레임 활용             |
| Bybit    | 재연결 폭발 시 5분당 500회 IP 연결 제한             | 반복 연결 실패 시 백오프 적용                         |

### 9.2 부분 데이터 시나리오

한 거래소의 WebSocket이 끊기고 다른 거래소는 연결된 상태인 경우, 해당 거래소 쌍의 스프레드 계산은 오래된 가격으로 계산되는 대신 "만료(stale)"로 표시하고 억제해야 한다. 거래소별 신선도 추적을 구현해야 한다.

### 9.3 요청 빈도 제한 전략 요약

| 거래소   | REST 전략                        | WebSocket 전략                           |
|----------|----------------------------------|------------------------------------------|
| Bithumb  | 최대 200ms당 1회                 | WS 우선; 초당 구독 메시지 5회            |
| Upbit    | 최대 초당 10회 (쿼터 헤더 활용)  | WS 우선; 초당 5회 메시지 하드 제한       |
| Coinone  | 보수적; 최대 초당 1회            | WS 우선; 단일 연결 유지                  |
| Binance  | `X-MBX-USED-WEIGHT` 모니터링    | 복합 스트림 사용 (연결 1개)              |
| Bybit    | `X-Bapi-Limit-Status` 모니터링  | WS 권장; 요청 빈도 제한 미적용           |

---

## 참고 자료

- Bithumb 공식 API 문서: https://apidocs.bithumb.com/
- Bithumb WebSocket 기본 정보: https://apidocs.bithumb.com/reference/websocket-기본-정보
- Upbit 개발자 센터: https://global-docs.upbit.com/
- Upbit 요청 빈도 제한: https://global-docs.upbit.com/reference/rate-limits
- Upbit WebSocket 모범 사례: https://global-docs.upbit.com/docs/websocket-best-practice
- Coinone 개발자 센터: https://docs.coinone.co.kr/
- Coinone 티커 엔드포인트: https://docs.coinone.co.kr/reference/ticker
- Coinone 공개 WebSocket: https://docs.coinone.co.kr/reference/public-websocket-1
- Binance 스팟 API 문서 (REST): https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
- Binance WebSocket 스트림: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- Binance 스팟 API GitHub: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
- Bybit V5 티커 조회: https://bybit-exchange.github.io/docs/v5/market/tickers
- Bybit WebSocket 연결: https://bybit-exchange.github.io/docs/v5/ws/connect
- Bybit WebSocket 티커: https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
- Bybit 요청 빈도 제한: https://bybit-exchange.github.io/docs/v5/rate-limit
- ExchangeRate-API: https://www.exchangerate-api.com/
- CCXT Bithumb 구현 (참고): https://github.com/ccxt/ccxt/blob/master/python/ccxt/async_support/bithumb.py
