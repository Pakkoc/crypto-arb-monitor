/**
 * DashboardPage — wraps the Dashboard component and manages the WebSocket.
 *
 * Also pre-fetches exchange status and alert configs on mount.
 */
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlerts } from "@/hooks/useAlerts";
import { Dashboard } from "@/components/Dashboard";

export function DashboardPage() {
  const { status } = useWebSocket({ enabled: true });

  // Pre-fetch alerts so the RecentAlerts widget has config data
  useAlerts();

  return <Dashboard wsStatus={status} />;
}
