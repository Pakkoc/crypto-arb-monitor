/**
 * PriceChart — price history chart using TradingView Lightweight Charts.
 *
 * Displays price history for a selected symbol + exchange combination.
 * Supports line chart and candlestick chart modes.
 * Tick data is aggregated into OHLC candles for candlestick display.
 */
import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type UTCTimestamp,
} from "lightweight-charts";
import { usePriceStore } from "@/stores/priceStore";
import { usePreferences } from "@/hooks/usePreferences";
import { EXCHANGE_NAMES, ALL_EXCHANGES } from "@/lib/format";
import type { ExchangeId, Currency } from "@/types/enums";

interface PriceChartProps {
  defaultSymbol?: string;
  defaultExchange?: ExchangeId;
}

type TimeRange = "1h" | "6h" | "24h" | "7d";
type ChartType = "line" | "candle";

const TIME_RANGE_MS: Record<TimeRange, number> = {
  "1h": 60 * 60 * 1000,
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

/** Candle bucket size (ms) per time range */
const CANDLE_BUCKET_MS: Record<TimeRange, number> = {
  "1h": 60 * 1000,         // 1분봉
  "6h": 5 * 60 * 1000,     // 5분봉
  "24h": 15 * 60 * 1000,   // 15분봉
  "7d": 60 * 60 * 1000,    // 1시간봉
};

interface TickData {
  time: UTCTimestamp;
  value: number;
  volume: number;
}

interface OhlcData {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** Aggregate tick data into OHLC candles */
function aggregateToOhlc(ticks: TickData[], bucketMs: number): OhlcData[] {
  if (ticks.length === 0) return [];

  const bucketSec = Math.floor(bucketMs / 1000);
  const bucketMap = new Map<number, OhlcData>();

  for (const tick of ticks) {
    const bucket = (Math.floor(tick.time / bucketSec) * bucketSec) as UTCTimestamp;
    const existing = bucketMap.get(bucket);
    if (!existing) {
      bucketMap.set(bucket, {
        time: bucket,
        open: tick.value,
        high: tick.value,
        low: tick.value,
        close: tick.value,
        volume: tick.volume,
      });
    } else {
      existing.high = Math.max(existing.high, tick.value);
      existing.low = Math.min(existing.low, tick.value);
      existing.close = tick.value;
      existing.volume = tick.volume;
    }
  }

  return Array.from(bucketMap.values()).sort((a, b) => a.time - b.time);
}

/** Map dashboard chart_interval setting to PriceChart TimeRange */
function mapIntervalToTimeRange(interval: string): TimeRange {
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

export function PriceChart({
  defaultSymbol = "BTC",
  defaultExchange = "bithumb",
}: PriceChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceSeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<SeriesType> | null>(null);

  const { dashboard } = usePreferences();
  const [selectedSymbol, setSelectedSymbol] = useState(defaultSymbol);
  const [selectedExchange, setSelectedExchange] =
    useState<ExchangeId>(defaultExchange);
  const [timeRange, setTimeRange] = useState<TimeRange>(() => mapIntervalToTimeRange(dashboard.chart_interval));
  const [chartType, setChartType] = useState<ChartType>("line");

  // Subscribe only to the selected key — other symbols' ticks won't trigger re-render
  const historyKey = `${selectedExchange}:${selectedSymbol}`;
  const history = usePriceStore((s) => s.priceHistory[historyKey]);
  const currentPrice = usePriceStore((s) => s.prices[`${selectedExchange}:${selectedSymbol}`]);
  const currency: Currency = currentPrice?.currency ?? "KRW";

  // Filter history data for the selected time range
  const chartData = useMemo(() => {
    if (!history || history.length === 0) return [];

    const cutoff = Date.now() - TIME_RANGE_MS[timeRange];
    return history
      .filter((p) => p.timestamp_ms >= cutoff)
      .map((p) => ({
        time: Math.floor(p.timestamp_ms / 1000) as UTCTimestamp,
        value: Number(p.price),
        volume: Number(p.volume_24h) || 0,
      }))
      .sort((a, b) => a.time - b.time);
  }, [history, timeRange]);

  // Aggregate into OHLC candles when in candle mode
  const ohlcData = useMemo(() => {
    if (chartType !== "candle") return [];
    return aggregateToOhlc(chartData, CANDLE_BUCKET_MS[timeRange]);
  }, [chartData, chartType, timeRange]);

  // Initialize chart — recreate when chartType or currency changes
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#6b7280",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "#374151",
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
      crosshair: {
        horzLine: {
          color: "#4b5563",
          labelBackgroundColor: "#374151",
        },
        vertLine: {
          color: "#4b5563",
          labelBackgroundColor: "#374151",
        },
      },
    });

    chartRef.current = chart;

    const priceFormat = {
      type: "price" as const,
      precision: currency === "KRW" ? 0 : 2,
      minMove: currency === "KRW" ? 1 : 0.01,
    };

    // Add price series based on chart type
    if (chartType === "candle") {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderUpColor: "#22c55e",
        borderDownColor: "#ef4444",
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
        priceFormat,
      });
      priceSeriesRef.current = candleSeries;
    } else {
      const lineSeries = chart.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 2,
        priceFormat,
      });
      priceSeriesRef.current = lineSeries;
    }

    // Histogram series for volume
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "#3b82f626",
      priceFormat: { type: "volume" as const },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // Resize handler
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      priceSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [currency, chartType]);

  // Update chart data
  const updateChartData = useCallback(() => {
    if (!priceSeriesRef.current || !volumeSeriesRef.current) return;

    if (chartType === "candle") {
      if (ohlcData.length === 0) {
        priceSeriesRef.current.setData([]);
        volumeSeriesRef.current.setData([]);
        return;
      }

      priceSeriesRef.current.setData(
        ohlcData.map((d) => ({
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
        })),
      );
      volumeSeriesRef.current.setData(
        ohlcData.map((d) => ({
          time: d.time,
          value: d.volume,
          color: d.close >= d.open ? "#22c55e26" : "#ef444426",
        })),
      );
    } else {
      if (chartData.length === 0) {
        priceSeriesRef.current.setData([]);
        volumeSeriesRef.current.setData([]);
        return;
      }

      // Deduplicate by time
      const seen = new Set<number>();
      const deduped = chartData.filter((d) => {
        if (seen.has(d.time)) return false;
        seen.add(d.time);
        return true;
      });

      priceSeriesRef.current.setData(
        deduped.map((d) => ({ time: d.time, value: d.value })),
      );
      volumeSeriesRef.current.setData(
        deduped.map((d) => ({
          time: d.time,
          value: d.volume,
          color: "#3b82f626",
        })),
      );
    }

    chartRef.current?.timeScale().fitContent();
  }, [chartData, ohlcData, chartType]);

  useEffect(() => {
    updateChartData();
  }, [updateChartData]);

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

  // Candle bucket label for display
  const candleLabel = chartType === "candle"
    ? { "1h": "1분봉", "6h": "5분봉", "24h": "15분봉", "7d": "1시간봉" }[timeRange]
    : null;

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      {/* Controls */}
      <div className="relative z-10 mb-3 flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-medium text-gray-300">가격 차트</h3>

        {/* Chart type selector */}
        <div className="flex gap-0.5 rounded border border-gray-700 p-0.5">
          <button
            onClick={() => setChartType("line")}
            className={`rounded px-2 py-0.5 text-xs transition-colors ${
              chartType === "line"
                ? "bg-blue-600 text-white"
                : "text-gray-500 hover:text-gray-300"
            }`}
            title="선 차트"
          >
            {/* Line chart icon */}
            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polyline points="1,12 5,6 9,9 15,3" />
            </svg>
          </button>
          <button
            onClick={() => setChartType("candle")}
            className={`rounded px-2 py-0.5 text-xs transition-colors ${
              chartType === "candle"
                ? "bg-blue-600 text-white"
                : "text-gray-500 hover:text-gray-300"
            }`}
            title="캔들 차트"
          >
            {/* Candlestick icon */}
            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
              <rect x="2" y="4" width="3" height="8" rx="0.5" />
              <line x1="3.5" y1="1" x2="3.5" y2="4" stroke="currentColor" strokeWidth="1.2" />
              <line x1="3.5" y1="12" x2="3.5" y2="15" stroke="currentColor" strokeWidth="1.2" />
              <rect x="8" y="6" width="3" height="6" rx="0.5" />
              <line x1="9.5" y1="3" x2="9.5" y2="6" stroke="currentColor" strokeWidth="1.2" />
              <line x1="9.5" y1="12" x2="9.5" y2="14" stroke="currentColor" strokeWidth="1.2" />
              <rect x="13" y="2" width="2" height="9" rx="0.5" />
              <line x1="14" y1="0.5" x2="14" y2="2" stroke="currentColor" strokeWidth="1.2" />
              <line x1="14" y1="11" x2="14" y2="13.5" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          </button>
        </div>

        {/* Candle bucket info */}
        {candleLabel && (
          <span className="text-[10px] text-gray-600">{candleLabel}</span>
        )}

        {/* Exchange selector */}
        <select
          value={selectedExchange}
          onChange={(e) => setSelectedExchange(e.target.value as ExchangeId)}
          className="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-gray-300 outline-none focus:border-blue-600"
        >
          {ALL_EXCHANGES.map((ex) => (
            <option key={ex} value={ex} className="bg-gray-800 text-gray-300">
              {EXCHANGE_NAMES[ex]}
            </option>
          ))}
        </select>

        {/* Symbol selector */}
        <select
          value={selectedSymbol}
          onChange={(e) => setSelectedSymbol(e.target.value)}
          className="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-gray-300 outline-none focus:border-blue-600"
        >
          {availableSymbols.map((sym) => (
            <option key={sym} value={sym} className="bg-gray-800 text-gray-300">
              {sym}
            </option>
          ))}
        </select>

        {/* Time range selector */}
        <div className="ml-auto flex gap-1">
          {(["1h", "6h", "24h", "7d"] as TimeRange[]).map((range) => (
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

      {/* Chart container */}
      <div ref={chartContainerRef} className="relative z-0 w-full">
        {chartData.length === 0 && (
          <div className="flex h-[300px] items-center justify-center text-xs text-gray-600">
            {EXCHANGE_NAMES[selectedExchange]} / {selectedSymbol} 가격 이력이 없습니다.
            데이터가 수신되면 여기에 표시됩니다.
          </div>
        )}
      </div>

      {/* Current price display */}
      {currentPrice && (
        <div className="mt-2 flex items-center gap-2 border-t border-gray-800 pt-2 text-xs">
          <span className="text-gray-500">현재가:</span>
          <span className="font-mono tabular-nums text-gray-200">
            {currency === "KRW" ? "\u20A9" : "$"}
            {Number(currentPrice.price).toLocaleString(
              currency === "KRW" ? "ko-KR" : "en-US",
              {
                minimumFractionDigits: currency === "KRW" ? 0 : 2,
                maximumFractionDigits: currency === "KRW" ? 0 : 2,
              },
            )}
          </span>
          <span className="text-gray-600">
            거래량: {Number(currentPrice.volume_24h).toLocaleString()}
          </span>
        </div>
      )}
    </div>
  );
}
