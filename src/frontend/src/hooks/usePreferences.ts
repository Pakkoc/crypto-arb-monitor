/**
 * usePreferences — shared hook for reading user preferences via TanStack Query.
 *
 * All components that need preferences should use this hook instead of
 * fetching directly. The query is cached globally under the ["preferences"] key,
 * so only one API call is made regardless of how many components subscribe.
 */
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";
import type { UserPreferences, DashboardPreferences, NotificationPreferences } from "@/types";

const DEFAULT_DASHBOARD: DashboardPreferences = {
  default_symbol: "BTC",
  visible_exchanges: ["upbit", "bithumb", "binance", "bybit", "gate"],
  spread_matrix_mode: "percentage",
  chart_interval: "1h",
  theme: "dark",
  min_spread_pct: 0,
};

const DEFAULT_NOTIFICATIONS: NotificationPreferences = {
  telegram_enabled: false,
  telegram_chat_id: null,
  sound_enabled: false,
};

const DEFAULT_PREFS: UserPreferences = {
  dashboard: DEFAULT_DASHBOARD,
  notifications: DEFAULT_NOTIFICATIONS,
  timezone: "Asia/Seoul",
  locale: "ko-KR",
};

export function usePreferences() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["preferences"],
    queryFn: async () => {
      const res = await api.getPreferences();
      return res.data;
    },
    staleTime: 60_000, // 1 minute — preferences rarely change
  });

  return {
    prefs: data ?? DEFAULT_PREFS,
    dashboard: data?.dashboard ?? DEFAULT_DASHBOARD,
    notifications: data?.notifications ?? DEFAULT_NOTIFICATIONS,
    timezone: data?.timezone ?? "Asia/Seoul",
    locale: data?.locale ?? "ko-KR",
    isLoading,
    isError,
  };
}
