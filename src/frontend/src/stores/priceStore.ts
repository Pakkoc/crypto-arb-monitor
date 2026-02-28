/**
 * Zustand store for real-time price and spread data.
 *
 * Updated by the useWebSocket hook on every price_update and spread_update
 * WebSocket event. Read by Dashboard, SpreadMatrix, and chart components.
 *
 * History throttling: to prevent OOM from 300+ updates/sec, history arrays
 * are only appended once per HISTORY_THROTTLE_MS per key. Latest prices/spreads
 * still update on every tick for real-time display.
 */
import { create } from "zustand";
import type { FxRateInfo, PriceEntry, SpreadEntry } from "@/types";
import type { ConnectorState, ExchangeId } from "@/types/enums";

/** Ring buffer capacity per key. */
const PRICE_HISTORY_SIZE = 500;

/** Minimum interval (ms) between history appends for the same key. */
const HISTORY_THROTTLE_MS = 5_000;

interface ExchangeStatusInfo {
  state: ConnectorState;
  latency_ms: number | null;
  last_message_ms: number | null;
  is_stale: boolean;
}

interface PriceState {
  /** Latest price per (exchange, symbol) — keyed as "exchange:symbol" */
  prices: Record<string, PriceEntry>;
  /** Price history ring buffers — keyed as "exchange:symbol", newest first */
  priceHistory: Record<string, PriceEntry[]>;
  /** Latest spread per (exchange_a:exchange_b:symbol) */
  spreads: Record<string, SpreadEntry>;
  /** Spread history ring buffers — keyed as "exchange_a:exchange_b:symbol", newest first */
  spreadHistory: Record<string, SpreadEntry[]>;
  /** Current KRW/USD FX rate */
  fxRate: FxRateInfo | null;
  /** Per-exchange connection status */
  exchangeStatuses: Record<string, ExchangeStatusInfo>;
  /** Whether we have received the initial snapshot */
  isInitialized: boolean;

  // Actions
  setPrice: (entry: PriceEntry) => void;
  setSpread: (entry: SpreadEntry) => void;
  setFxRate: (rate: FxRateInfo) => void;
  setExchangeStatus: (exchange: ExchangeId, status: ExchangeStatusInfo) => void;
  applySnapshot: (prices: PriceEntry[], spreads: SpreadEntry[], fxRate: FxRateInfo | null) => void;
  reset: () => void;
}

function appendToRingBuffer<T>(buffer: T[] | undefined, entry: T, maxSize: number): T[] {
  const arr = buffer ? [entry, ...buffer] : [entry];
  return arr.length > maxSize ? arr.slice(0, maxSize) : arr;
}

/**
 * Track the last history-append timestamp per key.
 * Lives outside the store to avoid triggering re-renders.
 */
const _lastHistoryAppend: Record<string, number> = {};

function shouldAppendHistory(key: string, now: number): boolean {
  const last = _lastHistoryAppend[key];
  if (last === undefined || now - last >= HISTORY_THROTTLE_MS) {
    _lastHistoryAppend[key] = now;
    return true;
  }
  return false;
}

export const usePriceStore = create<PriceState>((set) => ({
  prices: {},
  priceHistory: {},
  spreads: {},
  spreadHistory: {},
  fxRate: null,
  exchangeStatuses: {},
  isInitialized: false,

  setPrice: (entry) => {
    const key = `${entry.exchange}:${entry.symbol}`;
    const now = Date.now();
    if (shouldAppendHistory(key, now)) {
      set((state) => ({
        prices: { ...state.prices, [key]: entry },
        priceHistory: {
          ...state.priceHistory,
          [key]: appendToRingBuffer(state.priceHistory[key], entry, PRICE_HISTORY_SIZE),
        },
      }));
    } else {
      // Update latest price only — no history copy
      set((state) => ({
        prices: { ...state.prices, [key]: entry },
      }));
    }
  },

  setSpread: (entry) => {
    const key = `${entry.exchange_a}:${entry.exchange_b}:${entry.symbol}`;
    const now = Date.now();
    if (shouldAppendHistory(key, now)) {
      set((state) => ({
        spreads: { ...state.spreads, [key]: entry },
        spreadHistory: {
          ...state.spreadHistory,
          [key]: appendToRingBuffer(state.spreadHistory[key], entry, PRICE_HISTORY_SIZE),
        },
      }));
    } else {
      // Update latest spread only — no history copy
      set((state) => ({
        spreads: { ...state.spreads, [key]: entry },
      }));
    }
  },

  setFxRate: (rate) => set({ fxRate: rate }),

  setExchangeStatus: (exchange, status) =>
    set((state) => ({
      exchangeStatuses: { ...state.exchangeStatuses, [exchange]: status },
    })),

  applySnapshot: (prices, spreads, fxRate) =>
    set({
      prices: Object.fromEntries(prices.map((p) => [`${p.exchange}:${p.symbol}`, p])),
      spreads: Object.fromEntries(
        spreads.map((s) => [`${s.exchange_a}:${s.exchange_b}:${s.symbol}`, s]),
      ),
      fxRate: fxRate ?? null,
      isInitialized: true,
    }),

  reset: () => {
    // Clear throttle timestamps
    for (const key of Object.keys(_lastHistoryAppend)) {
      delete _lastHistoryAppend[key];
    }
    set({
      prices: {},
      priceHistory: {},
      spreads: {},
      spreadHistory: {},
      fxRate: null,
      exchangeStatuses: {},
      isInitialized: false,
    });
  },
}));
