import { useEffect, useState, useCallback } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { fetchPositions } from "../../api";

// ---------------------------------------------------------------------------
// Clock hook
// ---------------------------------------------------------------------------

function useClock(): string {
  const [time, setTime] = useState(() => formatTime(new Date()));

  useEffect(() => {
    const id = setInterval(() => {
      setTime(formatTime(new Date()));
    }, 1000);
    return () => {
      clearInterval(id);
    };
  }, []);

  return time;
}

function formatTime(d: Date): string {
  return d.toTimeString().slice(0, 8);
}

function formatDate(d: Date): string {
  const months = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
  ];
  const m = months[d.getMonth()];
  return `${m ?? "---"} ${String(d.getDate()).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Session uptime
// ---------------------------------------------------------------------------

const SESSION_START = Date.now();

function useUptime(): string {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setTick((t) => t + 1);
    }, 1000);
    return () => {
      clearInterval(id);
    };
  }, []);

  const elapsed = Math.floor((Date.now() - SESSION_START) / 1000);
  const days = Math.floor(elapsed / 86400);
  const hrs = Math.floor((elapsed % 86400) / 3600);
  const mins = Math.floor((elapsed % 3600) / 60);
  const secs = elapsed % 60;
  return `${String(days)}d${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function LeftPanel(): React.ReactElement {
  const clock = useClock();
  const uptime = useUptime();
  const positions = useOrbitStore((s) => s.positions);
  const recentTrades = useOrbitStore((s) => s.recentTrades);
  const setPositions = useOrbitStore((s) => s.setPositions);

  const loadPositions = useCallback(() => {
    fetchPositions()
      .then((p) => {
        setPositions(p);
      })
      .catch(() => {
        /* silent */
      });
  }, [setPositions]);

  useEffect(() => {
    loadPositions();
    const id = setInterval(loadPositions, 5000);
    return () => {
      clearInterval(id);
    };
  }, [loadPositions]);

  const totalPnl = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
  const capitalDeployed = positions.reduce(
    (sum, p) => sum + p.entry_price * p.size_shares,
    0,
  );

  return (
    <div className="LeftPanel" style={styles.container}>
      {/* Header */}
      <div className="panel-header">BOOK &middot; DESK</div>

      {/* Clock */}
      <div style={styles.clockSection}>
        <span style={styles.clock}>{clock}</span>
      </div>

      {/* Session info */}
      <div style={styles.sessionSection}>
        <div style={styles.sessionLine}>
          SESSION &middot; {formatDate(new Date())} &middot; LIVE {uptime}{" "}
          &middot; MODE PAPER &middot; FEED LIVE
        </div>
        <div style={styles.sessionLine}>
          ACCOUNT MAIN &middot; BROKER ALPACA &middot; VENUE SIM
        </div>
      </div>

      {/* Positions */}
      <div className="panel-section">
        <div className="label" style={styles.sectionLabel}>
          POSITIONS
        </div>
        {positions.length === 0 ? (
          <div style={styles.empty}>NO OPEN POSITIONS</div>
        ) : (
          <div style={styles.positionList}>
            {positions.map((p) => (
              <div key={p.ticker} style={styles.posRow}>
                <span style={styles.posTicker}>{p.ticker}</span>
                <span style={styles.posDir}>
                  {p.direction.toUpperCase()} {p.size_shares}
                </span>
                <span
                  style={{
                    ...styles.posPnl,
                    color:
                      p.unrealized_pnl >= 0
                        ? "var(--accent-teal)"
                        : "var(--accent-coral)",
                  }}
                >
                  {p.unrealized_pnl >= 0 ? "+" : ""}
                  {p.unrealized_pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Capital / PnL */}
      <div className="panel-section">
        <div style={styles.metricRow}>
          <span className="label">TOTAL P&amp;L</span>
          <span
            style={{
              color:
                totalPnl >= 0 ? "var(--accent-teal)" : "var(--accent-coral)",
            }}
          >
            {totalPnl >= 0 ? "+" : ""}
            {totalPnl.toFixed(2)}
          </span>
        </div>
        <div style={styles.metricRow}>
          <span className="label">CAPITAL DEPLOYED</span>
          <span className="value">${capitalDeployed.toFixed(0)}</span>
        </div>

        {/* Capital bar */}
        <div style={styles.capitalBar}>
          <div
            style={{
              ...styles.capitalFill,
              width: `${String(Math.min((capitalDeployed / 100000) * 100, 100))}%`,
            }}
          />
        </div>

        <div style={styles.metricRow}>
          <span className="label">MARGIN</span>
          <span className="value">PAPER &middot; UNLIMITED</span>
        </div>
      </div>

      {/* Recent Trades */}
      <div className="panel-section" style={styles.tradesSection}>
        <div className="label" style={styles.sectionLabel}>
          RECENT TRADES
        </div>
        {recentTrades.length === 0 ? (
          <div style={styles.empty}>NO TRADES</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>SYM</th>
                <th>P&amp;L</th>
                <th>SIZE</th>
              </tr>
            </thead>
            <tbody>
              {recentTrades.slice(0, 5).map((t) => (
                <tr key={t.id}>
                  <td style={styles.tradeId}>{t.id.slice(0, 6)}</td>
                  <td>{t.ticker}</td>
                  <td
                    style={{
                      color:
                        (t.realized_pnl ?? 0) >= 0
                          ? "var(--accent-teal)"
                          : "var(--accent-coral)",
                    }}
                  >
                    {t.realized_pnl != null
                      ? t.realized_pnl.toFixed(2)
                      : "\u2014"}
                  </td>
                  <td>{t.size_shares}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline styles (monospace aesthetic)
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
  },
  clockSection: {
    padding: "12px",
    textAlign: "center",
    borderBottom: "1px solid var(--border)",
  },
  clock: {
    fontSize: "24px",
    fontWeight: 300,
    color: "var(--fg-bright)",
    letterSpacing: "0.15em",
  },
  sessionSection: {
    padding: "8px 12px",
    borderBottom: "1px solid var(--border)",
  },
  sessionLine: {
    fontSize: "9px",
    letterSpacing: "0.08em",
    color: "var(--fg-dim)",
    lineHeight: 1.8,
  },
  sectionLabel: {
    marginBottom: "6px",
  },
  empty: {
    fontSize: "9px",
    color: "var(--fg-dim)",
    letterSpacing: "0.1em",
    padding: "4px 0",
  },
  positionList: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  posRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "10px",
    padding: "2px 0",
  },
  posTicker: {
    color: "var(--fg-bright)",
    fontWeight: 500,
    width: "40px",
  },
  posDir: {
    color: "var(--fg-dim)",
    flex: 1,
    textAlign: "center",
  },
  posPnl: {
    fontWeight: 500,
    textAlign: "right",
    width: "80px",
  },
  metricRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "2px 0",
    fontSize: "10px",
  },
  capitalBar: {
    width: "100%",
    height: "4px",
    background: "var(--border)",
    borderRadius: "2px",
    margin: "4px 0",
    overflow: "hidden",
  },
  capitalFill: {
    height: "100%",
    background: "var(--accent-teal)",
    borderRadius: "2px",
    transition: "width 0.3s",
  },
  tradesSection: {
    flex: 1,
    overflow: "auto",
  },
  tradeId: {
    color: "var(--fg-dim)",
    fontFamily: "var(--font-mono)",
    fontSize: "9px",
  },
};
