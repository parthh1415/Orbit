import { useEffect, useRef, useCallback } from "react";
import type React from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  ColorType,
  type CandlestickSeriesOptions,
  type DeepPartial,
  type UTCTimestamp,
} from "lightweight-charts";
import { useOrbitStore, TICKERS } from "../../store";
import { fetchChart, fetchEvents } from "../../api";

// ---------------------------------------------------------------------------
// Candlestick styling
// ---------------------------------------------------------------------------

const CANDLE_OPTIONS: DeepPartial<CandlestickSeriesOptions> = {
  upColor: "#5eead4",
  downColor: "#f87171",
  borderUpColor: "#5eead4",
  borderDownColor: "#f87171",
  wickUpColor: "#5eead4",
  wickDownColor: "#f87171",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Chart(): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const selectedTicker = useOrbitStore((s) => s.selectedTicker);
  const setTicker = useOrbitStore((s) => s.setTicker);
  const setChartData = useOrbitStore((s) => s.setChartData);
  const setEvents = useOrbitStore((s) => s.setEvents);

  // Initialize chart
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#000000" },
        textColor: "#666666",
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#0a0a0a" },
        horzLines: { color: "#0a0a0a" },
      },
      crosshair: {
        vertLine: { color: "#333333", labelBackgroundColor: "#1f1f1f" },
        horzLine: { color: "#333333", labelBackgroundColor: "#1f1f1f" },
      },
      timeScale: {
        borderColor: "#1f1f1f",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#1f1f1f",
      },
    });

    const series = chart.addCandlestickSeries(CANDLE_OPTIONS);

    chartRef.current = chart;
    seriesRef.current = series;

    // Resize observer
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width, height });
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Load data when ticker changes
  const loadData = useCallback(
    (ticker: string) => {
      fetchChart(ticker)
        .then((bars) => {
          setChartData(bars);

          const mapped = bars.map((b) => ({
            time: (new Date(b.timestamp).getTime() / 1000) as UTCTimestamp,
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
          }));

          if (seriesRef.current) {
            seriesRef.current.setData(mapped);
            chartRef.current?.timeScale().fitContent();
          }
        })
        .catch(() => {
          /* silent */
        });

      fetchEvents(ticker)
        .then((evts) => {
          setEvents(evts);

          if (seriesRef.current) {
            const markers = evts
              .filter((e) => e.relevance > 0.3)
              .map((e) => ({
                time: (new Date(e.timestamp).getTime() / 1000) as UTCTimestamp,
                position: "aboveBar" as const,
                color:
                  e.relevance > 0.7
                    ? "#f87171"
                    : e.relevance > 0.5
                      ? "#facc15"
                      : "#5eead4",
                shape: "arrowDown" as const,
                text: e.description.slice(0, 20),
              }));

            markers.sort((a, b) => (a.time as number) - (b.time as number));
            seriesRef.current.setMarkers(markers);
          }
        })
        .catch(() => {
          /* silent */
        });
    },
    [setChartData, setEvents],
  );

  useEffect(() => {
    loadData(selectedTicker);
  }, [selectedTicker, loadData]);

  return (
    <div style={styles.wrapper}>
      {/* Ticker tabs */}
      <div style={styles.tabs}>
        {TICKERS.map((t) => (
          <button
            key={t}
            type="button"
            style={{
              ...styles.tab,
              ...(t === selectedTicker ? styles.tabActive : {}),
            }}
            onClick={() => {
              setTicker(t);
            }}
          >
            {t}
          </button>
        ))}
        <span style={styles.tabPlaceholder}>&mdash;</span>
        <span style={styles.tabPlaceholder}>&mdash;</span>
      </div>

      {/* Chart container */}
      <div ref={containerRef} style={styles.chartContainer} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    width: "100%",
    overflow: "hidden",
  },
  tabs: {
    display: "flex",
    alignItems: "center",
    gap: "2px",
    padding: "4px 8px",
    borderBottom: "1px solid var(--border)",
    height: "28px",
    flexShrink: 0,
  },
  tab: {
    fontFamily: "var(--font-mono)",
    fontSize: "10px",
    letterSpacing: "0.08em",
    color: "var(--fg-dim)",
    background: "transparent",
    border: "1px solid var(--border)",
    padding: "2px 10px",
    cursor: "pointer",
    textTransform: "uppercase" as const,
  },
  tabActive: {
    color: "var(--accent-teal)",
    borderColor: "var(--accent-teal)",
  },
  tabPlaceholder: {
    fontSize: "10px",
    color: "var(--fg-dim)",
    padding: "2px 10px",
    opacity: 0.3,
  },
  chartContainer: {
    flex: 1,
    width: "100%",
    minHeight: 0,
  },
};
