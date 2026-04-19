import { useEffect, useCallback } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { fetchScorecardBacktest, fetchScorecardLive } from "../../api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function fmtNum(n: number): string {
  return n.toFixed(2);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ScorecardStrip(): React.ReactElement {
  const backtestRows = useOrbitStore((s) => s.scorecardBacktest);
  const liveRows = useOrbitStore((s) => s.scorecardLive);
  const positions = useOrbitStore((s) => s.positions);
  const recentTrades = useOrbitStore((s) => s.recentTrades);
  const setScorecardBacktest = useOrbitStore((s) => s.setScorecardBacktest);
  const setScorecardLive = useOrbitStore((s) => s.setScorecardLive);

  // Load backtest once
  useEffect(() => {
    fetchScorecardBacktest()
      .then((rows) => {
        setScorecardBacktest(rows);
      })
      .catch(() => {
        /* silent */
      });
  }, [setScorecardBacktest]);

  // Poll live scorecard
  const loadLive = useCallback(() => {
    fetchScorecardLive()
      .then((rows) => {
        setScorecardLive(rows);
      })
      .catch(() => {
        /* silent */
      });
  }, [setScorecardLive]);

  useEffect(() => {
    loadLive();
    const id = setInterval(loadLive, 5000);
    return () => {
      clearInterval(id);
    };
  }, [loadLive]);

  // Session stats computed from store
  const sessionTrades = recentTrades.length;
  const sessionPnl = positions.reduce((s, p) => s + p.unrealized_pnl, 0);

  // Aggregate a row array into a single summary line
  const summarize = (
    label: string,
    rows: Array<{
      total_trades: number;
      wins: number;
      win_rate: number;
      avg_return: number;
      sharpe: number;
    }>,
  ): React.ReactElement => {
    const trades = rows.reduce((s, r) => s + r.total_trades, 0);
    const wins = rows.reduce((s, r) => s + r.wins, 0);
    const wr = trades > 0 ? wins / trades : 0;
    const avgRet =
      rows.length > 0
        ? rows.reduce((s, r) => s + r.avg_return, 0) / rows.length
        : 0;
    const sharpe =
      rows.length > 0
        ? rows.reduce((s, r) => s + r.sharpe, 0) / rows.length
        : 0;

    return (
      <div style={styles.row}>
        <span style={styles.label}>{label}</span>
        <span style={styles.metric}>TRADES {trades}</span>
        <span style={styles.metric}>WINS {wins}</span>
        <span style={styles.metric}>WR {fmtPct(wr)}</span>
        <span style={styles.metric}>AVG {fmtPct(avgRet)}</span>
        <span style={styles.metric}>SHARPE {fmtNum(sharpe)}</span>
      </div>
    );
  };

  return (
    <div style={styles.container}>
      {summarize("BACKTEST", backtestRows)}
      {summarize("LIVE", liveRows)}
      <div style={styles.row}>
        <span style={styles.label}>SESSION</span>
        <span style={styles.metric}>TRADES {sessionTrades}</span>
        <span style={styles.metric}>OPEN {positions.length}</span>
        <span
          style={{
            ...styles.metric,
            color:
              sessionPnl >= 0 ? "var(--accent-teal)" : "var(--accent-coral)",
          }}
        >
          P&amp;L {sessionPnl >= 0 ? "+" : ""}
          {sessionPnl.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    height: "100%",
    padding: "4px 12px",
    gap: "2px",
    overflow: "hidden",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
    fontSize: "9px",
    letterSpacing: "0.08em",
    fontFamily: "var(--font-mono)",
  },
  label: {
    color: "var(--fg-dim)",
    width: "70px",
    flexShrink: 0,
    fontWeight: 500,
  },
  metric: {
    color: "var(--fg-primary)",
    whiteSpace: "nowrap",
  },
};
