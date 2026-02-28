/**
 * TypeScript const-object enums matching Python StrEnums in app/utils/enums.py.
 *
 * Using `as const` + type union pattern instead of TypeScript enums to:
 * - Preserve string values at runtime (no transpilation surprises)
 * - Allow exhaustive checks with union types
 * - Match the exact string values sent over the API/WebSocket
 */

export const ExchangeId = {
  BITHUMB: "bithumb",
  UPBIT: "upbit",
  COINONE: "coinone",
  BINANCE: "binance",
  BYBIT: "bybit",
} as const;
export type ExchangeId = (typeof ExchangeId)[keyof typeof ExchangeId];

export const Currency = {
  KRW: "KRW",
  USDT: "USDT",
} as const;
export type Currency = (typeof Currency)[keyof typeof Currency];

export const ConnectorState = {
  DISCONNECTED: "DISCONNECTED",
  CONNECTING: "CONNECTING",
  CONNECTED: "CONNECTED",
  SUBSCRIBING: "SUBSCRIBING",
  ACTIVE: "ACTIVE",
  WAIT_RETRY: "WAIT_RETRY",
} as const;
export type ConnectorState = (typeof ConnectorState)[keyof typeof ConnectorState];

export const SpreadType = {
  KIMCHI_PREMIUM: "kimchi_premium",
  SAME_CURRENCY: "same_currency",
} as const;
export type SpreadType = (typeof SpreadType)[keyof typeof SpreadType];

export const AlertDirection = {
  ABOVE: "above",
  BELOW: "below",
  BOTH: "both",
} as const;
export type AlertDirection = (typeof AlertDirection)[keyof typeof AlertDirection];

export const AlertSeverity = {
  INFO: "info",
  WARNING: "warning",
  CRITICAL: "critical",
} as const;
export type AlertSeverity = (typeof AlertSeverity)[keyof typeof AlertSeverity];

export const FxRateSource = {
  UPBIT: "upbit",
  EXCHANGERATE_API: "exchangerate-api",
} as const;
export type FxRateSource = (typeof FxRateSource)[keyof typeof FxRateSource];

export const WsEventType = {
  WELCOME: "welcome",
  SNAPSHOT: "snapshot",
  PRICE_UPDATE: "price_update",
  SPREAD_UPDATE: "spread_update",
  ALERT_TRIGGERED: "alert_triggered",
  EXCHANGE_STATUS: "exchange_status",
  HEARTBEAT: "heartbeat",
  ERROR: "error",
  SUBSCRIBE: "subscribe",
  SUBSCRIBED: "subscribed",
  UNSUBSCRIBE: "unsubscribe",
  UNSUBSCRIBED: "unsubscribed",
  PONG: "pong",
} as const;
export type WsEventType = (typeof WsEventType)[keyof typeof WsEventType];

export const WsChannel = {
  PRICES: "prices",
  SPREADS: "spreads",
  ALERTS: "alerts",
  EXCHANGE_STATUS: "exchange_status",
} as const;
export type WsChannel = (typeof WsChannel)[keyof typeof WsChannel];
