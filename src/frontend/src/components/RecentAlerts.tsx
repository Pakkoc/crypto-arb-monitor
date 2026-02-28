/**
 * RecentAlerts — displays the last 10 triggered alert notifications.
 *
 * Shows severity icon, exchange pair, spread %, and timestamp.
 * Alerts are dismissable (removed from the local store only).
 */
import { useAlertStore } from "@/stores/alertStore";
import { EXCHANGE_NAMES, formatSpreadPct, timeAgo } from "@/lib/format";
import type { AlertSeverity } from "@/types/enums";
import type { WsAlertTriggeredData } from "@/types";

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

function AlertItem({
  trigger,
  onDismiss,
}: {
  trigger: WsAlertTriggeredData;
  onDismiss: () => void;
}) {
  const style = SEVERITY_STYLES[trigger.severity] ?? SEVERITY_STYLES.info;

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border ${style.bg} bg-gray-900/50 px-3 py-2.5 transition-opacity`}
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
          <span className="text-gray-600">·</span>
          <span className="text-gray-600">{trigger.direction}</span>
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

      {/* Dismiss button */}
      <button
        onClick={onDismiss}
        className="mt-0.5 text-gray-700 transition-colors hover:text-gray-400"
        title="닫기"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    </div>
  );
}

export function RecentAlerts() {
  const triggers = useAlertStore((s) => s.recentTriggers);
  const clearTriggers = useAlertStore((s) => s.clearTriggers);

  // Show last 10 only
  const visible = triggers.slice(0, 10);

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">최근 알림</h3>
        {triggers.length > 0 && (
          <button
            onClick={clearTriggers}
            className="text-xs text-gray-600 transition-colors hover:text-gray-400"
          >
            모두 지우기
          </button>
        )}
      </div>

      {visible.length === 0 ? (
        <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-gray-800 text-xs text-gray-600">
          최근 알림이 없습니다. 스프레드가 임계값을 초과하면 여기에 표시됩니다.
        </div>
      ) : (
        <div className="space-y-2">
          {visible.map((trigger, idx) => (
            <AlertItem
              key={`${trigger.alert_config_id}-${trigger.timestamp_ms}-${idx}`}
              trigger={trigger}
              onDismiss={() => {
                // Remove this specific trigger from the store
                // Since recentTriggers is a simple array, we filter by index
                useAlertStore.setState((s) => ({
                  recentTriggers: s.recentTriggers.filter((_, i) => i !== idx),
                }));
              }}
            />
          ))}
        </div>
      )}

      {triggers.length > 10 && (
        <div className="mt-2 text-center text-[10px] text-gray-600">
          +{triggers.length - 10}개 더 보기
        </div>
      )}
    </div>
  );
}
