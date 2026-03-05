/**
 * Dashboard — main arbitrage monitoring view integrating all widgets.
 *
 * Layout:
 * - Top: ExchangeStatusBar
 * - Row 1: ExchangePriceCard grid (5 exchanges)
 * - Row 2: SpreadMatrix + RecentAlerts
 * - Row 3: SpreadChart + PriceChart
 */
import { useState, useMemo } from "react";
import { usePriceStore } from "@/stores/priceStore";
import { usePreferences } from "@/hooks/usePreferences";
import { ExchangeStatusBar } from "@/components/ExchangeStatusBar";
import { ExchangePriceCard } from "@/components/ExchangePriceCard";
import { SpreadMatrix } from "@/components/SpreadMatrix";
import { SpreadChart } from "@/components/SpreadChart";
import { PriceChart } from "@/components/PriceChart";
import { RecentAlerts } from "@/components/RecentAlerts";
import { AssetStatusPanel } from "@/components/AssetStatusPanel";
import { KRW_EXCHANGES, USDT_EXCHANGES } from "@/lib/format";
import type { WsStatus } from "@/hooks/useWebSocket";
import type { ExchangeId } from "@/types/enums";

interface DashboardProps {
  wsStatus: WsStatus;
}

export function Dashboard({ wsStatus }: DashboardProps) {
  const isInitialized = usePriceStore((s) => s.isInitialized);
  const { dashboard } = usePreferences();
  const [selectedSymbol, setSelectedSymbol] = useState(dashboard.default_symbol);

  // Filter exchanges based on user preferences
  const visibleKrw = useMemo(
    () => KRW_EXCHANGES.filter((ex) => (dashboard.visible_exchanges as string[]).includes(ex)),
    [dashboard.visible_exchanges],
  );
  const visibleUsdt = useMemo(
    () => USDT_EXCHANGES.filter((ex) => (dashboard.visible_exchanges as string[]).includes(ex)),
    [dashboard.visible_exchanges],
  );

  // Derive symbol list as a stable string — only re-renders when the set of symbols changes
  const symbolsKey = usePriceStore((s) => {
    const syms = new Set<string>();
    for (const key of Object.keys(s.prices)) {
      const sym = key.split(":")[1];
      if (sym) syms.add(sym);
    }
    return Array.from(syms).sort().join(",");
  });

  const availableSymbols = useMemo(
    () => (symbolsKey ? symbolsKey.split(",") : ["BTC", "ETH"]),
    [symbolsKey],
  );

  return (
    <div className="space-y-4">
      {/* Status bar */}
      <ExchangeStatusBar wsStatus={wsStatus} />

      {/* Symbol selector + min spread filter */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">종목:</span>
        <div className="flex gap-1">
          {availableSymbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSelectedSymbol(sym)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                selectedSymbol === sym
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
        </div>
      </div>

      {/* Loading state */}
      {!isInitialized ? (
        <div className="space-y-4">
          {/* Skeleton: Price cards */}
          <div className="grid grid-cols-5 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-36 animate-pulse rounded-lg border border-gray-800 bg-gray-900"
              >
                <div className="p-4">
                  <div className="mb-3 h-4 w-20 rounded bg-gray-800" />
                  <div className="space-y-2">
                    <div className="h-3 w-full rounded bg-gray-800" />
                    <div className="h-3 w-3/4 rounded bg-gray-800" />
                  </div>
                </div>
              </div>
            ))}
          </div>
          {/* Skeleton: Charts */}
          <div className="grid grid-cols-2 gap-4">
            <div className="h-64 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
            <div className="h-64 animate-pulse rounded-lg border border-gray-800 bg-gray-900" />
          </div>
          <div className="flex h-48 items-center justify-center text-sm text-gray-500">
            실시간 데이터 스트림에 연결 중...
          </div>
        </div>
      ) : (
        <>
          {/* Row 1: Exchange Price Cards */}
          <div className={`grid gap-3`} style={{ gridTemplateColumns: `repeat(${visibleKrw.length + visibleUsdt.length}, minmax(0, 1fr))` }}>
            {visibleKrw.map((ex) => (
              <ExchangePriceCard
                key={ex}
                exchange={ex as ExchangeId}
                currency="KRW"
                symbols={availableSymbols}
              />
            ))}
            {visibleUsdt.map((ex) => (
              <ExchangePriceCard
                key={ex}
                exchange={ex as ExchangeId}
                currency="USDT"
                symbols={availableSymbols}
              />
            ))}
          </div>

          {/* Row 2: Spread Matrix + Recent Alerts */}
          <div className="grid grid-cols-3 gap-4">
            <div className="relative z-10 col-span-2 rounded-lg border border-gray-800 bg-gray-900 p-4">
              <SpreadMatrix symbol={selectedSymbol} />
            </div>
            <div>
              <RecentAlerts />
            </div>
          </div>

          {/* Row 3: Asset Status */}
          <AssetStatusPanel symbol={selectedSymbol} />

          {/* Row 4: Charts */}
          <div className="grid grid-cols-2 gap-4">
            <SpreadChart symbol={selectedSymbol} />
            <PriceChart
              defaultSymbol={selectedSymbol}
              defaultExchange="bithumb"
            />
          </div>
        </>
      )}
    </div>
  );
}
