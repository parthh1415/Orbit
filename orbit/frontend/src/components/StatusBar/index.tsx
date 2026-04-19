import { useEffect, useCallback } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { fetchStatus } from "../../api";

export default function StatusBar(): React.ReactElement {
  const status = useOrbitStore((s) => s.systemStatus);
  const setStatus = useOrbitStore((s) => s.setSystemStatus);

  const load = useCallback(() => {
    fetchStatus()
      .then((s) => {
        setStatus(s);
      })
      .catch(() => {
        /* silent */
      });
  }, [setStatus]);

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => {
      clearInterval(id);
    };
  }, [load]);

  const levelColor =
    status?.level === "error"
      ? "var(--accent-coral)"
      : status?.level === "warning"
        ? "var(--accent-yellow)"
        : "var(--accent-teal)";

  return (
    <div style={styles.bar}>
      <span style={styles.brand}>ORBIT v0.1.0</span>
      <span style={styles.divider}>|</span>
      {status ? (
        <>
          <span style={{ ...styles.level, color: levelColor }}>
            {status.level.toUpperCase()}
          </span>
          <span style={styles.message}>{status.message}</span>
          <span style={styles.timestamp}>{status.timestamp}</span>
        </>
      ) : (
        <span style={styles.message}>CONNECTING...</span>
      )}
      <span style={styles.spacer} />
      <span style={styles.timestamp}>{new Date().toISOString()}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  bar: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    height: "100%",
    fontSize: "9px",
    letterSpacing: "0.08em",
    fontFamily: "var(--font-mono)",
    color: "var(--fg-dim)",
    padding: "0 12px",
    overflow: "hidden",
  },
  brand: {
    color: "var(--fg-dim)",
    fontWeight: 500,
  },
  divider: {
    color: "var(--border)",
  },
  level: {
    fontWeight: 500,
  },
  message: {
    color: "var(--fg-primary)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  spacer: {
    flex: 1,
  },
  timestamp: {
    color: "var(--fg-dim)",
    flexShrink: 0,
  },
};
