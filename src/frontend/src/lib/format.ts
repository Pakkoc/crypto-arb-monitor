/**
 * Formatting utilities for prices, percentages, and timestamps.
 *
 * All price values arrive as Decimal-as-string from the API.
 * These helpers format for display without losing precision via parseFloat.
 */

const krwFormatter = new Intl.NumberFormat("ko-KR", {
  style: "decimal",
  maximumFractionDigits: 0,
});

const usdtFormatter = new Intl.NumberFormat("en-US", {
  style: "decimal",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const pctFormatter = new Intl.NumberFormat("en-US", {
  style: "decimal",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "always",
});

/**
 * Format a price string for display based on currency.
 * KRW prices have no decimals; USDT prices have 2 decimals.
 */
export function formatPrice(price: string, currency: "KRW" | "USDT"): string {
  const num = Number(price);
  if (Number.isNaN(num)) return price;
  if (currency === "KRW") {
    return "₩" + krwFormatter.format(num);
  }
  return "$" + usdtFormatter.format(num);
}

/**
 * Format a spread percentage string for display.
 */
export function formatSpreadPct(pct: string): string {
  const num = Number(pct);
  if (Number.isNaN(num)) return pct;
  return pctFormatter.format(num) + "%";
}

/**
 * Format a plain percentage (no sign).
 */
export function formatPct(pct: string | number): string {
  const num = Number(pct);
  if (Number.isNaN(num)) return String(pct);
  return num.toFixed(2) + "%";
}

/**
 * Return a relative time string like "3s ago", "2m ago".
 */
export function timeAgo(timestampMs: number): string {
  const diff = Date.now() - timestampMs;
  if (diff < 0) return "방금";
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}초 전`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

/**
 * Format a timestamp_ms as HH:MM:SS.
 */
export function formatTime(timestampMs: number): string {
  const date = new Date(timestampMs);
  return date.toLocaleTimeString("ko-KR", { hour12: false });
}

/**
 * Format a full datetime from ISO string.
 */
export function formatDatetime(isoStr: string): string {
  const date = new Date(isoStr);
  return date.toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Get the spread color class based on absolute spread percentage.
 */
export function spreadColorClass(pct: string): string {
  const abs = Math.abs(Number(pct));
  if (abs < 1) return "text-green-400";
  if (abs < 2) return "text-yellow-400";
  if (abs < 3) return "text-orange-400";
  return "text-red-400";
}

/**
 * Get the spread background color class for matrix cells.
 */
export function spreadBgClass(pct: string): string {
  const abs = Math.abs(Number(pct));
  if (abs < 1) return "bg-green-900/40";
  if (abs < 2) return "bg-yellow-900/40";
  if (abs < 3) return "bg-orange-900/40";
  return "bg-red-900/40";
}

/**
 * Exchange display names.
 */
export const EXCHANGE_NAMES: Record<string, string> = {
  bithumb: "Bithumb",
  upbit: "Upbit",
  binance: "Binance",
  bybit: "Bybit",
  gate: "Gate.io",
};

/**
 * KRW exchanges (domestic).
 */
export const KRW_EXCHANGES = ["bithumb", "upbit"] as const;

/**
 * USDT exchanges (global).
 */
export const USDT_EXCHANGES = ["binance", "bybit", "gate"] as const;

/**
 * All exchanges in display order.
 */
export const ALL_EXCHANGES = [...KRW_EXCHANGES, ...USDT_EXCHANGES] as const;
