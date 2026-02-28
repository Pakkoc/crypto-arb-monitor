/**
 * useAlerts — TanStack Query hooks for alert CRUD operations.
 *
 * Wraps the REST API calls and integrates with the alertStore.
 * Wraps REST API calls with query caching and optimistic updates.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { useAlertStore } from "@/stores/alertStore";
import type { AlertConfigCreate, AlertConfigUpdate } from "@/types";

const QUERY_KEY = ["alerts"] as const;

export function useAlerts() {
  const { setConfigs } = useAlertStore();
  const queryClient = useQueryClient();

  const alertsQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const response = await api.listAlerts();
      const configs = response.data ?? [];
      setConfigs(configs);
      return configs;
    },
    refetchInterval: 30_000, // Refresh every 30s as background sync
    staleTime: 10_000,
  });

  const createMutation = useMutation({
    mutationFn: (body: AlertConfigCreate) => api.createAlert(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: AlertConfigUpdate }) =>
      api.updateAlert(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });

  return {
    alerts: alertsQuery.data ?? [],
    isLoading: alertsQuery.isLoading,
    isError: alertsQuery.isError,
    createAlert: createMutation.mutateAsync,
    updateAlert: updateMutation.mutateAsync,
    deleteAlert: deleteMutation.mutateAsync,
  };
}
