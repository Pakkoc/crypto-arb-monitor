/**
 * useWebSocket — manages the WebSocket connection to the backend.
 *
 * Implements the reconnection protocol from api-design.md §2.4:
 * - Exponential backoff: min(1000 * 2^attempt, 30000) ms
 * - Automatic resubscription after reconnect
 * - State reconciliation via snapshot
 *
 * Dispatches incoming messages to the Zustand stores (priceStore, alertStore).
 */
import { useEffect, useRef, useState } from "react";
import { usePriceStore } from "@/stores/priceStore";
import { useAlertStore } from "@/stores/alertStore";
import { WsEventType } from "@/types/enums";
import type {
  WsAlertTriggeredData,
  WsExchangeStatusData,
  WsSnapshotData,
} from "@/types/ws";
import type { PriceEntry, SpreadEntry } from "@/types";

const WS_URL = "/api/v1/ws";
const MAX_BACKOFF_MS = 30_000;

export type WsStatus = "connecting" | "connected" | "disconnected" | "error";

interface UseWebSocketOptions {
  symbols?: string[];
  channels?: string[];
  enabled?: boolean;
}

function backoffDelay(attempt: number): number {
  return Math.min(1_000 * Math.pow(2, attempt), MAX_BACKOFF_MS);
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    symbols = [],
    channels = ["prices", "spreads", "alerts", "exchange_status"],
    enabled = true,
  } = options;

  const [status, setStatus] = useState<WsStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSeqRef = useRef(0);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const closedRef = useRef(false);

  // Store refs to avoid recreating callbacks
  const symbolsRef = useRef(symbols);
  symbolsRef.current = symbols;
  const channelsRef = useRef(channels);
  channelsRef.current = channels;

  useEffect(() => {
    if (!enabled) return;

    const { applySnapshot, setPrice, setSpread, setFxRate, setExchangeStatus } =
      usePriceStore.getState();
    const { addTrigger } = useAlertStore.getState();

    function scheduleReconnect() {
      if (!enabledRef.current || closedRef.current) return;
      const delay = backoffDelay(attemptRef.current);
      attemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    }

    function connect() {
      if (!enabledRef.current || closedRef.current) return;

      setStatus("connecting");
      const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}${WS_URL}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setStatus("connected");
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(event.data) as {
            type: string;
            data: unknown;
            seq?: number;
          };

          // Sequence number gap detection
          if (typeof msg.seq === "number") {
            const expected = lastSeqRef.current + 1;
            if (lastSeqRef.current > 0 && msg.seq > expected) {
              console.warn(
                `[WS] Sequence gap: expected ${expected}, got ${msg.seq}`,
              );
            }
            lastSeqRef.current = msg.seq;
          }

          switch (msg.type) {
            case WsEventType.WELCOME: {
              // Send subscription
              const subMsg = {
                type: WsEventType.SUBSCRIBE,
                ...(symbolsRef.current.length > 0 && { symbols: symbolsRef.current }),
                channels: channelsRef.current,
              };
              ws.send(JSON.stringify(subMsg));
              break;
            }

            case WsEventType.SNAPSHOT: {
              const data = msg.data as WsSnapshotData;
              applySnapshot(
                data.prices ?? [],
                data.spreads ?? [],
                data.fx_rate ?? null,
              );
              if (data.exchange_statuses) {
                for (const es of data.exchange_statuses) {
                  setExchangeStatus(es.exchange, {
                    state: es.state,
                    latency_ms: es.latency_ms,
                    last_message_ms: es.last_message_ms,
                    is_stale: false,
                  });
                }
              }
              if (data.fx_rate) {
                setFxRate(data.fx_rate);
              }
              break;
            }

            case WsEventType.PRICE_UPDATE:
              usePriceStore.getState().setPrice(msg.data as PriceEntry);
              break;

            case WsEventType.SPREAD_UPDATE:
              usePriceStore.getState().setSpread(msg.data as SpreadEntry);
              break;

            case WsEventType.ALERT_TRIGGERED:
              useAlertStore.getState().addTrigger(msg.data as WsAlertTriggeredData);
              break;

            case WsEventType.EXCHANGE_STATUS: {
              const esData = msg.data as WsExchangeStatusData;
              usePriceStore.getState().setExchangeStatus(esData.exchange, {
                state: esData.state,
                latency_ms: esData.latency_ms,
                last_message_ms: esData.last_message_ms,
                is_stale: esData.is_stale,
              });
              break;
            }

            case WsEventType.HEARTBEAT:
              ws.send(JSON.stringify({ type: WsEventType.PONG }));
              break;

            default:
              break;
          }
        } catch {
          // Malformed JSON — ignore
        }
      };

      ws.onclose = () => {
        setStatus("disconnected");
        scheduleReconnect();
      };

      ws.onerror = () => {
        setStatus("error");
        ws.close();
      };
    }

    closedRef.current = false;
    connect();

    return () => {
      closedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      } else if (ws) {
        // Still CONNECTING — defer close until open or let it fail silently
        ws.onopen = () => ws.close();
        ws.onerror = () => {};
        ws.onclose = () => {};
      }
    };
  }, [enabled]);

  return { status };
}
