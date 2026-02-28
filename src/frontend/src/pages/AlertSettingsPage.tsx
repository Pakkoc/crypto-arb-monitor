/**
 * AlertSettingsPage — full CRUD interface for alert configurations.
 *
 * Features:
 * - List existing alerts with enable/disable toggle
 * - Create new alert form
 * - Edit existing alert (modal)
 * - Delete alert with confirmation
 * - Alert history tab
 */
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAlerts } from "@/hooks/useAlerts";
import api from "@/lib/api";
import { AlertDirection } from "@/types/enums";
import { EXCHANGE_NAMES, ALL_EXCHANGES, formatSpreadPct, formatDatetime } from "@/lib/format";
import type { AlertConfig, AlertConfigCreate, AlertConfigUpdate, AlertHistoryEntry } from "@/types";

// ── Sub-components ────────────────────────────────────────────────────────────

type TabId = "alerts" | "history";

function AlertToggle({
  alert,
  onToggle,
}: {
  alert: AlertConfig;
  onToggle: (id: number, enabled: boolean) => void;
}) {
  const [pending, setPending] = useState(false);

  const handleClick = async () => {
    setPending(true);
    try {
      await onToggle(alert.id, !alert.enabled);
    } finally {
      setPending(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={pending}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        alert.enabled ? "bg-blue-600" : "bg-gray-700"
      } ${pending ? "opacity-50" : ""}`}
      title={alert.enabled ? "비활성화" : "활성화"}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
          alert.enabled ? "translate-x-4.5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

function AlertRow({
  alert,
  onToggle,
  onEdit,
  onDelete,
}: {
  alert: AlertConfig;
  onToggle: (id: number, enabled: boolean) => void;
  onEdit: (alert: AlertConfig) => void;
  onDelete: (id: number) => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div
      className={`rounded-lg border p-4 transition-colors ${
        alert.enabled
          ? "border-gray-800 bg-gray-900"
          : "border-gray-800/50 bg-gray-900/50 opacity-60"
      }`}
    >
      <div className="flex items-center gap-4">
        {/* Toggle */}
        <AlertToggle alert={alert} onToggle={onToggle} />

        {/* Main info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">#{alert.id}</span>
            <span className="font-mono text-sm text-gray-200">
              {alert.exchange_a
                ? EXCHANGE_NAMES[alert.exchange_a] ?? alert.exchange_a
                : "Any"}
              {" → "}
              {alert.exchange_b
                ? EXCHANGE_NAMES[alert.exchange_b] ?? alert.exchange_b
                : "Any"}
            </span>
            {alert.symbol && (
              <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400">
                {alert.symbol}
              </span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
            <span>
              임계값:{" "}
              <span className="font-mono text-gray-400">
                {alert.threshold_pct}%
              </span>
            </span>
            <span>방향: {alert.direction}</span>
            <span>쿨다운: {alert.cooldown_minutes}분</span>
            <span>발동: {alert.trigger_count}회</span>
            {alert.last_triggered_at && (
              <span>최근: {formatDatetime(alert.last_triggered_at)}</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onEdit(alert)}
            className="rounded px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
          >
            수정
          </button>
          {confirmDelete ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => {
                  onDelete(alert.id);
                  setConfirmDelete(false);
                }}
                className="rounded bg-red-900/50 px-2 py-1 text-xs text-red-400 transition-colors hover:bg-red-900"
              >
                확인
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded px-2 py-1 text-xs text-gray-600 hover:text-gray-400"
              >
                취소
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="rounded px-2 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-800 hover:text-red-400"
            >
              삭제
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Create/Edit Form ─────────────────────────────────────────────────────────

interface AlertFormData {
  exchange_a: string;
  exchange_b: string;
  symbol: string;
  threshold_pct: number;
  direction: string;
  cooldown_minutes: number;
}

const DEFAULT_FORM: AlertFormData = {
  exchange_a: "",
  exchange_b: "",
  symbol: "BTC",
  threshold_pct: 2.0,
  direction: AlertDirection.ABOVE,
  cooldown_minutes: 5,
};

function AlertFormModal({
  editAlert,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  editAlert: AlertConfig | null;
  onClose: () => void;
  onSubmit: (data: AlertFormData, editId: number | null) => Promise<void>;
  isSubmitting: boolean;
}) {
  const [form, setForm] = useState<AlertFormData>(() => {
    if (editAlert) {
      return {
        exchange_a: editAlert.exchange_a ?? "",
        exchange_b: editAlert.exchange_b ?? "",
        symbol: editAlert.symbol ?? "BTC",
        threshold_pct: Number(editAlert.threshold_pct),
        direction: editAlert.direction,
        cooldown_minutes: editAlert.cooldown_minutes,
      };
    }
    return { ...DEFAULT_FORM };
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(form, editAlert?.id ?? null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
        <h3 className="mb-4 text-lg font-medium text-gray-200">
          {editAlert ? "알림 수정" : "알림 생성"}
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Exchange pair */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-gray-500">
                거래소 A
              </label>
              <select
                value={form.exchange_a}
                onChange={(e) =>
                  setForm((f) => ({ ...f, exchange_a: e.target.value }))
                }
                className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 outline-none focus:border-blue-600"
              >
                <option value="">전체</option>
                {ALL_EXCHANGES.map((ex) => (
                  <option key={ex} value={ex}>
                    {EXCHANGE_NAMES[ex]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">
                거래소 B
              </label>
              <select
                value={form.exchange_b}
                onChange={(e) =>
                  setForm((f) => ({ ...f, exchange_b: e.target.value }))
                }
                className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 outline-none focus:border-blue-600"
              >
                <option value="">전체</option>
                {ALL_EXCHANGES.map((ex) => (
                  <option key={ex} value={ex}>
                    {EXCHANGE_NAMES[ex]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Symbol */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">
              거래 종목
            </label>
            <select
              value={form.symbol}
              onChange={(e) =>
                setForm((f) => ({ ...f, symbol: e.target.value }))
              }
              className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 outline-none focus:border-blue-600"
            >
              <option value="BTC">BTC</option>
              <option value="ETH">ETH</option>
              <option value="XRP">XRP</option>
              <option value="SOL">SOL</option>
              <option value="ADA">ADA</option>
            </select>
          </div>

          {/* Threshold */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">
              임계값 (%)
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="0.1"
                max="10"
                step="0.1"
                value={form.threshold_pct}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    threshold_pct: Number(e.target.value),
                  }))
                }
                className="flex-1"
              />
              <input
                type="number"
                min="0.1"
                max="50"
                step="0.1"
                value={form.threshold_pct}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    threshold_pct: Number(e.target.value),
                  }))
                }
                className="w-20 rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-right font-mono text-sm text-gray-300 outline-none focus:border-blue-600"
              />
              <span className="text-sm text-gray-500">%</span>
            </div>
          </div>

          {/* Direction */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">
              방향
            </label>
            <div className="flex gap-2">
              {[
                { value: AlertDirection.ABOVE, label: "이상" },
                { value: AlertDirection.BELOW, label: "이하" },
                { value: AlertDirection.BOTH, label: "양방향" },
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() =>
                    setForm((f) => ({ ...f, direction: opt.value }))
                  }
                  className={`rounded px-4 py-1.5 text-xs transition-colors ${
                    form.direction === opt.value
                      ? "bg-blue-600 text-white"
                      : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Cooldown */}
          <div>
            <label className="mb-1 block text-xs text-gray-500">
              쿨다운 (분)
            </label>
            <input
              type="number"
              min="1"
              max="60"
              value={form.cooldown_minutes}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  cooldown_minutes: Number(e.target.value),
                }))
              }
              className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 outline-none focus:border-blue-600"
            />
          </div>

          {/* Buttons */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded px-4 py-2 text-sm text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
            >
              {isSubmitting
                ? "저장 중..."
                : editAlert
                  ? "알림 수정"
                  : "알림 생성"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Alert History Tab ────────────────────────────────────────────────────────

function AlertHistoryTab() {
  const historyQuery = useQuery({
    queryKey: ["alert-history"],
    queryFn: async () => {
      const response = await api.getAlertHistory({ limit: 50 });
      return response.data ?? [];
    },
    staleTime: 30_000,
  });

  if (historyQuery.isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-12 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
          />
        ))}
      </div>
    );
  }

  if (historyQuery.isError) {
    return (
      <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-4 text-center">
        <p className="text-sm text-red-400">알림 이력을 불러오지 못했습니다.</p>
        <button
          onClick={() => historyQuery.refetch()}
          className="mt-2 rounded bg-gray-800 px-3 py-1 text-xs text-gray-400 hover:bg-gray-700"
        >
          다시 시도
        </button>
      </div>
    );
  }

  const history = historyQuery.data as AlertHistoryEntry[];

  if (history.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-gray-800 text-sm text-gray-600">
        알림 이력이 없습니다.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {history.map((entry) => (
        <div
          key={entry.id}
          className="flex items-center gap-4 rounded-lg border border-gray-800 bg-gray-900 px-4 py-3"
        >
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs">
              <span className="font-mono text-gray-300">
                {EXCHANGE_NAMES[entry.exchange_a] ?? entry.exchange_a} →{" "}
                {EXCHANGE_NAMES[entry.exchange_b] ?? entry.exchange_b}
              </span>
              <span className="rounded bg-gray-800 px-1 py-0.5 text-[10px] text-gray-500">
                {entry.symbol}
              </span>
              <span className="font-mono font-medium text-gray-200">
                {formatSpreadPct(entry.spread_pct)}
              </span>
            </div>
            <div className="mt-0.5 text-[10px] text-gray-600">
              {entry.message_text}
            </div>
          </div>
          <div className="flex flex-col items-end gap-0.5 text-[10px]">
            <span className="text-gray-500">
              {formatDatetime(entry.created_at)}
            </span>
            <span
              className={
                entry.telegram_delivered ? "text-green-700" : "text-gray-700"
              }
            >
              {entry.telegram_delivered ? "TG 전송됨" : "TG 대기"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export function AlertSettingsPage() {
  const { alerts, isLoading, isError, createAlert, updateAlert, deleteAlert } =
    useAlerts();

  const [activeTab, setActiveTab] = useState<TabId>("alerts");
  const [showForm, setShowForm] = useState(false);
  const [editingAlert, setEditingAlert] = useState<AlertConfig | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleToggle = useCallback(
    async (id: number, enabled: boolean) => {
      await updateAlert({ id, body: { enabled } });
    },
    [updateAlert],
  );

  const handleSubmit = useCallback(
    async (data: AlertFormData, editId: number | null) => {
      setIsSubmitting(true);
      try {
        if (editId !== null) {
          const body: AlertConfigUpdate = {
            symbol: data.symbol || undefined,
            exchange_a: (data.exchange_a as AlertConfigUpdate["exchange_a"]) || undefined,
            exchange_b: (data.exchange_b as AlertConfigUpdate["exchange_b"]) || undefined,
            threshold_pct: data.threshold_pct,
            direction: data.direction as AlertConfigUpdate["direction"],
            cooldown_minutes: data.cooldown_minutes,
          };
          await updateAlert({ id: editId, body });
        } else {
          const body: AlertConfigCreate = {
            chat_id: 0, // Default chat_id; backend should handle
            symbol: data.symbol || undefined,
            exchange_a: (data.exchange_a as AlertConfigCreate["exchange_a"]) || undefined,
            exchange_b: (data.exchange_b as AlertConfigCreate["exchange_b"]) || undefined,
            threshold_pct: data.threshold_pct,
            direction: data.direction as AlertConfigCreate["direction"],
            cooldown_minutes: data.cooldown_minutes,
          };
          await createAlert(body);
        }
        setShowForm(false);
        setEditingAlert(null);
      } finally {
        setIsSubmitting(false);
      }
    },
    [createAlert, updateAlert],
  );

  const handleEdit = useCallback((alert: AlertConfig) => {
    setEditingAlert(alert);
    setShowForm(true);
  }, []);

  const handleDelete = useCallback(
    async (id: number) => {
      await deleteAlert(id);
    },
    [deleteAlert],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">알림 설정</h2>
        <button
          onClick={() => {
            setEditingAlert(null);
            setShowForm(true);
          }}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
        >
          + 새 알림
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        <button
          onClick={() => setActiveTab("alerts")}
          className={`border-b-2 px-4 py-2 text-sm transition-colors ${
            activeTab === "alerts"
              ? "border-blue-600 text-white"
              : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          알림 ({alerts.length})
        </button>
        <button
          onClick={() => setActiveTab("history")}
          className={`border-b-2 px-4 py-2 text-sm transition-colors ${
            activeTab === "history"
              ? "border-blue-600 text-white"
              : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          이력
        </button>
      </div>

      {/* Content */}
      {activeTab === "alerts" ? (
        <>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-20 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
                />
              ))}
            </div>
          ) : isError ? (
            <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-6 text-center">
              <p className="text-sm text-red-400">
                알림 설정을 불러오지 못했습니다.
              </p>
              <p className="mt-1 text-xs text-gray-600">
                백엔드가 실행 중인지 확인하고 새로고침해 주세요.
              </p>
            </div>
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-gray-700 py-12">
              <svg
                className="mb-3 h-10 w-10 text-gray-700"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
              <p className="text-sm text-gray-500">
                설정된 알림이 없습니다.
              </p>
              <p className="mt-1 text-xs text-gray-600">
                스프레드가 임계값을 초과하면 알림을 받을 수 있도록 첫 번째 알림을 만들어 보세요.
              </p>
              <button
                onClick={() => {
                  setEditingAlert(null);
                  setShowForm(true);
                }}
                className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
              >
                + 알림 생성
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <AlertRow
                  key={alert.id}
                  alert={alert}
                  onToggle={handleToggle}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <AlertHistoryTab />
      )}

      {/* Create/Edit Modal */}
      {showForm && (
        <AlertFormModal
          editAlert={editingAlert}
          onClose={() => {
            setShowForm(false);
            setEditingAlert(null);
          }}
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
        />
      )}
    </div>
  );
}
