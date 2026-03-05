/**
 * Shared TypeScript interfaces matching Python Pydantic schemas in app/schemas/.
 *
 * All numeric price/spread values are strings (Decimal-as-string) to preserve
 * precision — never use parseFloat() for display; use toLocaleString() or a
 * dedicated formatting library.
 */

import type {
  AlertDirection,
  AlertSeverity,
  ConnectorState,
  Currency,
  ExchangeId,
  FxRateSource,
  SpreadType,
  WsChannel,
  WsEventType,
} from "./enums";

// ── Common ──────────────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  status: "ok";
  data: T;
  timestamp_ms: number;
}

export interface ApiError {
  status: "error";
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  timestamp_ms: number;
}

export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface PaginatedResponse<T> {
  status: "ok";
  data: T[];
  pagination: PaginationMeta;
  timestamp_ms: number;
}

// ── Price ───────────────────────────────────────────────────────────────────────

export interface PriceEntry {
  exchange: ExchangeId;
  symbol: string;
  price: string;          // Decimal-as-string for precision
  currency: Currency;
  bid_price: string | null;
  ask_price: string | null;
  volume_24h: string;
  timestamp_ms: number;
  received_at_ms: number;
  is_stale: boolean;
}

export interface FxRateInfo {
  rate: string;
  source: FxRateSource;
  is_stale: boolean;
  last_update_ms: number;
}

export interface PricesData {
  prices: PriceEntry[];
  fx_rate: FxRateInfo;
}

export interface PriceHistoryEntry {
  exchange: ExchangeId;
  symbol: string;
  price: string;
  currency: Currency;
  volume_24h: string;
  timestamp_ms: number;
  created_at: string;
}

// ── Spread ──────────────────────────────────────────────────────────────────────

export interface SpreadEntry {
  exchange_a: ExchangeId;
  exchange_b: ExchangeId;
  symbol: string;
  spread_pct: string;
  spread_type: SpreadType;
  is_stale: boolean;
  stale_reason: string | null;
  price_a: string;
  price_a_currency: Currency;
  price_b: string;
  price_b_currency: Currency;
  fx_rate: string | null;
  fx_source: FxRateSource | null;
  timestamp_ms: number;
}

export interface SpreadMatrixSummary {
  symbol: string;
  max_spread: {
    pair: string;
    spread_pct: string;
    type: SpreadType;
  };
  min_spread: {
    pair: string;
    spread_pct: string;
    type: SpreadType;
  };
  stale_pairs: number;
  total_pairs: number;
}

export interface SpreadsData {
  spreads: SpreadEntry[];
  matrix_summary: SpreadMatrixSummary | null;
}

export interface SpreadHistoryEntry {
  exchange_a: ExchangeId;
  exchange_b: ExchangeId;
  symbol: string;
  spread_pct: string;
  spread_type: SpreadType;
  is_stale: boolean;
  fx_rate: string | null;
  fx_source: FxRateSource | null;
  timestamp_ms: number;
  created_at: string;
}

// ── Alert Config ────────────────────────────────────────────────────────────────

export interface AlertConfig {
  id: number;
  chat_id: number;
  symbol: string | null;
  exchange_a: ExchangeId | null;
  exchange_b: ExchangeId | null;
  threshold_pct: string;
  direction: AlertDirection;
  cooldown_minutes: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_triggered_at: string | null;
  trigger_count: number;
}

export interface AlertConfigCreate {
  chat_id?: number;
  symbol?: string | null;
  exchange_a?: ExchangeId | null;
  exchange_b?: ExchangeId | null;
  threshold_pct: number;
  direction: AlertDirection;
  cooldown_minutes?: number;
  enabled?: boolean;
}

export interface AlertConfigUpdate {
  symbol?: string | null;
  exchange_a?: ExchangeId | null;
  exchange_b?: ExchangeId | null;
  threshold_pct?: number;
  direction?: AlertDirection;
  cooldown_minutes?: number;
  enabled?: boolean;
}

export interface AlertHistoryEntry {
  id: number;
  alert_config_id: number;
  exchange_a: ExchangeId;
  exchange_b: ExchangeId;
  symbol: string;
  spread_pct: string;
  spread_type: SpreadType;
  threshold_pct: string;
  direction: AlertDirection;
  price_a: string;
  price_b: string;
  fx_rate: string | null;
  fx_source: FxRateSource | null;
  message_text: string;
  telegram_delivered: boolean;
  telegram_message_id: number | null;
  created_at: string;
}

// ── Exchange ─────────────────────────────────────────────────────────────────────

export interface ExchangeStatus {
  id: ExchangeId;
  name: string;
  currency: Currency;
  state: ConnectorState;
  ws_url: string;
  last_message_ms: number | null;
  latency_ms: number | null;
  reconnect_count: number;
  connected_since_ms: number | null;
  is_stale: boolean;
  stale_threshold_ms: number;
  fallback_mode: string | null;
  supported_symbols: string[];
}

// ── Symbols ─────────────────────────────────────────────────────────────────────

export interface TrackedSymbol {
  symbol: string;
  enabled: boolean;
  exchange_coverage: Record<ExchangeId, boolean>;
  created_at: string;
}

// ── Health ───────────────────────────────────────────────────────────────────────

export interface HealthData {
  server: {
    uptime_seconds: number;
    version: string;
    python_version: string;
    started_at: string;
  };
  exchanges: {
    total: number;
    connected: number;
    disconnected: number;
    summary: Record<ExchangeId, ConnectorState>;
  };
  database: {
    status: string;
    size_mb: number;
    wal_size_mb: number;
  };
  fx_rate: FxRateInfo;
  tracked_symbols: string[];
  active_alerts: number;
  dashboard_clients: number;
}

// ── Preferences ─────────────────────────────────────────────────────────────────

export interface DashboardPreferences {
  default_symbol: string;
  visible_exchanges: ExchangeId[];
  spread_matrix_mode: "percentage" | "absolute";
  chart_interval: "10s" | "1m" | "5m" | "1h";
  theme: "dark" | "light";
  min_spread_pct: number;
}

export interface NotificationPreferences {
  telegram_enabled: boolean;
  telegram_chat_id: number | null;
  sound_enabled: boolean;
}

export interface UserPreferences {
  dashboard: DashboardPreferences;
  notifications: NotificationPreferences;
  timezone: string;
  locale: "ko-KR" | "en-US";
}

// ── Asset Status ─────────────────────────────────────────────────────────────

export interface NetworkInfoEntry {
  network: string;
  deposit_enabled: boolean;
  withdraw_enabled: boolean;
  min_withdraw: string | null;
  withdraw_fee: string | null;
  confirmation_count: number | null;
}

export interface AssetStatusEntry {
  exchange: ExchangeId;
  symbol: string;
  deposit_enabled: boolean;
  withdraw_enabled: boolean;
  networks: NetworkInfoEntry[];
  updated_at_ms: number;
}

// ── Gate.io Lending ──────────────────────────────────────────────────────────

export interface GateLendingEntry {
  currency: string;
  amount: string;
  min_amount: string;
  rate: string;
  rate_day: string;
  leverage: string;
  borrowable: boolean;
}

// ── WebSocket Messages ──────────────────────────────────────────────────────────

export interface WsMessage<T = unknown> {
  type: WsEventType;
  data: T;
  seq: number;
  timestamp_ms: number;
}

export interface WsSubscribeMessage {
  type: "subscribe";
  symbols?: string[];
  channels?: WsChannel[];
}

export interface WsUnsubscribeMessage {
  type: "unsubscribe";
  symbols?: string[];
}

export interface WsPongMessage {
  type: "pong";
}

// Server-to-client payload types

export interface WsWelcomeData {
  server_version: string;
  available_symbols: string[];
  exchanges: ExchangeId[];
  heartbeat_interval_ms: number;
}

export interface WsSnapshotData {
  prices: PriceEntry[];
  spreads: SpreadEntry[];
  exchange_statuses: {
    exchange: ExchangeId;
    state: ConnectorState;
    latency_ms: number | null;
    last_message_ms: number | null;
  }[];
  fx_rate: FxRateInfo | null;
}

export interface WsAlertTriggeredData {
  alert_config_id: number;
  exchange_a: ExchangeId;
  exchange_b: ExchangeId;
  symbol: string;
  spread_pct: string;
  spread_type: SpreadType;
  threshold_pct: string;
  direction: AlertDirection;
  severity: AlertSeverity;
  fx_rate: string | null;
  fx_source: FxRateSource | null;
  telegram_delivered: boolean;
  timestamp_ms: number;
}

export interface WsExchangeStatusData {
  exchange: ExchangeId;
  state: ConnectorState;
  previous_state: ConnectorState;
  latency_ms: number | null;
  last_message_ms: number | null;
  reconnect_attempt: number;
  is_stale: boolean;
  fallback_mode: string | null;
  reason: string | null;
}

export interface WsHeartbeatData {
  server_time_ms: number;
}

export interface WsErrorData {
  code: string;
  message: string;
  original_message_type: string;
}
