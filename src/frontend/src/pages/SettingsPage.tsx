/**
 * SettingsPage — user preferences for dashboard, notifications, and general settings.
 *
 * Sections:
 * - Dashboard: default symbol, visible exchanges, spread display mode, chart interval, theme
 * - Notifications: Telegram toggle + chat ID, sound toggle
 * - General: timezone, locale
 */
import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { EXCHANGE_NAMES, ALL_EXCHANGES } from "@/lib/format";
import type { UserPreferences, DashboardPreferences, NotificationPreferences } from "@/types";

// ── Toggle Switch ────────────────────────────────────────────────────────────

function Toggle({
  enabled,
  onChange,
  disabled,
}: {
  enabled: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      disabled={disabled}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        enabled ? "bg-blue-600" : "bg-gray-700"
      } ${disabled ? "opacity-50" : ""}`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
          enabled ? "translate-x-4.5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

// ── Button Group ─────────────────────────────────────────────────────────────

function ButtonGroup<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1.5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded px-3 py-1.5 text-xs transition-colors ${
            value === opt.value
              ? "bg-blue-600 text-white"
              : "bg-gray-800 text-gray-400 hover:bg-gray-700"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <h3 className="text-sm font-medium text-gray-200">{title}</h3>
      {description && (
        <p className="mt-0.5 text-xs text-gray-600">{description}</p>
      )}
      <div className="mt-4 space-y-4">{children}</div>
    </div>
  );
}

function FieldRow({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-8">
      <div className="min-w-0">
        <div className="text-xs text-gray-400">{label}</div>
        {description && (
          <div className="mt-0.5 text-[10px] text-gray-600">{description}</div>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

const SYMBOLS = ["BTC", "ETH", "XRP", "SOL", "DOGE"];

const TIMEZONES = [
  { value: "Asia/Seoul", label: "Asia/Seoul (KST)" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo (JST)" },
  { value: "America/New_York", label: "America/New_York (EST)" },
  { value: "Europe/London", label: "Europe/London (GMT)" },
  { value: "UTC", label: "UTC" },
];

export function SettingsPage() {
  const queryClient = useQueryClient();

  const { data: prefs, isLoading, isError } = useQuery({
    queryKey: ["preferences"],
    queryFn: async () => {
      const res = await api.getPreferences();
      return res.data;
    },
  });

  // Local form state — mirrors server state, updated on fetch
  const [dashboard, setDashboard] = useState<DashboardPreferences | null>(null);
  const [notifications, setNotifications] = useState<NotificationPreferences | null>(null);
  const [timezone, setTimezone] = useState("Asia/Seoul");
  const [locale, setLocale] = useState<"ko-KR" | "en-US">("ko-KR");

  // Sync fetched prefs into local state
  useEffect(() => {
    if (prefs) {
      setDashboard(prefs.dashboard);
      setNotifications(prefs.notifications);
      setTimezone(prefs.timezone);
      setLocale(prefs.locale);
    }
  }, [prefs]);

  // Dirty check
  const isDirty =
    prefs != null &&
    dashboard != null &&
    notifications != null &&
    JSON.stringify({ dashboard, notifications, timezone, locale }) !==
      JSON.stringify({
        dashboard: prefs.dashboard,
        notifications: prefs.notifications,
        timezone: prefs.timezone,
        locale: prefs.locale,
      });

  const mutation = useMutation({
    mutationFn: (body: Partial<UserPreferences>) => api.updatePreferences(body),
    onSuccess: (res) => {
      queryClient.setQueryData(["preferences"], res.data);
    },
  });

  const handleSave = useCallback(() => {
    if (!dashboard || !notifications) return;
    mutation.mutate({ dashboard, notifications, timezone, locale });
  }, [dashboard, notifications, timezone, locale, mutation]);

  const handleReset = useCallback(() => {
    if (prefs) {
      setDashboard(prefs.dashboard);
      setNotifications(prefs.notifications);
      setTimezone(prefs.timezone);
      setLocale(prefs.locale);
    }
  }, [prefs]);

  // Exchange visibility toggle
  const toggleExchange = useCallback(
    (exId: string) => {
      if (!dashboard) return;
      const visible = dashboard.visible_exchanges as string[];
      const next = visible.includes(exId)
        ? visible.filter((e) => e !== exId)
        : [...visible, exId];
      // Keep at least one exchange
      if (next.length === 0) return;
      setDashboard({ ...dashboard, visible_exchanges: next as DashboardPreferences["visible_exchanges"] });
    },
    [dashboard],
  );

  // ── Loading / Error ──────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-semibold text-white">설정</h2>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-40 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
            />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !dashboard || !notifications) {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-semibold text-white">설정</h2>
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 p-6 text-center">
          <p className="text-sm text-red-400">환경설정을 불러오지 못했습니다.</p>
          <p className="mt-1 text-xs text-gray-600">
            백엔드가 실행 중인지 확인하고 새로고침해 주세요.
          </p>
        </div>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">설정</h2>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              onClick={handleReset}
              className="rounded px-3 py-1.5 text-xs text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
            >
              되돌리기
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!isDirty || mutation.isPending}
            className={`rounded px-4 py-1.5 text-sm font-medium transition-colors ${
              isDirty
                ? "bg-blue-600 text-white hover:bg-blue-500"
                : "bg-gray-800 text-gray-600 cursor-not-allowed"
            }`}
          >
            {mutation.isPending ? "저장 중..." : "변경사항 저장"}
          </button>
        </div>
      </div>

      {/* Success / Error toast */}
      {mutation.isSuccess && !isDirty && (
        <div className="rounded-lg border border-green-900/50 bg-green-950/20 px-4 py-2 text-xs text-green-400">
          설정이 저장되었습니다.
        </div>
      )}
      {mutation.isError && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-2 text-xs text-red-400">
          설정 저장에 실패했습니다. 다시 시도해 주세요.
        </div>
      )}

      {/* Dashboard Section */}
      <Section title="대시보드" description="기본 대시보드 화면을 설정합니다.">
        <FieldRow label="기본 종목" description="처음 로드 시 표시할 종목">
          <select
            value={dashboard.default_symbol}
            onChange={(e) =>
              setDashboard({ ...dashboard, default_symbol: e.target.value })
            }
            className="rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-blue-600"
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </FieldRow>

        <div>
          <div className="text-xs text-gray-400">표시 거래소</div>
          <div className="mt-0.5 text-[10px] text-gray-600">
            대시보드에 표시할 거래소를 선택하세요
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {ALL_EXCHANGES.map((ex) => {
              const active = (dashboard.visible_exchanges as string[]).includes(ex);
              return (
                <button
                  key={ex}
                  type="button"
                  onClick={() => toggleExchange(ex)}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    active
                      ? "border-blue-600/50 bg-blue-600/10 text-blue-400"
                      : "border-gray-700 bg-gray-800 text-gray-500 hover:border-gray-600"
                  }`}
                >
                  {EXCHANGE_NAMES[ex]}
                </button>
              );
            })}
          </div>
        </div>

        <FieldRow label="스프레드 표시" description="스프레드 값 표시 방식">
          <ButtonGroup
            options={[
              { value: "percentage" as const, label: "%" },
              { value: "absolute" as const, label: "절대값" },
            ]}
            value={dashboard.spread_matrix_mode}
            onChange={(v) =>
              setDashboard({ ...dashboard, spread_matrix_mode: v })
            }
          />
        </FieldRow>

        <FieldRow label="차트 간격" description="기본 차트 시간 간격">
          <ButtonGroup
            options={[
              { value: "10s" as const, label: "10s" },
              { value: "1m" as const, label: "1m" },
              { value: "5m" as const, label: "5m" },
              { value: "1h" as const, label: "1h" },
            ]}
            value={dashboard.chart_interval}
            onChange={(v) => setDashboard({ ...dashboard, chart_interval: v })}
          />
        </FieldRow>

        <FieldRow label="테마">
          <ButtonGroup
            options={[
              { value: "dark" as const, label: "다크" },
              { value: "light" as const, label: "라이트" },
            ]}
            value={dashboard.theme}
            onChange={(v) => setDashboard({ ...dashboard, theme: v })}
          />
        </FieldRow>
      </Section>

      {/* Notifications Section */}
      <Section
        title="알림"
        description="텔레그램 및 사운드 알림을 설정합니다."
      >
        <FieldRow label="텔레그램 알림" description="텔레그램 봇으로 알림 전송">
          <Toggle
            enabled={notifications.telegram_enabled}
            onChange={(v) =>
              setNotifications({ ...notifications, telegram_enabled: v })
            }
          />
        </FieldRow>

        {notifications.telegram_enabled && (
          <FieldRow label="텔레그램 채팅 ID" description="알림을 받을 텔레그램 채팅 ID">
            <input
              type="number"
              value={notifications.telegram_chat_id ?? ""}
              onChange={(e) =>
                setNotifications({
                  ...notifications,
                  telegram_chat_id: e.target.value ? Number(e.target.value) : null,
                })
              }
              placeholder="예: 123456789"
              className="w-44 rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-right font-mono text-sm text-gray-300 outline-none placeholder:text-gray-700 focus:border-blue-600"
            />
          </FieldRow>
        )}

        <FieldRow label="사운드 알림" description="알림 발생 시 소리 재생">
          <Toggle
            enabled={notifications.sound_enabled}
            onChange={(v) =>
              setNotifications({ ...notifications, sound_enabled: v })
            }
          />
        </FieldRow>
      </Section>

      {/* General Section */}
      <Section title="일반" description="언어 및 시간대를 설정합니다.">
        <FieldRow label="시간대">
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 outline-none focus:border-blue-600"
          >
            {TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>
                {tz.label}
              </option>
            ))}
          </select>
        </FieldRow>

        <FieldRow label="언어">
          <ButtonGroup
            options={[
              { value: "ko-KR" as const, label: "한국어" },
              { value: "en-US" as const, label: "English" },
            ]}
            value={locale}
            onChange={(v) => setLocale(v)}
          />
        </FieldRow>
      </Section>
    </div>
  );
}
