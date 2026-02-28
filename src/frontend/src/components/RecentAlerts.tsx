/**
 * RecentAlerts — displays recent triggered alert notifications with pagination.
 *
 * Shows severity icon, exchange pair, spread %, and timestamp.
 * Seeds initial data from DB, then appends live WS alerts.
 * 5 items per page with prev/next navigation.
 */
import { useEffect, useRef, useState } from "react";
import { useAlertStore } from "@/stores/alertStore";
import { EXCHANGE_NAMES, formatSpreadPct, timeAgo } from "@/lib/format";
import type { AlertSeverity } from "@/types/enums";
import type { WsAlertTriggeredData } from "@/types";
import api from "@/lib/api";

const PAGE_SIZE = 5;

const SEVERITY_STYLES: Record<
  AlertSeverity,
  { dot: string; bg: string; label: string }
> = {
  info: { dot: "bg-blue-500", bg: "border-blue-900/50", label: "INFO" },
  warning: {
    dot: "bg-yellow-500",
    bg: "border-yellow-900/50",
    label: "WARN",
  },
  critical: { dot: "bg-red-500", bg: "border-red-900/50", label: "CRIT" },
};

function AlertItem({ trigger }: { trigger: WsAlertTriggeredData }) {
  const style = SEVERITY_STYLES[trigger.severity] ?? SEVERITY_STYLES.info;

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border ${style.bg} bg-gray-900/50 px-3 py-2.5`}
    >
      {/* Severity indicator */}
      <div className="flex flex-col items-center gap-1 pt-0.5">
        <span
          className={`inline-block h-2 w-2 rounded-full ${style.dot}`}
          title={style.label}
        />
        <span className="text-[9px] font-medium text-gray-600">
          {style.label}
        </span>
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-300">
            {EXCHANGE_NAMES[trigger.exchange_a] ?? trigger.exchange_a}
            {" → "}
            {EXCHANGE_NAMES[trigger.exchange_b] ?? trigger.exchange_b}
          </span>
          <span className="rounded bg-gray-800 px-1 py-0.5 text-[10px] text-gray-500">
            {trigger.symbol}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs">
          <span className="font-mono tabular-nums text-gray-200">
            {formatSpreadPct(trigger.spread_pct)}
          </span>
          <span className="text-gray-600">
            (임계값: {formatSpreadPct(trigger.threshold_pct)})
          </span>
        </div>
        <div className="mt-1 flex items-center gap-2 text-[10px] text-gray-600">
          <span>{timeAgo(trigger.timestamp_ms)}</span>
          {trigger.telegram_delivered && (
            <span className="text-green-700" title="텔레그램 알림 전송됨">
              TG 전송됨
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function RecentAlerts() {
  const triggers = useAlertStore((s) => s.recentTriggers);
  const clearTriggers = useAlertStore((s) => s.clearTriggers);
  const seededRef = useRef(false);
  const [page, setPage] = useState(0);

  // Seed recent alerts from DB on first mount
  useEffect(() => {
    if (seededRef.current) return;
    seededRef.current = true;

    api.getAlertHistory({ limit: 50 }).then((res) => {
      const rows = res.data;
      if (!Array.isArray(rows) || rows.length === 0) return;
      if (useAlertStore.getState().recentTriggers.length > 0) return;

      const mapped: WsAlertTriggeredData[] = rows.map((row) => ({
        alert_config_id: row.alert_config_id,
        exchange_a: row.exchange_a,
        exchange_b: row.exchange_b,
        symbol: row.symbol,
        spread_pct: row.spread_pct,
        spread_type: row.spread_type,
        threshold_pct: row.threshold_pct,
        direction: row.direction,
        severity: (Math.abs(Number(row.spread_pct)) >= 3 ? "critical" : Math.abs(Number(row.spread_pct)) >= 2 ? "warning" : "info") as AlertSeverity,
        fx_rate: row.fx_rate,
        fx_source: row.fx_source,
        telegram_delivered: row.telegram_delivered,
        timestamp_ms: new Date(row.created_at).getTime(),
      }));

      useAlertStore.setState({ recentTriggers: mapped });
    }).catch(() => {});
  }, []);

  // Reset to page 0 when new alerts arrive
  const triggerCountRef = useRef(triggers.length);
  useEffect(() => {
    if (triggers.length > triggerCountRef.current) {
      setPage(0);
    }
    triggerCountRef.current = triggers.length;
  }, [triggers.length]);

  const totalPages = Math.max(1, Math.ceil(triggers.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const visible = triggers.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">
          최근 알림
          {triggers.length > 0 && (
            <span className="ml-2 text-xs text-gray-600">({triggers.length})</span>
          )}
        </h3>
        {triggers.length > 0 && (
          <button
            onClick={() => { clearTriggers(); setPage(0); }}
            className="text-xs text-gray-600 transition-colors hover:text-gray-400"
          >
            모두 지우기
          </button>
        )}
      </div>

      {triggers.length === 0 ? (
        <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-gray-800 text-xs text-gray-600">
          최근 알림이 없습니다. 스프레드가 임계값을 초과하면 여기에 표시됩니다.
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {visible.map((trigger, idx) => (
              <AlertItem
                key={`${trigger.alert_config_id}-${trigger.timestamp_ms}-${safePage}-${idx}`}
                trigger={trigger}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-3 flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={safePage === 0}
                className="rounded px-2 py-0.5 text-xs text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 disabled:opacity-30 disabled:hover:bg-transparent"
              >
                ‹ 이전
              </button>
              <span className="text-xs text-gray-600">
                {safePage + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={safePage >= totalPages - 1}
                className="rounded px-2 py-0.5 text-xs text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 disabled:opacity-30 disabled:hover:bg-transparent"
              >
                다음 ›
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
