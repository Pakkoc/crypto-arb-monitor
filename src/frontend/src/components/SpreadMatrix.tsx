/**
 * SpreadMatrix — cross-exchange spread comparison grid.
 *
 * Shows kimchi premium spreads (KRW exchanges vs USDT exchanges)
 * and same-currency spreads among KRW exchanges.
 * Color-coded cells: green (< 1%), yellow (1-2%), orange (2-3%), red (> 3%).
 */
import { memo, useState } from "react";
import { usePriceStore } from "@/stores/priceStore";
import {
  EXCHANGE_NAMES,
  KRW_EXCHANGES,
  USDT_EXCHANGES,
  formatSpreadPct,
  spreadBgClass,
  spreadColorClass,
  formatPrice,
  timeAgo,
} from "@/lib/format";

interface SpreadMatrixProps {
  symbol: string;
}

interface SpreadCellData {
  spreadPct: string;
  isStale: boolean;
  staleReason: string | null;
  priceA: string;
  priceACurrency: string;
  priceB: string;
  priceBCurrency: string;
  fxRate: string | null;
  timestampMs: number;
}

const SpreadCell = memo(function SpreadCell({
  data,
  rowExchange,
  colExchange,
}: {
  data: SpreadCellData | null;
  rowExchange: string;
  colExchange: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (rowExchange === colExchange) {
    return (
      <td className="border border-gray-800 bg-gray-900/30 p-2 text-center text-xs text-gray-700">
        —
      </td>
    );
  }

  if (!data) {
    return (
      <td className="border border-gray-800 p-2 text-center text-xs text-gray-700">
        N/A
      </td>
    );
  }

  return (
    <td
      className={`relative cursor-default border border-gray-800 p-2 text-center ${spreadBgClass(data.spreadPct)} ${data.isStale ? "opacity-60" : ""}`}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span
        className={`font-mono text-sm tabular-nums font-medium ${spreadColorClass(data.spreadPct)}`}
      >
        {formatSpreadPct(data.spreadPct)}
      </span>
      {data.isStale && (
        <span className="ml-1 text-[10px] text-orange-400" title={data.staleReason ?? "Stale"}>
          !
        </span>
      )}

      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 rounded-lg border border-gray-700 bg-gray-800 p-3 shadow-xl">
          <div className="text-left text-xs">
            <div className="mb-1.5 font-medium text-gray-200">
              {EXCHANGE_NAMES[rowExchange]} vs {EXCHANGE_NAMES[colExchange]}
            </div>
            <div className="space-y-1 text-gray-400">
              <div className="flex justify-between">
                <span>{EXCHANGE_NAMES[rowExchange]}:</span>
                <span className="font-mono text-gray-300">
                  {formatPrice(data.priceA, data.priceACurrency as "KRW" | "USDT")}
                </span>
              </div>
              <div className="flex justify-between">
                <span>{EXCHANGE_NAMES[colExchange]}:</span>
                <span className="font-mono text-gray-300">
                  {formatPrice(data.priceB, data.priceBCurrency as "KRW" | "USDT")}
                </span>
              </div>
              {data.fxRate && (
                <div className="flex justify-between">
                  <span>환율:</span>
                  <span className="font-mono text-gray-300">
                    ₩{Number(data.fxRate).toLocaleString("ko-KR")}
                  </span>
                </div>
              )}
              <div className="flex justify-between border-t border-gray-700 pt-1">
                <span>스프레드:</span>
                <span className={`font-mono font-medium ${spreadColorClass(data.spreadPct)}`}>
                  {formatSpreadPct(data.spreadPct)}
                </span>
              </div>
              <div className="text-[10px] text-gray-600">
                {timeAgo(data.timestampMs)}
              </div>
            </div>
          </div>
          {/* Arrow */}
          <div className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-b border-r border-gray-700 bg-gray-800" />
        </div>
      )}
    </td>
  );
});

export function SpreadMatrix({ symbol }: SpreadMatrixProps) {
  const spreads = usePriceStore((s) => s.spreads);

  // Build lookup for spreads
  const getSpreadData = (
    exchangeA: string,
    exchangeB: string,
  ): SpreadCellData | null => {
    // Try both orderings
    const key1 = `${exchangeA}:${exchangeB}:${symbol}`;
    const key2 = `${exchangeB}:${exchangeA}:${symbol}`;
    const entry = spreads[key1] ?? spreads[key2];
    if (!entry) return null;

    // If we found the reversed key, negate the spread
    const isReversed = !spreads[key1] && !!spreads[key2];
    const pct = isReversed
      ? String(-Number(entry.spread_pct))
      : entry.spread_pct;

    return {
      spreadPct: pct,
      isStale: entry.is_stale,
      staleReason: entry.stale_reason,
      priceA: isReversed ? entry.price_b : entry.price_a,
      priceACurrency: isReversed
        ? entry.price_b_currency
        : entry.price_a_currency,
      priceB: isReversed ? entry.price_a : entry.price_b,
      priceBCurrency: isReversed
        ? entry.price_a_currency
        : entry.price_b_currency,
      fxRate: entry.fx_rate,
      timestampMs: entry.timestamp_ms,
    };
  };

  return (
    <div className="space-y-4">
      {/* Kimchi Premium Matrix: KRW rows vs USDT columns */}
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
          김치 프리미엄 ({symbol})
        </h3>
        <div className="overflow-visible">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="border border-gray-800 bg-gray-900/50 p-2 text-left text-xs text-gray-500">
                  KRW \ USDT
                </th>
                {USDT_EXCHANGES.map((ex) => (
                  <th
                    key={ex}
                    className="border border-gray-800 bg-gray-900/50 p-2 text-center text-xs text-gray-400"
                  >
                    {EXCHANGE_NAMES[ex]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {KRW_EXCHANGES.map((rowEx) => (
                <tr key={rowEx}>
                  <td className="border border-gray-800 bg-gray-900/50 p-2 text-xs text-gray-400">
                    {EXCHANGE_NAMES[rowEx]}
                  </td>
                  {USDT_EXCHANGES.map((colEx) => (
                    <SpreadCell
                      key={`${rowEx}-${colEx}`}
                      data={getSpreadData(rowEx, colEx)}
                      rowExchange={rowEx}
                      colExchange={colEx}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Same-currency spreads among KRW exchanges */}
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
          원화 거래소 간 스프레드 ({symbol})
        </h3>
        <div className="overflow-visible">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="border border-gray-800 bg-gray-900/50 p-2 text-left text-xs text-gray-500" />
                {KRW_EXCHANGES.map((ex) => (
                  <th
                    key={ex}
                    className="border border-gray-800 bg-gray-900/50 p-2 text-center text-xs text-gray-400"
                  >
                    {EXCHANGE_NAMES[ex]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {KRW_EXCHANGES.map((rowEx) => (
                <tr key={rowEx}>
                  <td className="border border-gray-800 bg-gray-900/50 p-2 text-xs text-gray-400">
                    {EXCHANGE_NAMES[rowEx]}
                  </td>
                  {KRW_EXCHANGES.map((colEx) => (
                    <SpreadCell
                      key={`${rowEx}-${colEx}`}
                      data={
                        rowEx === colEx
                          ? null
                          : getSpreadData(rowEx, colEx)
                      }
                      rowExchange={rowEx}
                      colExchange={colEx}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-[10px] text-gray-600">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-green-900/40" />
          &lt; 1%
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-yellow-900/40" />
          1-2%
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-orange-900/40" />
          2-3%
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded bg-red-900/40" />
          &gt; 3%
        </span>
      </div>
    </div>
  );
}
