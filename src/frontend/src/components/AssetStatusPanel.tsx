/**
 * AssetStatusPanel — shows deposit/withdrawal status per exchange for a symbol.
 *
 * Fetches from GET /api/v1/asset-status?symbol=BTC every 60 seconds.
 * Shows green/red indicators for deposit and withdrawal availability.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EXCHANGE_NAMES } from "@/lib/format";
import type { AssetStatusEntry, GateLendingEntry } from "@/types";

interface AssetStatusPanelProps {
  symbol: string;
}

function StatusDot({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${
        enabled ? "bg-green-500" : "bg-red-500"
      }`}
      title={enabled ? "가능" : "중지"}
    />
  );
}

export function AssetStatusPanel({ symbol }: AssetStatusPanelProps) {
  const { data: statusData, isLoading } = useQuery({
    queryKey: ["asset-status", symbol],
    queryFn: async () => {
      const res = await api.getAssetStatus({ symbol });
      return res.data as AssetStatusEntry[];
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const { data: lendingData } = useQuery({
    queryKey: ["gate-lending"],
    queryFn: async () => {
      try {
        const res = await api.getGateLending();
        return res.data as GateLendingEntry[];
      } catch {
        return [];
      }
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const gateLending = lendingData?.find(
    (l) => l.currency.toUpperCase() === symbol.toUpperCase(),
  );

  if (isLoading) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
        <div className="h-4 w-24 animate-pulse rounded bg-gray-800" />
      </div>
    );
  }

  const statuses = statusData ?? [];
  if (statuses.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-gray-500">
        입출금 상태 — {symbol}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500">
              <th className="pb-2 text-left font-medium">거래소</th>
              <th className="pb-2 text-center font-medium">입금</th>
              <th className="pb-2 text-center font-medium">출금</th>
              <th className="pb-2 text-center font-medium">비고</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {statuses.map((s) => (
              <tr key={s.exchange} className="text-gray-300">
                <td className="py-1.5">
                  {EXCHANGE_NAMES[s.exchange] ?? s.exchange}
                </td>
                <td className="py-1.5 text-center">
                  <StatusDot enabled={s.deposit_enabled} />
                </td>
                <td className="py-1.5 text-center">
                  <StatusDot enabled={s.withdraw_enabled} />
                </td>
                <td className="py-1.5 text-center text-gray-500">
                  {s.exchange === "gate" && gateLending?.borrowable && (
                    <span
                      className="mr-2 text-[10px] text-blue-400"
                      title={`최소 ${gateLending.min_amount} ${symbol} / 레버리지 ${gateLending.leverage}x${Number(gateLending.amount) > 0 ? ` / 대출가능 ${Number(gateLending.amount).toLocaleString()} ${symbol}` : ""}`}
                    >
                      대출가능 (최소 {gateLending.min_amount} {symbol}, {gateLending.leverage}x)
                    </span>
                  )}
                  {s.networks.length > 0 && (
                    <span className="text-[10px]">
                      {s.networks.map((n) => (
                        <span
                          key={n.network}
                          className={`mr-1 inline-block rounded px-1.5 py-0.5 ${
                            n.withdraw_enabled
                              ? "bg-gray-800 text-gray-400"
                              : "bg-red-950/30 text-red-400"
                          }`}
                          title={`${n.network}: 입금 ${n.deposit_enabled ? "가능" : "중지"} / 출금 ${n.withdraw_enabled ? "가능" : "중지"}${n.withdraw_fee ? ` / 수수료 ${n.withdraw_fee}` : ""}`}
                        >
                          {n.network}
                        </span>
                      ))}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
