/**
 * SpreadChart — real-time spread trend chart using Recharts LineChart.
 *
 * Shows spread percentage over time for selected exchange pairs.
 * Auto-updates with new WebSocket data from the priceStore spread history.
 */
import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import { usePriceStore } from "@/stores/priceStore";
import { usePreferences } from "@/hooks/usePreferences";
import { EXCHANGE_NAMES, KRW_EXCHANGES, USDT_EXCHANGES } from "@/lib/format";

interface SpreadChartProps {
  symbol: string;
}

type TimeRange = "1h" | "6h" | "24h";

const TIME_RANGE_MS: Record<TimeRange, number> = {
  "1h": 60 * 60 * 1000,
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
};

/** Colors for each exchange pair line. */
const LINE_COLORS = [
  "#3b82f6", // blue
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
];

interface ChartDataPoint {
  time: number;
  timeStr: string;
  [key: string]: string | number; // spread values keyed by pair label
}

function formatTimeAxis(timestampMs: number): string {
  const d = new Date(timestampMs);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

/** Map dashboard chart_interval setting to SpreadChart TimeRange */
function mapIntervalToRange(interval: string): TimeRange {
  switch (interval) {
    case "10s":
    case "1m":
      return "1h";
    case "5m":
      return "6h";
    case "1h":
      return "24h";
    default:
      return "1h";
  }
}

export function SpreadChart({ symbol }: SpreadChartProps) {
  const { dashboard } = usePreferences();
  const [timeRange, setTimeRange] = useState<TimeRange>(() => mapIntervalToRange(dashboard.chart_interval));

  // Build the set of spread keys for this symbol — only re-derive when spreads keys change
  const pairKeysStr = usePriceStore((s) => {
    const keys: string[] = [];
    for (const krwEx of KRW_EXCHANGES) {
      for (const usdtEx of USDT_EXCHANGES) {
        const key = `${krwEx}:${usdtEx}:${symbol}`;
        if (s.spreads[key] || s.spreadHistory[key]?.length) {
          keys.push(key);
        }
      }
    }
    return keys.slice(0, 6).join("|");
  });

  const activePairs = useMemo(() => {
    if (!pairKeysStr) return [];
    return pairKeysStr.split("|").map((key) => {
      const [a, b] = key.split(":");
      return { key, label: `${EXCHANGE_NAMES[a]}/${EXCHANGE_NAMES[b]}` };
    });
  }, [pairKeysStr]);

  // Subscribe to a fingerprint of the relevant history lengths — avoids full object subscription
  const historyFingerprint = usePriceStore((s) => {
    if (activePairs.length === 0) return "";
    return activePairs.map((p) => `${p.key}:${s.spreadHistory[p.key]?.length ?? 0}`).join("|");
  });

  // Build chart data only when fingerprint, time range, or pairs change
  const chartData = useMemo(() => {
    if (activePairs.length === 0 || !historyFingerprint) return [];

    const store = usePriceStore.getState();
    const cutoff = Date.now() - TIME_RANGE_MS[timeRange];
    const pointMap = new Map<number, ChartDataPoint>();

    for (const pair of activePairs) {
      const history = store.spreadHistory[pair.key] ?? [];
      for (const entry of history) {
        if (entry.timestamp_ms < cutoff) continue;
        const bucket = Math.floor(entry.timestamp_ms / 10000) * 10000;
        let point = pointMap.get(bucket);
        if (!point) {
          point = { time: bucket, timeStr: formatTimeAxis(bucket) };
          pointMap.set(bucket, point);
        }
        point[pair.label] = Number(entry.spread_pct);
      }
    }

    return Array.from(pointMap.values()).sort((a, b) => a.time - b.time);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePairs, historyFingerprint, timeRange]);

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">
          스프레드 추이 — {symbol}
        </h3>
        <div className="flex gap-1">
          {(["1h", "6h", "24h"] as TimeRange[]).map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={`rounded px-2 py-0.5 text-xs transition-colors ${
                timeRange === range
                  ? "bg-blue-600 text-white"
                  : "text-gray-500 hover:bg-gray-800 hover:text-gray-300"
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      {chartData.length === 0 ? (
        <div className="flex h-48 items-center justify-center text-xs text-gray-600">
          스프레드 이력이 없습니다. 데이터가 수신되면 여기에 표시됩니다.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="timeStr"
              tick={{ fontSize: 10, fill: "#6b7280" }}
              stroke="#374151"
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#6b7280" }}
              stroke="#374151"
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "8px",
                fontSize: 11,
              }}
              labelStyle={{ color: "#9ca3af" }}
              formatter={(value: number) => [`${value.toFixed(2)}%`, ""]}
            />
            <Legend
              wrapperStyle={{ fontSize: 10 }}
              iconSize={8}
            />
            <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="2 2" />
            {activePairs.map((pair, idx) => (
              <Line
                key={pair.key}
                type="monotone"
                dataKey={pair.label}
                stroke={LINE_COLORS[idx % LINE_COLORS.length]}
                strokeWidth={1.5}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
