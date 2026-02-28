/**
 * ExchangePriceCard — displays price info for a single exchange.
 *
 * Shows exchange name, connection status dot, BTC and ETH prices,
 * last update timestamp with staleness indicator, and brief flash
 * animation on price updates.
 */
import { memo, useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/shallow";
import { usePriceStore } from "@/stores/priceStore";
import { ConnectorState } from "@/types/enums";
import type { ExchangeId, Currency } from "@/types/enums";
import { EXCHANGE_NAMES, formatPrice, timeAgo } from "@/lib/format";

interface ExchangePriceCardProps {
  exchange: ExchangeId;
  currency: Currency;
  symbols?: string[];
}

const STATE_DOT: Record<string, string> = {
  [ConnectorState.ACTIVE]: "bg-green-500",
  [ConnectorState.CONNECTED]: "bg-green-400",
  [ConnectorState.SUBSCRIBING]: "bg-yellow-400",
  [ConnectorState.CONNECTING]: "bg-yellow-500",
  [ConnectorState.WAIT_RETRY]: "bg-orange-500",
  [ConnectorState.DISCONNECTED]: "bg-red-500",
};

function PriceRow({
  symbol,
  exchange,
  currency,
}: {
  symbol: string;
  exchange: ExchangeId;
  currency: Currency;
}) {
  const key = `${exchange}:${symbol}`;
  const entry = usePriceStore((s) => s.prices[key]);
  const [flashClass, setFlashClass] = useState("");
  const prevPrice = useRef<string | null>(null);

  useEffect(() => {
    if (!entry) return;
    const prev = prevPrice.current;
    prevPrice.current = entry.price;
    if (prev !== null && prev !== entry.price) {
      const prevNum = Number(prev);
      const currNum = Number(entry.price);
      if (currNum > prevNum) {
        setFlashClass("text-green-400");
      } else if (currNum < prevNum) {
        setFlashClass("text-red-400");
      }
      const timer = setTimeout(() => setFlashClass(""), 600);
      return () => clearTimeout(timer);
    }
  }, [entry]);

  if (!entry) {
    return (
      <div className="flex items-center justify-between py-1">
        <span className="text-xs text-gray-500">{symbol}</span>
        <span className="text-xs text-gray-600">--</span>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-gray-400">{symbol}</span>
      <span
        className={`font-mono text-sm tabular-nums transition-colors duration-500 ${flashClass || "text-gray-100"}`}
      >
        {formatPrice(entry.price, currency)}
      </span>
    </div>
  );
}

export const ExchangePriceCard = memo(function ExchangePriceCard({
  exchange,
  currency,
  symbols = ["BTC", "ETH"],
}: ExchangePriceCardProps) {
  const exchangeStatus = usePriceStore((s) => s.exchangeStatuses[exchange]);
  const state = exchangeStatus?.state ?? ConnectorState.DISCONNECTED;
  const dotClass = STATE_DOT[state] ?? "bg-gray-600";

  // Granular selector: only re-render when latestTs or isStale actually changes
  const { latestTs, isStale } = usePriceStore(
    useShallow((s) => {
      let lt = 0;
      let stale = false;
      for (const sym of symbols) {
        const entry = s.prices[`${exchange}:${sym}`];
        if (entry) {
          if (entry.timestamp_ms > lt) lt = entry.timestamp_ms;
          if (entry.is_stale) stale = true;
        }
      }
      return { latestTs: lt, isStale: stale };
    }),
  );

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${dotClass} ${state === ConnectorState.CONNECTING ? "animate-pulse" : ""}`}
          title={state}
        />
        <span className="text-sm font-medium text-gray-200">
          {EXCHANGE_NAMES[exchange]}
        </span>
        <span className="ml-auto rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
          {currency}
        </span>
      </div>

      {/* Prices */}
      <div className="space-y-0.5">
        {symbols.map((sym) => (
          <PriceRow
            key={sym}
            symbol={sym}
            exchange={exchange}
            currency={currency}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-3 flex items-center gap-2 border-t border-gray-800 pt-2">
        {latestTs > 0 ? (
          <span
            className={`text-[10px] ${isStale ? "text-orange-400" : "text-gray-600"}`}
          >
            {isStale && "지연 · "}
            {timeAgo(latestTs)}
          </span>
        ) : (
          <span className="text-[10px] text-gray-700">데이터 없음</span>
        )}
        {exchangeStatus?.latency_ms != null && (
          <span className="ml-auto text-[10px] text-gray-600">
            {exchangeStatus.latency_ms}ms
          </span>
        )}
      </div>
    </div>
  );
});
