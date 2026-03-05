/**
 * API client — typed fetch wrapper for all REST endpoints.
 *
 * Base URL: /api/v1 (proxied to http://localhost:8000 via Vite in dev)
 *
 * Usage:
 *   const health = await api.get<HealthData>("/health");
 *   const alert = await api.post<AlertConfig>("/alerts", body);
 */

import type {
  AlertConfig,
  AlertConfigCreate,
  AlertConfigUpdate,
  AlertHistoryEntry,
  AssetStatusEntry,
  ExchangeStatus,
  GateLendingEntry,
  HealthData,
  PaginatedResponse,
  PricesData,
  SpreadsData,
  TrackedSymbol,
  UserPreferences,
} from "@/types";

const BASE_URL = "/api/v1";

// ── Generic fetch wrapper ──────────────────────────────────────────────────────

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const response = await fetch(url.toString(), {
    method,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiRequestError(response.status, errorData);
  }

  return response.json() as Promise<T>;
}

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly data: unknown,
  ) {
    super(`API request failed with status ${status}`);
    this.name = "ApiRequestError";
  }
}

// ── Typed API methods ──────────────────────────────────────────────────────────

export const api = {
  // Health
  getHealth: () =>
    request<{ status: string; data: HealthData; timestamp_ms: number }>("GET", "/health"),

  // Exchanges
  getExchanges: () =>
    request<{ status: string; data: ExchangeStatus[]; timestamp_ms: number }>("GET", "/exchanges"),

  // Prices
  getPrices: (params?: { symbols?: string; exchanges?: string }) =>
    request<{ status: string; data: PricesData; timestamp_ms: number }>("GET", "/prices", undefined, params),

  getPricesBySymbol: (symbol: string, params?: { exchanges?: string }) =>
    request<{ status: string; data: PricesData; timestamp_ms: number }>(
      "GET",
      `/prices/${symbol}`,
      undefined,
      params,
    ),

  getPriceHistory: (params: {
    symbol: string;
    exchange?: string;
    start_time?: number;
    end_time?: number;
    interval?: string;
    limit?: number;
    offset?: number;
  }) =>
    request<PaginatedResponse<unknown>>("GET", "/prices/history", undefined, params as Record<string, string | number | boolean | undefined>),

  // Spreads
  getSpreads: (params?: { symbols?: string; spread_type?: string; include_stale?: boolean }) =>
    request<{ status: string; data: SpreadsData; timestamp_ms: number }>("GET", "/spreads", undefined, params as Record<string, string | number | boolean | undefined>),

  getSpreadHistory: (params: {
    symbol: string;
    exchange_a?: string;
    exchange_b?: string;
    spread_type?: string;
    start_time?: number;
    end_time?: number;
    interval?: string;
    limit?: number;
    offset?: number;
  }) =>
    request<PaginatedResponse<unknown>>("GET", "/spreads/history", undefined, params as Record<string, string | number | boolean | undefined>),

  // Alerts
  listAlerts: (params?: { enabled?: boolean; symbol?: string; limit?: number; offset?: number }) =>
    request<PaginatedResponse<AlertConfig>>("GET", "/alerts", undefined, params as Record<string, string | number | boolean | undefined>),

  createAlert: (body: AlertConfigCreate) =>
    request<{ status: string; data: AlertConfig; timestamp_ms: number }>("POST", "/alerts", body),

  getAlert: (id: number) =>
    request<{ status: string; data: AlertConfig; timestamp_ms: number }>("GET", `/alerts/${id}`),

  updateAlert: (id: number, body: AlertConfigUpdate) =>
    request<{ status: string; data: AlertConfig; timestamp_ms: number }>("PUT", `/alerts/${id}`, body),

  deleteAlert: (id: number) =>
    request<{ status: string; data: { deleted_id: number; message: string }; timestamp_ms: number }>(
      "DELETE",
      `/alerts/${id}`,
    ),

  getAlertHistory: (params?: {
    alert_config_id?: number;
    symbol?: string;
    delivered?: boolean;
    start_time?: number;
    end_time?: number;
    limit?: number;
    offset?: number;
  }) =>
    request<PaginatedResponse<AlertHistoryEntry>>("GET", "/alerts/history", undefined, params as Record<string, string | number | boolean | undefined>),

  // Symbols
  getSymbols: () =>
    request<{ status: string; data: TrackedSymbol[]; timestamp_ms: number }>("GET", "/symbols"),

  updateSymbols: (symbols: string[]) =>
    request<{ status: string; data: unknown; timestamp_ms: number }>("PUT", "/symbols", { symbols }),

  // FX Rate
  getFxRate: () =>
    request<{ status: string; data: unknown; timestamp_ms: number }>("GET", "/fx-rate"),

  // Preferences
  getPreferences: () =>
    request<{ status: string; data: UserPreferences; timestamp_ms: number }>("GET", "/preferences"),

  updatePreferences: (body: Partial<UserPreferences>) =>
    request<{ status: string; data: UserPreferences; timestamp_ms: number }>("PUT", "/preferences", body),

  // Asset Status
  getAssetStatus: (params?: { symbol?: string }) =>
    request<{ status: string; data: AssetStatusEntry[]; timestamp_ms: number }>("GET", "/asset-status", undefined, params),

  // Gate.io Lending
  getGateLending: () =>
    request<{ status: string; data: GateLendingEntry[]; timestamp_ms: number }>("GET", "/gate-lending"),
};

export default api;
