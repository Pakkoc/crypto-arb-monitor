/**
 * Zustand store for alert configurations and recent alert trigger events.
 *
 * Alert configs are loaded from the REST API via TanStack Query.
 * Alert trigger events arrive via WebSocket (alert_triggered messages).
 */
import { create } from "zustand";
import type { AlertConfig, WsAlertTriggeredData } from "@/types";

const MAX_RECENT_ALERTS = 50;

interface AlertState {
  /** All alert configurations (loaded from REST API) */
  configs: AlertConfig[];
  /** Recent alert trigger events received via WebSocket */
  recentTriggers: WsAlertTriggeredData[];

  // Actions
  setConfigs: (configs: AlertConfig[]) => void;
  addConfig: (config: AlertConfig) => void;
  updateConfig: (id: number, updated: AlertConfig) => void;
  removeConfig: (id: number) => void;
  addTrigger: (trigger: WsAlertTriggeredData) => void;
  clearTriggers: () => void;
}

export const useAlertStore = create<AlertState>((set) => ({
  configs: [],
  recentTriggers: [],

  setConfigs: (configs) => set({ configs }),

  addConfig: (config) =>
    set((state) => ({ configs: [...state.configs, config] })),

  updateConfig: (id, updated) =>
    set((state) => ({
      configs: state.configs.map((c) => (c.id === id ? updated : c)),
    })),

  removeConfig: (id) =>
    set((state) => ({
      configs: state.configs.filter((c) => c.id !== id),
    })),

  addTrigger: (trigger) =>
    set((state) => ({
      recentTriggers: [trigger, ...state.recentTriggers].slice(0, MAX_RECENT_ALERTS),
    })),

  clearTriggers: () => set({ recentTriggers: [] }),
}));
