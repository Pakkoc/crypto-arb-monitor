/**
 * ExchangeStatusBar — top status bar showing connection status for all exchanges,
 * FX rate, WebSocket status, and last update timestamp.
 */
import { usePriceStore } from "@/stores/priceStore";
import { ConnectorState } from "@/types/enums";
import { EXCHANGE_NAMES, ALL_EXCHANGES, formatTime, timeAgo } from "@/lib/format";
import type { WsStatus } from "@/hooks/useWebSocket";

interface ExchangeStatusBarProps {
  wsStatus: WsStatus;
}

const STATE_DOT: Record<string, string> = {
  [ConnectorState.ACTIVE]: "bg-green-500",
  [ConnectorState.CONNECTED]: "bg-green-400",
  [ConnectorState.SUBSCRIBING]: "bg-yellow-400",
  [ConnectorState.CONNECTING]: "bg-yellow-500",
  [ConnectorState.WAIT_RETRY]: "bg-orange-500",
  [ConnectorState.DISCONNECTED]: "bg-red-500",
};

const WS_STATUS_DOT: Record<WsStatus, string> = {
  connected: "bg-green-500",
  connecting: "bg-yellow-500",
  disconnected: "bg-gray-500",
  error: "bg-red-500",
};

export function ExchangeStatusBar({ wsStatus }: ExchangeStatusBarProps) {
  const exchangeStatuses = usePriceStore((s) => s.exchangeStatuses);
  const fxRate = usePriceStore((s) => s.fxRate);

  return (
    <div className="flex items-center gap-4 rounded-lg border border-gray-800 bg-gray-900/80 px-4 py-2 text-xs">
      {/* Exchange connection indicators */}
      <div className="flex items-center gap-3">
        {ALL_EXCHANGES.map((ex) => {
          const status = exchangeStatuses[ex];
          const state = status?.state ?? ConnectorState.DISCONNECTED;
          const dotClass = STATE_DOT[state] ?? "bg-gray-600";
          const latency = status?.latency_ms;

          return (
            <div
              key={ex}
              className="group relative flex items-center gap-1.5"
              title={`${EXCHANGE_NAMES[ex]}: ${state}${latency != null ? ` (${latency}ms)` : ""}`}
            >
              <span
                className={`inline-block h-2 w-2 rounded-full ${dotClass} ${state === ConnectorState.CONNECTING || state === ConnectorState.SUBSCRIBING ? "animate-pulse" : ""}`}
              />
              <span className="text-gray-400">{EXCHANGE_NAMES[ex]}</span>
              {latency != null && (
                <span className="text-gray-600">{latency}ms</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Separator */}
      <div className="h-4 w-px bg-gray-700" />

      {/* FX Rate */}
      <div className="flex items-center gap-1.5">
        <span className="text-gray-500">환율:</span>
        {fxRate ? (
          <>
            <span className="font-mono text-gray-200">
              ₩{Number(fxRate.rate).toLocaleString("ko-KR")}
            </span>
            <span className="text-gray-600">({fxRate.source})</span>
            {fxRate.is_stale && (
              <span className="text-orange-400" title="환율 데이터 오래됨">
                ⚠
              </span>
            )}
          </>
        ) : (
          <span className="text-gray-600">N/A</span>
        )}
      </div>

      {/* Separator */}
      <div className="h-4 w-px bg-gray-700" />

      {/* WebSocket status */}
      <div className="flex items-center gap-1.5">
        <span
          className={`inline-block h-2 w-2 rounded-full ${WS_STATUS_DOT[wsStatus]}`}
        />
        <span className="text-gray-400 capitalize">WS: {wsStatus}</span>
      </div>

      {/* Last update — derived from exchange statuses */}
      <div className="ml-auto text-gray-500">
        {(() => {
          let latest = 0;
          for (const s of Object.values(exchangeStatuses)) {
            if (s.last_message_ms && s.last_message_ms > latest) latest = s.last_message_ms;
          }
          return latest > 0 ? (
            <>
              갱신: {formatTime(latest)}{" "}
              <span className="text-gray-600">({timeAgo(latest)})</span>
            </>
          ) : (
            "데이터 대기 중..."
          );
        })()}
      </div>
    </div>
  );
}
