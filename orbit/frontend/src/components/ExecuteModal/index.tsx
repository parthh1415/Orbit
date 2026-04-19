import { useState, useMemo } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { executeTradeAPI } from "../../api";
import type { DirectionEnum } from "../../types";

interface ExecuteModalProps {
  onClose: () => void;
}

export default function ExecuteModal({
  onClose,
}: ExecuteModalProps): React.ReactElement {
  const verdict = useOrbitStore((s) => s.currentVerdict);
  const [size, setSize] = useState(100);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const ticker = verdict?.ticker ?? "AAPL";
  const direction: DirectionEnum = verdict?.direction ?? "flat";

  // Estimate fill price (from chart data last bar)
  const chartData = useOrbitStore((s) => s.chartData);
  const lastPrice = useMemo(() => {
    const last = chartData[chartData.length - 1];
    return last ? last.close : 0;
  }, [chartData]);

  const slippageBps = 2;
  const slippage = lastPrice * (slippageBps / 10000);
  const estFill =
    direction === "long"
      ? lastPrice + slippage
      : direction === "short"
        ? lastPrice - slippage
        : lastPrice;

  const handleConfirm = (): void => {
    setSubmitting(true);
    setResult(null);

    executeTradeAPI({
      ticker,
      direction,
      size_shares: size,
    })
      .then((res) => {
        setResult(res.message);
        setTimeout(onClose, 2000);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "UNKNOWN ERROR";
        setResult(`ERROR: ${msg}`);
      })
      .finally(() => {
        setSubmitting(false);
      });
  };

  return (
    <div style={styles.overlay} onClick={onClose} role="presentation">
      <div
        style={styles.modal}
        onClick={(e) => {
          e.stopPropagation();
        }}
        role="dialog"
        aria-label="Execute Trade"
      >
        {/* Header */}
        <div style={styles.header}>EXECUTE TRADE</div>

        {/* Fields */}
        <div style={styles.fields}>
          <div style={styles.fieldRow}>
            <span style={styles.fieldLabel}>DIRECTION</span>
            <span
              style={{
                ...styles.fieldValue,
                color:
                  direction === "long"
                    ? "var(--accent-teal)"
                    : direction === "short"
                      ? "var(--accent-coral)"
                      : "var(--fg-dim)",
              }}
            >
              {direction.toUpperCase()}
            </span>
          </div>
          <div style={styles.fieldRow}>
            <span style={styles.fieldLabel}>TICKER</span>
            <span style={styles.fieldValue}>{ticker}</span>
          </div>
          <div style={styles.fieldRow}>
            <span style={styles.fieldLabel}>SIZE</span>
            <input
              type="number"
              value={size}
              onChange={(e) => {
                setSize(Math.max(1, Number(e.target.value)));
              }}
              style={styles.sizeInput}
              min={1}
            />
          </div>
          <div style={styles.fieldRow}>
            <span style={styles.fieldLabel}>PRICE</span>
            <span style={styles.fieldValue}>${lastPrice.toFixed(2)}</span>
          </div>
          <div style={styles.fieldRow}>
            <span style={styles.fieldLabel}>SLIPPAGE</span>
            <span style={styles.fieldValue}>{slippageBps} BPS</span>
          </div>
          <div style={styles.fieldRow}>
            <span style={styles.fieldLabel}>EST FILL</span>
            <span style={{ ...styles.fieldValue, color: "var(--fg-bright)" }}>
              ${estFill.toFixed(2)}
            </span>
          </div>
        </div>

        {/* Result message */}
        {result && (
          <div
            style={{
              ...styles.result,
              color: result.startsWith("ERROR")
                ? "var(--accent-coral)"
                : "var(--accent-teal)",
            }}
          >
            {result}
          </div>
        )}

        {/* Actions */}
        <div style={styles.actions}>
          <button
            type="button"
            style={styles.cancelBtn}
            onClick={onClose}
            disabled={submitting}
          >
            CANCEL
          </button>
          <button
            type="button"
            style={styles.confirmBtn}
            onClick={handleConfirm}
            disabled={submitting || direction === "flat"}
          >
            {submitting ? "..." : "CONFIRM"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    background: "rgba(0, 0, 0, 0.85)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
  },
  modal: {
    width: "400px",
    maxHeight: "300px",
    background: "#000000",
    border: "1px solid var(--border)",
    padding: "16px",
    fontFamily: "var(--font-mono)",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  header: {
    fontSize: "11px",
    fontWeight: 500,
    letterSpacing: "0.12em",
    color: "var(--fg-bright)",
    borderBottom: "1px solid var(--border)",
    paddingBottom: "8px",
  },
  fields: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
  },
  fieldRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSize: "10px",
  },
  fieldLabel: {
    color: "var(--fg-dim)",
    letterSpacing: "0.08em",
  },
  fieldValue: {
    color: "var(--fg-primary)",
    fontWeight: 500,
  },
  sizeInput: {
    width: "80px",
    fontFamily: "var(--font-mono)",
    fontSize: "10px",
    background: "transparent",
    border: "1px solid var(--border)",
    color: "var(--fg-bright)",
    padding: "2px 6px",
    textAlign: "right" as const,
    outline: "none",
  },
  result: {
    fontSize: "9px",
    letterSpacing: "0.06em",
    padding: "4px 0",
  },
  actions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: "8px",
    paddingTop: "8px",
    borderTop: "1px solid var(--border)",
  },
  cancelBtn: {
    fontFamily: "var(--font-mono)",
    fontSize: "9px",
    letterSpacing: "0.1em",
    background: "transparent",
    border: "1px solid var(--border)",
    color: "var(--fg-dim)",
    padding: "4px 12px",
    cursor: "pointer",
  },
  confirmBtn: {
    fontFamily: "var(--font-mono)",
    fontSize: "9px",
    letterSpacing: "0.1em",
    background: "transparent",
    border: "1px solid var(--accent-teal)",
    color: "var(--accent-teal)",
    padding: "4px 12px",
    cursor: "pointer",
  },
};
