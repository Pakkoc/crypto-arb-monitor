# Exchange API Analysis — Crypto Arbitrage Monitor

**Research Date:** 2026-02-27
**Scope:** Real-time price data collection for 5 exchanges (Bithumb, Upbit, Coinone, Binance, Bybit)
**Purpose:** Step 1 output — foundation for system architecture and connector implementation

---

## Executive Summary

This document covers all five target exchanges in detail: three South Korean domestic exchanges (Bithumb, Upbit, Coinone) that quote prices in KRW, and two international exchanges (Binance, Bybit) that quote in USDT. The core architectural challenge is that domestic and international prices are denominated in different currencies, so meaningful spread comparison requires a live KRW/USD exchange rate as a third data source.

**Key findings:**

1. **All five exchanges provide free public WebSocket streams** — no API key is required for ticker and orderbook data. WebSocket is strongly preferred over REST polling for latency and rate limit reasons.
2. **Bithumb underwent a significant API transition.** The legacy REST/WebSocket API (`api.bithumb.com/public/`, `pubwss.bithumb.com`) remains operational, but the current official API uses the `/v1/` path prefix (REST) and `wss://ws-api.bithumb.com/websocket/v1` (WebSocket). The newer endpoints use the same market-code format as Upbit (`KRW-BTC`), suggesting a unified design.
3. **Upbit and Bithumb v2 share a near-identical REST response schema.** Both use `trade_price`, `acc_trade_volume`, `timestamp` and the `KRW-BTC` market code convention, which simplifies normalization.
4. **Coinone uses a distinct REST API** at `api.coinone.co.kr/public/v2/` with snake_case fields and separate `quote_currency`/`target_currency` path parameters.
5. **Binance's WebSocket uses abbreviated single-character field names** (`c`, `h`, `l`, `v`, etc.) in the stream protocol. Their REST API uses full English names. Parsers must handle both schemas.
6. **Bybit provides the highest-frequency spot ticker stream at 50 ms** and does not count WebSocket activity against REST rate limits.
7. **For KRW/USD conversion**, ExchangeRate-API (open access) or a Binance-provided USDTKRW price are both viable options, each with different tradeoffs (discussed in Section 8).

---

## 1. Bithumb

**Type:** South Korean domestic exchange
**Quote currency:** KRW
**Market code format:** `KRW-BTC`, `KRW-ETH`, etc.

### 1.1 REST API Endpoints

**Base URL:** `https://api.bithumb.com`

> Note: Bithumb maintains two active API surfaces. The legacy API uses the path prefix `/public/` with `{SYMBOL}_{QUOTE}` format (e.g., `/public/ticker/BTC_KRW`). The current API uses `/v1/` path prefix and market codes (`KRW-BTC`). This document targets the current `/v1/` API as the primary implementation target, with legacy paths noted where relevant. Bithumb does not use semantic versioning labels in their official documentation — the path prefix `/v1/` is the only version indicator.

#### Ticker Endpoint (current /v1/ API)

```
GET https://api.bithumb.com/v1/ticker
```

**Query Parameters:**

| Parameter | Type   | Required | Description                                      |
|-----------|--------|----------|--------------------------------------------------|
| `markets` | string | Yes      | Comma-separated market codes, e.g. `KRW-BTC,KRW-ETH` |

**Example Request:**
```
GET https://api.bithumb.com/v1/ticker?markets=KRW-BTC
```

**Example Response:**
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

**Key price field:** `trade_price` (integer, KRW)
**Timestamp field:** `timestamp` (Unix ms)

#### Orderbook Endpoint (current /v1/ API)

```
GET https://api.bithumb.com/v1/orderbook
```

**Query Parameters:**

| Parameter | Type            | Required | Description                               |
|-----------|-----------------|----------|-------------------------------------------|
| `markets` | array of string | Yes      | Market codes, e.g. `KRW-BTC`             |

**Example Response:**
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

#### Market Codes (current /v1/ API)

```
GET https://api.bithumb.com/v1/market/all
```

Returns all supported market codes. Use this to enumerate available KRW pairs.

### 1.2 WebSocket Streaming

**WebSocket URL:** `wss://ws-api.bithumb.com/websocket/v1`
**Private URL:** `wss://ws-api.bithumb.com/websocket/v1/private`

#### Subscription Message Format

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

**Parameters:**

| Field             | Type    | Description                                       |
|-------------------|---------|---------------------------------------------------|
| `ticket`          | string  | Unique identifier for this connection             |
| `type`            | string  | `ticker`, `trade`, or `orderbook`                |
| `codes`           | array   | Market code list (must be uppercase)              |
| `isOnlySnapshot`  | boolean | If true, receive only initial snapshot            |
| `isOnlyRealtime`  | boolean | If true, receive only real-time updates           |
| `format`          | string  | `DEFAULT` or `SIMPLE`                             |

#### Ticker Stream Response

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

**Note:** Legacy WebSocket endpoint `wss://pubwss.bithumb.com/pub/ws` remains operational with a different subscription format:
```json
{"type": "ticker", "symbols": ["BTC_KRW"], "tickTypes": ["MID"]}
```
This endpoint should be avoided for new implementations.

### 1.3 Authentication

| Endpoint type      | API Key required? | Method                                       |
|--------------------|-------------------|----------------------------------------------|
| Public REST        | No                | None                                         |
| Public WebSocket   | No                | None                                         |
| Private REST       | Yes               | HMAC-SHA512 with `Api-Key`, `Api-Sign`, `Api-Nonce` headers |
| Private WebSocket  | Yes               | Token-based auth after connection            |

Private REST authentication requires:
- `Api-Key`: issued API key
- `Api-Sign`: HMAC-SHA512 of `{endpoint}\0{body}\0{nonce}` using the secret key
- `Api-Nonce`: current Unix timestamp in milliseconds

### 1.4 Rate Limits

| Resource                | Limit                        |
|-------------------------|------------------------------|
| WebSocket connections   | 10 connection requests/s per IP |
| WebSocket messages (send) | 5 requests/s, 100/min (as of Dec 2025) |
| REST API public         | Not explicitly published; community reports ~10 req/s before throttling |
| REST rate limit headers | `X-RateLimit-Remaining`, `X-RateLimit-Burst-Capacity`, `X-RateLimit-Replenish-Rate` |

**Recommendation:** Use WebSocket for real-time price data. REST polling should not exceed 5 req/s for public endpoints.

### 1.5 Data Format

| Field             | Type    | Description                    |
|-------------------|---------|--------------------------------|
| `market`          | string  | Market code (`KRW-BTC`)       |
| `trade_price`     | number  | Latest transaction price (KRW) |
| `trade_volume`    | number  | Latest trade size (BTC)        |
| `timestamp`       | integer | Unix ms timestamp              |
| `change`          | string  | `RISE`, `FALL`, or `EVEN`     |
| `acc_trade_volume_24h` | number | 24h rolling volume       |

### 1.6 Known Limitations

- **API version split:** Bithumb runs two distinct API surfaces (legacy at `/public/` and current at `/v1/`). Third-party libraries often target the legacy API. Verify which API surface a library targets before using it.
- **KRW integer prices:** All KRW prices are returned as integers (no decimal places). BTC quantity fields have up to 8 decimal places.
- **WebSocket reconnection:** The current `/v1/` WebSocket does not implement an automatic reconnect mechanism on the server side; clients must detect drops and re-subscribe.
- **Maintenance windows:** Bithumb schedules maintenance approximately once per month. Service may be unavailable for 1–2 hours during these windows.

---

## 2. Upbit

**Type:** South Korean domestic exchange
**Quote currency:** KRW
**Market code format:** `KRW-BTC`, `KRW-ETH`, etc.

### 2.1 REST API Endpoints

**Base URL:** `https://api.upbit.com` (Korean domestic)
**Global/Regional URLs:** `https://sg-api.upbit.com`, `https://id-api.upbit.com`, `https://th-api.upbit.com`

For a Korean-market arbitrage monitor, use `https://api.upbit.com`.

#### Ticker Endpoint

```
GET https://api.upbit.com/v1/ticker
```

**Query Parameters:**

| Parameter | Type   | Required | Description                                          |
|-----------|--------|----------|------------------------------------------------------|
| `markets` | string | Yes      | Comma-separated market codes, e.g. `KRW-BTC,KRW-ETH` |

**Example Request:**
```
GET https://api.upbit.com/v1/ticker?markets=KRW-BTC
```

**Example Response:**
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

**Key price field:** `trade_price` (number, KRW)
**Timestamp field:** `timestamp` (Unix ms) and `trade_timestamp` (exact trade time in Unix ms)

#### Orderbook Endpoint

```
GET https://api.upbit.com/v1/orderbook
```

**Query Parameters:**

| Parameter | Type   | Required | Description                     |
|-----------|--------|----------|---------------------------------|
| `markets` | string | Yes      | Market codes, e.g. `KRW-BTC`  |

**Example Response:**
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

#### Market Codes

```
GET https://api.upbit.com/v1/market/all?isDetails=false
```

### 2.2 WebSocket Streaming

**WebSocket URL:** `wss://api.upbit.com/websocket/v1`
**Private URL:** `wss://api.upbit.com/websocket/v1/private`

#### Subscription Message Format

```json
[
  {"ticket": "unique-uuid-here"},
  {"type": "ticker", "codes": ["KRW-BTC", "KRW-ETH"]},
  {"format": "DEFAULT"}
]
```

Multiple data types can be combined in a single subscription:
```json
[
  {"ticket": "my-connection-001"},
  {"type": "ticker", "codes": ["KRW-BTC"]},
  {"type": "orderbook", "codes": ["KRW-BTC"]},
  {"format": "DEFAULT"}
]
```

| Field    | Type   | Description                                     |
|----------|--------|-------------------------------------------------|
| `ticket` | string | Unique connection identifier (any string/UUID)  |
| `type`   | string | `ticker`, `trade`, or `orderbook`              |
| `codes`  | array  | Market codes — must be uppercase                |
| `format` | string | `DEFAULT` (full fields) or `SIMPLE` (abbreviated) |

**Snapshot control:**
- `"isOnlySnapshot": true` — receive only the initial snapshot, no live stream
- `"isOnlyRealtime": true` — skip snapshot, receive only live updates

#### Ticker Stream Response

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

### 2.3 Authentication

| Endpoint type      | API Key required? | Method                                                   |
|--------------------|-------------------|----------------------------------------------------------|
| Quotation REST     | No                | None — all market data endpoints are open                |
| Quotation WebSocket | No               | None                                                     |
| Exchange REST      | Yes               | JWT token in `Authorization: Bearer {JWT}` header        |
| Exchange WebSocket | Yes               | JWT token in `Authorization` header after connection     |

**Important:** Upbit Quotation API (ticker, orderbook, candle, trade history) has no authentication requirement. Only account-level operations (orders, balances) require API keys.

### 2.4 Rate Limits

| Resource / Group       | Limit                                   |
|------------------------|-----------------------------------------|
| Quotation API (ticker, orderbook, candle, trades) | 10 requests/second per IP |
| Exchange API (orders, account)   | 30 requests/second per API key |
| Order creation         | 8 requests/second per API key  |
| WebSocket connections  | 5 new connections/second              |
| WebSocket messages     | 5 messages/second, 100 messages/minute |

**Response Header:** `Remaining-Req: group=market; min=600; sec=9`
- `sec` = requests remaining in current second window
- `min` = requests remaining in current minute window

**HTTP 429** on limit exceeded; **HTTP 418** for repeated violators (with duration in response).

### 2.5 Data Format

| Field                | Type   | Description                              |
|----------------------|--------|------------------------------------------|
| `code`               | string | Market code (`KRW-BTC`)                 |
| `trade_price`        | number | Latest transaction price (KRW)           |
| `trade_volume`       | number | Latest trade quantity (BTC)              |
| `timestamp`          | integer | Server timestamp (Unix ms)              |
| `trade_timestamp`    | integer | Exact trade timestamp (Unix ms)          |
| `acc_trade_volume_24h` | number | 24h rolling volume                     |
| `change`             | string | `RISE`, `FALL`, or `EVEN`               |
| `stream_type`        | string | `SNAPSHOT` or `REALTIME`                |

### 2.6 Known Limitations

- **10 req/s ceiling** for quotation endpoints is strictly enforced. Multiple concurrent polling threads on the same IP will quickly hit this limit across all endpoints combined.
- **WebSocket 5 msg/s limit** applies to subscription messages sent to the server, not to messages received. Once subscribed, incoming stream data is unrestricted.
- **JWT expiry:** Exchange API JWT tokens expire; token refresh logic is required for long-running sessions.
- **Upbit breaches:** Upbit experienced a significant security incident in November 2019 (342,000 ETH stolen, approximately $49M at the time). Enhanced security measures and cold wallet policies were introduced post-incident. The exchange has operated without major breaches since, but monitor for ongoing API policy changes related to security hardening.

---

## 3. Coinone

**Type:** South Korean domestic exchange
**Quote currency:** KRW
**Market code format:** `quote_currency=KRW`, `target_currency=BTC` (path parameters)

### 3.1 REST API Endpoints

**Base URL:** `https://api.coinone.co.kr`

#### Ticker Endpoint — Single Symbol

```
GET https://api.coinone.co.kr/public/v2/ticker_new/{quote_currency}/{target_currency}
```

**Path Parameters:**

| Parameter         | Type   | Required | Description                 |
|-------------------|--------|----------|-----------------------------|
| `quote_currency`  | string | Yes      | Market base currency: `KRW` |
| `target_currency` | string | Yes      | Coin symbol: `BTC`          |

**Query Parameters:**

| Parameter         | Type    | Required | Description                                |
|-------------------|---------|----------|--------------------------------------------|
| `additional_data` | boolean | No       | Include previous day data (default: false) |

**Example Request:**
```
GET https://api.coinone.co.kr/public/v2/ticker_new/KRW/BTC
```

**Example Response:**
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

#### Ticker Endpoint — All Symbols

```
GET https://api.coinone.co.kr/public/v2/ticker_new/{quote_currency}
```

Returns all KRW-quoted tickers in a single call (`tickers` array contains all assets).

**Example Request:**
```
GET https://api.coinone.co.kr/public/v2/ticker_new/KRW
```

#### Orderbook Endpoint

```
GET https://api.coinone.co.kr/public/v2/orderbook/{quote_currency}/{target_currency}
```

**Query Parameters:**

| Parameter          | Type    | Required | Description                                    |
|--------------------|---------|----------|------------------------------------------------|
| `size`             | integer | No       | Depth: 5, 10, 15, or 20 (default: 15)         |
| `order_book_unit`  | number  | No       | Aggregation unit (default: 0.0, no aggregation)|

**Example Response:**
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

### 3.2 WebSocket Streaming

**WebSocket URL:** `wss://stream.coinone.co.kr`

Public WebSocket does not require authentication.

#### Subscription Message Format

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

| Field          | Type   | Description                                      |
|----------------|--------|--------------------------------------------------|
| `request_type` | string | `SUBSCRIBE` or `UNSUBSCRIBE` (uppercase required)|
| `channel`      | string | `TICKER`, `ORDERBOOK`, or `TRADE`                |
| `topic`        | object | `quote_currency` + `target_currency` fields      |
| `format`       | string | `DEFAULT` (full fields) or `SHORT` (compact)     |

#### Ticker Stream Response

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

#### Orderbook Stream Response

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

**Behavior:** Upon subscription, an initial snapshot is delivered. Subsequent messages are incremental updates sent only when the orderbook changes.

#### Heartbeat

The server closes idle connections after 30 minutes without a PING. Send a PING every 25 seconds:
```json
{"request_type": "PING"}
```

### 3.3 Authentication

| Endpoint type      | API Key required? | Method                                           |
|--------------------|-------------------|--------------------------------------------------|
| Public REST (v2)   | No                | None                                             |
| Public WebSocket   | No                | None                                             |
| Private REST (v2)  | Yes               | `X-COINONE-PAYLOAD` (base64 JSON) + `X-COINONE-SIGNATURE` (HMAC-SHA512) headers |
| Private REST (v2.1)| Yes               | UUID v4 nonce (prevents replay attacks)          |

### 3.4 Rate Limits

| Resource               | Limit                                           |
|------------------------|-------------------------------------------------|
| WebSocket connections  | Maximum 20 per IP (excess triggers 4290 close)  |
| WebSocket idle timeout | 30 minutes without PING                         |
| REST API (public)      | Not explicitly published; conservative estimate: ~10 req/s |

**Note:** Coinone does not publicly publish specific numerical REST rate limits in their documentation. Rate limit guidance is referenced as "API 요청건수 제한 안내" without specific numbers. Implement conservative retry-with-backoff.

### 3.5 Data Format

| Field            | Type   | Description                              |
|------------------|--------|------------------------------------------|
| `target_currency`| string | Coin symbol (`BTC`)                     |
| `quote_currency` | string | Market currency (`KRW`)                 |
| `last`           | string | Latest transaction price (KRW, string)  |
| `high`           | string | 24h high price (KRW, string)            |
| `low`            | string | 24h low price (KRW, string)             |
| `first`          | string | Opening price (KRW, string)             |
| `target_volume`  | string | 24h trading volume (BTC, string)        |
| `quote_volume`   | string | 24h volume in KRW (string)              |
| `timestamp`      | integer | Unix ms timestamp                       |

**Important:** Unlike Bithumb and Upbit, all numeric values in Coinone responses are returned as **strings**, not numbers. Parse with `float()` or `Decimal()`.

### 3.6 Known Limitations

- **String-encoded numbers:** All price and volume fields are JSON strings. Type conversion is required before arithmetic.
- **WebSocket reconnection:** Coinone does not auto-reconnect. Clients must re-subscribe on disconnect.
- **20-connection IP limit:** Running multiple development instances on the same IP may hit this limit quickly during testing.
- **Partial orderbook updates:** Orderbook WebSocket delivers only changed levels, not the full book. Clients must maintain a local orderbook state.
- **API version differences:** v2.0 uses camelCase responses; v2.1 uses snake_case for both request and response. Ensure you are using v2 (current) for all new implementations.

---

## 4. Binance

**Type:** International exchange
**Quote currency:** USDT
**Market code format:** `BTCUSDT`, `ETHUSDT` (no separator)

### 4.1 REST API Endpoints

**Base URLs:**
- Primary: `https://api.binance.com`
- Alternatives: `https://api-gcp.binance.com`, `https://api1.binance.com` – `https://api4.binance.com`
- Market data only (no trading): `https://data-api.binance.vision`

#### Ticker Price Endpoint (Lightweight)

```
GET https://api.binance.com/api/v3/ticker/price
```

**Query Parameters:**

| Parameter | Type   | Required | Description                                         |
|-----------|--------|----------|-----------------------------------------------------|
| `symbol`  | string | No       | Single symbol, e.g. `BTCUSDT`; omit for all symbols|
| `symbols` | string | No       | JSON array string, e.g. `["BTCUSDT","ETHUSDT"]`    |

**Request Weight:** 2 (single symbol), 4 (all symbols), 4 (multiple symbols)

**Example Request:**
```
GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
```

**Example Response (single):**
```json
{
  "symbol": "BTCUSDT",
  "price": "92450.15000000"
}
```

**Example Response (multiple):**
```json
[
  {"symbol": "BTCUSDT", "price": "92450.15000000"},
  {"symbol": "ETHUSDT", "price": "3215.82000000"}
]
```

#### 24-Hour Rolling Statistics

```
GET https://api.binance.com/api/v3/ticker/24hr
```

**Query Parameters:**

| Parameter | Type   | Required | Description                         |
|-----------|--------|----------|-------------------------------------|
| `symbol`  | string | No       | Single symbol                       |
| `symbols` | string | No       | JSON array of symbols               |
| `type`    | string | No       | `FULL` (default) or `MINI`          |

**Request Weight:**
- 1–20 symbols: 2
- 21–100 symbols: 40
- 101+ or all symbols: 80

**Example Response (FULL type):**
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

#### Orderbook Endpoint

```
GET https://api.binance.com/api/v3/depth
```

**Query Parameters:**

| Parameter | Type    | Required | Description                                          |
|-----------|---------|----------|------------------------------------------------------|
| `symbol`  | string  | Yes      | Market symbol, e.g. `BTCUSDT`                       |
| `limit`   | integer | No       | Depth: 5, 10, 20, 50, 100 (default), 500, 1000, 5000|

**Request Weight by limit:** 1–100 → 5; 101–500 → 25; 501–1000 → 50; 1001–5000 → 250

**Example Response:**
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

### 4.2 WebSocket Streaming

**WebSocket Base URLs:**
- `wss://stream.binance.com:9443`
- `wss://stream.binance.com:443`

#### Connection Methods

**Single stream:**
```
wss://stream.binance.com:9443/ws/btcusdt@ticker
```

**Combined streams:**
```
wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker
```

**Dynamic subscription (after connection):**
```json
{
  "method": "SUBSCRIBE",
  "params": ["btcusdt@ticker", "ethusdt@ticker"],
  "id": 1
}
```

#### Individual Symbol Ticker Stream

**Stream name:** `{symbol}@ticker` (lowercase symbol)

**Example:** `wss://stream.binance.com:9443/ws/btcusdt@ticker`

**Stream Response:**
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

**Field legend:**

| Field | Description                           |
|-------|---------------------------------------|
| `e`   | Event type (`24hrTicker`)            |
| `E`   | Event time (Unix ms)                  |
| `s`   | Symbol                                |
| `p`   | Price change (absolute)               |
| `P`   | Price change percent                  |
| `w`   | Weighted average price                |
| `x`   | First trade price before 24hr window  |
| `c`   | Last price (current price)            |
| `Q`   | Last trade quantity                   |
| `b`   | Best bid price                        |
| `B`   | Best bid quantity                     |
| `a`   | Best ask price                        |
| `A`   | Best ask quantity                     |
| `o`   | Open price (24h window start)         |
| `h`   | High price (24h)                      |
| `l`   | Low price (24h)                       |
| `v`   | Total base asset volume (24h)         |
| `q`   | Total quote asset volume (24h)        |
| `O`   | Statistics open time                  |
| `C`   | Statistics close time                 |
| `F`   | First trade ID                        |
| `L`   | Last trade ID                         |
| `n`   | Number of trades                      |

**Key price field:** `c` (last price, USDT)

#### Mini Ticker (Lightweight Alternative)

Stream: `btcusdt@miniTicker`

Contains only: `e`, `E`, `s`, `c` (close), `o` (open), `h` (high), `l` (low), `v` (volume), `q` (quote volume).

**Deprecation notice:** The `!ticker@arr` (all market tickers) stream was deprecated on 2025-11-14. Use `{symbol}@ticker` for individual symbols or `!miniTicker@arr` for all symbols.

### 4.3 Authentication

| Endpoint type    | API Key required? | Method                                              |
|------------------|-------------------|-----------------------------------------------------|
| Public REST      | No                | None — market data endpoints are open               |
| Public WebSocket | No                | None                                                |
| Private REST     | Yes               | `X-MBX-APIKEY` header + HMAC-SHA256 signature on query string |
| Private WebSocket| Yes               | `listenKey` from `/api/v3/userDataStream` endpoint  |

### 4.4 Rate Limits

**REST API (per IP):**

| Limit type       | Limit                                |
|------------------|--------------------------------------|
| REQUEST_WEIGHT   | 6,000 weight units per minute        |
| RAW_REQUESTS     | 61,000 requests per 5 minutes        |

**Response headers:**
- `X-MBX-USED-WEIGHT-1M`: current weight used in this minute

**WebSocket connection limits:**

| Limit type                  | Limit                               |
|-----------------------------|-------------------------------------|
| Incoming messages per connection | 5 messages/second             |
| Streams per connection      | 1,024 maximum                       |
| New connections per IP (5 min) | 300 connections                  |
| Connection lifetime         | 24 hours (must reconnect)           |

**Important endpoints and their weights:**
- `GET /api/v3/ticker/price` (single): weight 2
- `GET /api/v3/ticker/price` (all): weight 4
- `GET /api/v3/ticker/24hr` (single): weight 2
- `GET /api/v3/ticker/24hr` (all symbols): weight 80
- `GET /api/v3/depth` (limit 100): weight 5

**HTTP 429** on rate limit exceeded; IP bans scale from 2 minutes to 3 days for repeated violations.

### 4.5 Data Format

| Field      | REST field    | WS field | Type   | Description          |
|------------|---------------|----------|--------|----------------------|
| Symbol     | `symbol`      | `s`      | string | `BTCUSDT`            |
| Last price | `lastPrice`   | `c`      | string | Current price (USDT) |
| High 24h   | `highPrice`   | `h`      | string | 24h high             |
| Low 24h    | `lowPrice`    | `l`      | string | 24h low              |
| Volume 24h | `volume`      | `v`      | string | Base asset volume    |
| Quote vol  | `quoteVolume` | `q`      | string | Quote (USDT) volume  |
| Timestamp  | `closeTime`   | `C`      | integer | Unix ms             |

**Important:** All numeric values in Binance responses are **JSON strings** (e.g., `"92450.15000000"`). Parse with `float()` before arithmetic.

### 4.6 Known Limitations

- **Abbreviated WS field names:** The ticker stream uses single-character abbreviated field names (`c`, `h`, `l`, etc.) that differ from REST field names (`lastPrice`, `highPrice`, `lowPrice`). Normalizers must handle both schemas.
- **24-hour rolling window:** The ticker statistics use a 24-hour rolling window (not UTC day reset). This affects volume and price change calculations.
- **WebSocket 24h expiry:** WebSocket connections are automatically terminated after 24 hours. Implement automatic reconnection.
- **Regional restrictions:** Binance is not available in the USA, Ontario (Canada), and several other jurisdictions. The arbitrage monitor targeting KRW markets is unaffected, but VPN setups in those regions may need to use `data-api.binance.vision` for public market data.
- **`!ticker@arr` deprecation:** The all-market ticker stream was deprecated. Do not use it.

---

## 5. Bybit

**Type:** International exchange
**Quote currency:** USDT
**Market code format:** `BTCUSDT`, `ETHUSDT` (no separator)

### 5.1 REST API Endpoints

**Base URL:** `https://api.bybit.com`
**Testnet:** `https://api-testnet.bybit.com`

All endpoints use `/v5/` prefix (V5 is the current production API since 2023).

#### Ticker Endpoint

```
GET https://api.bybit.com/v5/market/tickers
```

**Query Parameters:**

| Parameter | Type   | Required | Description                                  |
|-----------|--------|----------|----------------------------------------------|
| `category`| string | Yes      | `spot`, `linear`, `inverse`, or `option`     |
| `symbol`  | string | No       | Symbol, e.g. `BTCUSDT`; omit for all         |

**Example Request:**
```
GET https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT
```

**Example Response:**
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

**Key price field:** `lastPrice` (string, USDT)
**Timestamp field:** `time` (top-level, Unix ms)

#### Orderbook Endpoint

```
GET https://api.bybit.com/v5/market/orderbook
```

**Query Parameters:**

| Parameter | Type    | Required | Description                                |
|-----------|---------|----------|--------------------------------------------|
| `category`| string  | Yes      | `spot`, `linear`, `inverse`, `option`      |
| `symbol`  | string  | Yes      | Symbol, e.g. `BTCUSDT`                    |
| `limit`   | integer | No       | Depth: 1–50 (spot default 1), max 200      |

**Example Response:**
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

### 5.2 WebSocket Streaming

**WebSocket URL (Spot — Mainnet):** `wss://stream.bybit.com/v5/public/spot`
**WebSocket URL (Testnet):** `wss://stream-testnet.bybit.com/v5/public/spot`
**Linear (USDT Perpetual):** `wss://stream.bybit.com/v5/public/linear`

Public WebSocket topics require no authentication.

#### Subscription Message Format

```json
{
  "op": "subscribe",
  "args": ["tickers.BTCUSDT"]
}
```

Multiple subscriptions in one message:
```json
{
  "req_id": "my-sub-001",
  "op": "subscribe",
  "args": ["tickers.BTCUSDT", "tickers.ETHUSDT"]
}
```

| Field    | Type   | Description                                   |
|----------|--------|-----------------------------------------------|
| `op`     | string | `subscribe` or `unsubscribe`                  |
| `args`   | array  | List of topic strings                         |
| `req_id` | string | Optional request identifier for correlation   |

#### Ticker Stream Response

**Topic:** `tickers.{SYMBOL}`
**Push frequency:** Every 50 ms (fastest available across all 5 exchanges)
**Data type:** Snapshot only (no delta updates for spot tickers)

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

**Field descriptions:**

| Field            | Description                                    |
|------------------|------------------------------------------------|
| `topic`          | Stream topic identifier                        |
| `ts`             | Server timestamp (Unix ms)                     |
| `type`           | Always `snapshot` for spot tickers             |
| `cs`             | Cross-sequence number                          |
| `symbol`         | Trading pair                                   |
| `lastPrice`      | Current price (USDT)                           |
| `highPrice24h`   | 24h high                                       |
| `lowPrice24h`    | 24h low                                        |
| `prevPrice24h`   | Price from 24 hours ago                        |
| `volume24h`      | 24h base asset volume                          |
| `turnover24h`    | 24h quote (USDT) volume                        |
| `price24hPcnt`   | 24h price change percent                       |
| `usdIndexPrice`  | USD index price                                |

#### Heartbeat / Ping-Pong

Send every 20 seconds to maintain connection:
```json
{"req_id": "heartbeat-001", "op": "ping"}
```

Server response:
```json
{"success": true, "ret_msg": "pong", "conn_id": "abc123", "op": "ping"}
```

### 5.3 Authentication

| Endpoint type    | API Key required? | Method                                          |
|------------------|-------------------|-------------------------------------------------|
| Public REST      | No                | None                                            |
| Public WebSocket | No                | None                                            |
| Private REST     | Yes               | `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP`, `X-BAPI-SIGN` headers + HMAC-SHA256 |
| Private WebSocket| Yes               | Auth message after connection with API key + signature |

### 5.4 Rate Limits

**REST API (per IP):**

| Resource                    | Limit                             |
|-----------------------------|-----------------------------------|
| HTTP requests               | 600 requests per 5-second window  |
| IP ban on violation         | 10-minute ban                     |

**REST API (per UID — order/trading endpoints):**

| Endpoint type               | Limit                             |
|-----------------------------|-----------------------------------|
| Create/amend/cancel orders  | 10–20 requests/second             |
| Order history queries       | 50 requests/second                |
| Position queries            | 50 requests/second                |

**WebSocket connection limits:**

| Resource                    | Limit                             |
|-----------------------------|-----------------------------------|
| New connections (5 min)     | Max 500 per 5-minute window       |
| Total connections per IP    | 1,000 (counted per market type)   |
| Args per subscription message| Max 10                           |
| Args character length       | Max 21,000 characters             |

**Important:** WebSocket requests are **not counted** against REST rate limits. Bybit explicitly recommends WebSocket for market data to avoid REST exhaustion.

**Response headers:**
- `X-Bapi-Limit-Status`: remaining requests
- `X-Bapi-Limit`: current limit
- `X-Bapi-Limit-Reset-Timestamp`: when the limit resets

### 5.5 Data Format

| Field          | Type   | Description                              |
|----------------|--------|------------------------------------------|
| `symbol`       | string | `BTCUSDT`                               |
| `lastPrice`    | string | Current price (USDT)                    |
| `highPrice24h` | string | 24h high (USDT)                         |
| `lowPrice24h`  | string | 24h low (USDT)                          |
| `volume24h`    | string | Base asset volume (BTC)                 |
| `turnover24h`  | string | Quote volume (USDT)                     |
| `ts`           | integer| Server timestamp (Unix ms)              |

**Important:** Like Binance, all numeric values are returned as **strings**. Parse with `float()` before arithmetic.

### 5.6 Known Limitations

- **Spot tickers are snapshot-only:** Unlike derivatives markets which support delta updates, spot ticker WebSocket delivers full snapshots every 50 ms. This is higher bandwidth but simpler to process.
- **50 ms push frequency:** While the fastest among the five exchanges in this project, this means up to a 50 ms delay relative to real-time trades.
- **500 connections / 5 min limit:** High-frequency reconnection (e.g., during testing) can trigger this limit quickly.
- **No regional restrictions for public market data:** Bybit operates globally; public WebSocket streams are accessible without VPN from any region.

---

## 6. Exchange Comparison Matrix

| Feature                      | Bithumb (v2)            | Upbit                   | Coinone                 | Binance                 | Bybit                   |
|------------------------------|-------------------------|-------------------------|-------------------------|-------------------------|-------------------------|
| **Quote Currency**           | KRW                     | KRW                     | KRW                     | USDT                    | USDT                    |
| **Market Code Format**       | `KRW-BTC`               | `KRW-BTC`               | path: `KRW/BTC`         | `BTCUSDT`               | `BTCUSDT`               |
| **REST Base URL**            | api.bithumb.com/v1/     | api.upbit.com/v1/       | api.coinone.co.kr/public/v2/ | api.binance.com/api/v3/ | api.bybit.com/v5/       |
| **WebSocket URL**            | ws-api.bithumb.com/websocket/v1 | api.upbit.com/websocket/v1 | stream.coinone.co.kr | stream.binance.com:9443/ws/ | stream.bybit.com/v5/public/spot |
| **Auth for public data**     | None                    | None                    | None                    | None                    | None                    |
| **REST Rate Limit**          | ~10 req/s (undocumented)| 10 req/s per IP        | Not published           | 6,000 weight/min        | 600 req/5-sec           |
| **WS Connection Limit**      | 10 new/sec per IP       | 5 new/sec               | 20 total per IP         | 300/5-min per IP        | 500/5-min               |
| **WS Message Limit**         | 5/sec, 100/min          | 5/sec, 100/min          | Not published           | 5 msg/sec per connection| Not counted against REST|
| **Ticker Push Frequency**    | Real-time (event-based) | Real-time (event-based) | On change               | 1s (rolling stats)      | 50 ms                   |
| **Numeric type in JSON**     | number                  | number                  | **string**              | **string**              | **string**              |
| **Subscription format**      | JSON array with ticket  | JSON array with ticket  | Single JSON object      | JSON object with op/params | JSON object with op/args |
| **Heartbeat required**       | Yes (implicit)          | Implicit                | Yes (PING every 25s)    | Ping implicit           | Yes (PING every 20s)    |
| **Price field name (ticker)**| `trade_price`           | `trade_price`           | `last`                  | `c` (WS), `lastPrice` (REST) | `lastPrice`      |
| **Volume field (24h)**       | `acc_trade_volume_24h`  | `acc_trade_volume_24h`  | `target_volume`         | `v` (WS), `volume` (REST) | `volume24h`          |
| **Timestamp field**          | `timestamp`             | `timestamp`             | `timestamp`             | `E` (WS), `closeTime` (REST) | `ts`             |

---

## 7. Kimchi Premium Calculation Methodology

The "Kimchi Premium" (김치 프리미엄) refers to the percentage premium at which a cryptocurrency trades on Korean exchanges (KRW-denominated) relative to international exchanges (USDT-denominated). It arises from South Korea's capital controls, regulatory environment, and demand/supply imbalance.

### 7.1 Formula

```
kimchi_premium_pct = ((krw_price / usd_krw_rate) / usdt_price - 1) × 100
```

Where:
- `krw_price` = latest trade price on a domestic exchange (KRW), e.g. Bithumb BTC price
- `usd_krw_rate` = current KRW per 1 USD exchange rate (e.g. 1,320.50 KRW/USD)
- `usdt_price` = latest trade price on an international exchange (USDT), e.g. Binance BTC price
- The formula converts KRW price to a USD-equivalent before comparing

**Example:**
```
Bithumb BTC:  88,200,000 KRW
Binance BTC:  65,000 USDT ≈ 65,000 USD (assuming USDT ≈ USD)
KRW/USD rate: 1,350 KRW per USD

BTC in USD via Bithumb: 88,200,000 / 1,350 = 65,333.33 USD
Kimchi Premium: (65,333.33 / 65,000 - 1) × 100 = +0.51%
```

### 7.2 Simplifying Assumptions

**USDT ≈ USD (1:1 peg assumption):**
Tether (USDT) maintains a soft peg to USD and typically trades within ±0.1% of USD. For real-time arbitrage monitoring, treating 1 USDT = 1 USD is standard practice. If required precision demands it, a live USDT/USD depeg check can be incorporated using Binance's `USDTUSD` pair or checking USDT price against a fiat-USD reference, but this adds complexity for negligible benefit.

### 7.3 Implementation Architecture

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

### 7.4 Cross-Exchange Spread (Same Currency)

For pairs within the same currency zone (e.g., Bithumb vs Upbit), no FX conversion is needed:

```
spread_pct = (price_a / price_b - 1) × 100
```

This is a simpler calculation and should be tracked separately from the Kimchi Premium metric.

### 7.5 Data Freshness Considerations

Spread calculations are only valid when both price inputs are recent. Implement a staleness threshold:

```python
MAX_PRICE_AGE_MS = 5000  # 5 seconds

def is_valid_for_spread(price_a_ts: int, price_b_ts: int) -> bool:
    now_ms = int(time.time() * 1000)
    return (
        (now_ms - price_a_ts) < MAX_PRICE_AGE_MS and
        (now_ms - price_b_ts) < MAX_PRICE_AGE_MS
    )
```

If either price is stale (e.g., a WebSocket disconnection), suppress the spread calculation and surface an alert rather than display a stale spread.

---

## 8. KRW/USD Exchange Rate API Recommendations

Converting KRW prices to USD-equivalent values requires a reliable KRW/USD rate source. Three options are evaluated below.

### 8.1 Option A — ExchangeRate-API (Recommended)

**Provider:** ExchangeRate-API (exchangerate-api.com)
**Free tier endpoint:** `https://v6.exchangerate-api.com/v6/{API_KEY}/latest/USD`
**Open access (no key):** `https://open.er-api.com/v6/latest/USD`

**Example Request (open access, no key required):**
```
GET https://open.er-api.com/v6/latest/USD
```

**Example Response (abbreviated):**
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

**Extract KRW rate:** `response["rates"]["KRW"]`
**Update frequency:** Every 24 hours (open access) / every hour (free-tier with key)

| Tier          | Rate limit              | Update frequency | Cost   |
|---------------|-------------------------|------------------|--------|
| Open access   | No documented limit     | 24 hours         | Free   |
| Free (API key)| 1,500 requests/month    | 1 hour           | Free   |
| Starter       | 30,000 requests/month   | 1 minute         | ~$5/mo |

**Recommendation:** For a real-time arbitrage monitor, the **open access** endpoint updated every 24 hours is acceptable because KRW/USD moves slowly (typically < 1% per day). Cache the rate and refresh every 60 seconds against this endpoint; the rate will only change once per 24 hours regardless.

For tighter accuracy (e.g., during high-volatility KRW periods), upgrade to the Starter plan for minute-level updates.

### 8.2 Option B — Binance USDT/KRW Pair

Binance does not directly list KRW pairs in most regions. However, some indirect methods exist:

- **Binance P2P market** quotes KRW rates but is not available via public API in a structured form.
- **USDKRW synthetic rate** can be computed from Binance's BUSD or USDC pairs on Korean markets, but this requires cross-referencing multiple endpoints.

**Assessment:** Not recommended. No clean, stable API endpoint provides KRW/USD rate from Binance.

### 8.3 Option C — Bank of Korea API (한국은행 경제통계시스템)

The Bank of Korea provides official exchange rate data via their ECOS API:

**Endpoint:** `https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/1/1/064Y001/D/{YYYYMMDD}/{YYYYMMDD}/0000001`

**Registration:** Required — free API key from ecos.bok.or.kr
**Update frequency:** Daily (official settlement rate)
**Data:** Official daily USD/KRW reference rate (고시환율)

**Assessment:** Suitable for daily reconciliation and audit trails, but the once-daily update makes it unsuitable for real-time spread monitoring. Use as a sanity check against the ExchangeRate-API value, not as the primary source.

### 8.4 Final Recommendation

| Scenario                              | Recommended Source            |
|---------------------------------------|-------------------------------|
| Real-time arbitrage (primary)         | ExchangeRate-API open access  |
| High-volatility periods / production  | ExchangeRate-API free key tier|
| Daily audit / reconciliation          | Bank of Korea ECOS API        |

**Implementation pattern:**

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

## 9. Error Handling and Resilience Notes

### 9.1 Common WebSocket Failure Patterns

| Exchange | Known failure pattern                              | Recommended handling                            |
|----------|----------------------------------------------------|-------------------------------------------------|
| Bithumb  | Server-side maintenance disconnects               | Exponential backoff reconnect (2s → 64s)        |
| Upbit    | 418 on sustained rate limit abuse                 | Honor `Retry-After` header; pause all requests  |
| Coinone  | 4290 close code on >20 connections from same IP  | Enforce single connection per IP in code         |
| Binance  | 24-hour WebSocket expiry                          | Schedule daily reconnect; use `/ws/` ping frame |
| Bybit    | 500 connections/5-min IP limit during reconnect storms | Backoff on repeated connection failures      |

### 9.2 Partial Data Scenarios

If one exchange's WebSocket drops while others remain connected, the spread calculation for that exchange pair should be suppressed (marked as "stale") rather than computed with a cached old price. Implement per-exchange freshness tracking.

### 9.3 Rate Limit Strategy Summary

| Exchange | REST strategy                | WebSocket strategy                    |
|----------|------------------------------|---------------------------------------|
| Bithumb  | Max 1 req/200ms              | Prefer WS; 5 sub-messages/sec         |
| Upbit    | Max 10 req/sec (quota header)| Prefer WS; 5 msg/sec hard limit       |
| Coinone  | Conservative; max 1 req/sec  | Prefer WS; maintain single connection |
| Binance  | Monitor `X-MBX-USED-WEIGHT`  | Use combined stream (1 connection)    |
| Bybit    | Monitor `X-Bapi-Limit-Status`| WS recommended; not rate-limited      |

---

## References

- Bithumb Official API Docs: https://apidocs.bithumb.com/
- Bithumb WebSocket Basic Info: https://apidocs.bithumb.com/reference/websocket-기본-정보
- Upbit Developer Center: https://global-docs.upbit.com/
- Upbit Rate Limits: https://global-docs.upbit.com/reference/rate-limits
- Upbit WebSocket Best Practices: https://global-docs.upbit.com/docs/websocket-best-practice
- Coinone Developer Center: https://docs.coinone.co.kr/
- Coinone Ticker Endpoint: https://docs.coinone.co.kr/reference/ticker
- Coinone Public WebSocket: https://docs.coinone.co.kr/reference/public-websocket-1
- Binance Spot API Docs (REST): https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
- Binance WebSocket Streams: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- Binance Spot API GitHub: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md
- Bybit V5 Get Tickers: https://bybit-exchange.github.io/docs/v5/market/tickers
- Bybit WebSocket Connect: https://bybit-exchange.github.io/docs/v5/ws/connect
- Bybit WebSocket Ticker: https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
- Bybit Rate Limits: https://bybit-exchange.github.io/docs/v5/rate-limit
- ExchangeRate-API: https://www.exchangerate-api.com/
- CCXT Bithumb implementation (reference): https://github.com/ccxt/ccxt/blob/master/python/ccxt/async_support/bithumb.py
