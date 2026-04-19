import { useEffect, useCallback } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { fetchVerdict } from "../../api";

interface VerdictStripProps {
  onExecute: () => void;
}

// ---------------------------------------------------------------------------
// Verdict classification helpers
// ---------------------------------------------------------------------------

function getVerdictColor(verdictClass: string): string {
  if (verdictClass === "strong_buy" || verdictClass === "buy") {
    return "var(--accent-teal)";
  }
  if (verdictClass === "strong_sell" || verdictClass === "sell") {
    return "var(--accent-coral)";
  }
  if (verdictClass === "hold") {
    return "var(--accent-yellow)";
  }
  return "var(--fg-dim)";
}

function getVerdictLabel(verdictClass: string, direction: string): string {
  const isAct =
    verdictClass === "strong_buy" ||
    verdictClass === "buy" ||
    verdictClass === "strong_sell" ||
    verdictClass === "sell";
  const arrow =
    direction === "long"
      ? "\u25B2"
      : direction === "short"
        ? "\u25BC"
        : "\u25CF";

  if (isAct) return `ACT ${arrow}`;
  if (verdictClass === "hold") return "WAIT";
  return "IGNORE";
}

function isActVerdict(verdictClass: string): boolean {
  return (
    verdictClass === "strong_buy" ||
    verdictClass === "buy" ||
    verdictClass === "strong_sell" ||
    verdictClass === "sell"
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function VerdictStrip({
  onExecute,
}: VerdictStripProps): React.ReactElement {
  const selectedTicker = useOrbitStore((s) => s.selectedTicker);
  const verdict = useOrbitStore((s) => s.currentVerdict);
  const setVerdict = useOrbitStore((s) => s.setVerdict);

  const loadVerdict = useCallback(
    (ticker: string) => {
      fetchVerdict(ticker)
        .then((v) => {
          setVerdict(v);
        })
        .catch(() => {
          setVerdict(null);
        });
    },
    [setVerdict],
  );

  useEffect(() => {
    loadVerdict(selectedTicker);
    const id = setInterval(() => {
      loadVerdict(selectedTicker);
    }, 5000);
    return () => {
      clearInterval(id);
    };
  }, [selectedTicker, loadVerdict]);

  if (!verdict) {
    return (
      <div style={styles.strip}>
        <span style={{ color: "var(--fg-dim)" }}>
          AWAITING VERDICT &middot; {selectedTicker}
        </span>
      </div>
    );
  }

  const color = getVerdictColor(verdict.verdict_class);
  const label = getVerdictLabel(verdict.verdict_class, verdict.direction);
  const canExecute = isActVerdict(verdict.verdict_class);

  return (
    <div style={{ ...styles.strip, borderLeft: `3px solid ${color}` }}>
      <span style={{ color, fontWeight: 500 }}>
        [{label} {verdict.ticker}]
      </span>
      <span style={styles.description}>
        SCORE {verdict.relevance_score.toFixed(2)} &middot;{" "}
        {verdict.verdict_class.toUpperCase().replace("_", " ")}
      </span>
      <span style={styles.spacer} />
      <button
        type="button"
        style={{
          ...styles.execBtn,
          borderColor: canExecute ? color : "var(--border)",
          color: canExecute ? color : "var(--fg-dim)",
          opacity: canExecute ? 1 : 0.3,
        }}
        disabled={!canExecute}
        onClick={onExecute}
      >
        EXECUTE
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  strip: {
    display: "flex",
    alignItems: "center",
    height: "100%",
    padding: "0 12px",
    gap: "12px",
    fontSize: "11px",
    letterSpacing: "0.06em",
    fontFamily: "var(--font-mono)",
    overflow: "hidden",
  },
  description: {
    color: "var(--fg-primary)",
    fontSize: "10px",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  spacer: {
    flex: 1,
  },
  execBtn: {
    fontFamily: "var(--font-mono)",
    fontSize: "9px",
    letterSpacing: "0.1em",
    background: "transparent",
    border: "1px solid var(--border)",
    padding: "3px 10px",
    cursor: "pointer",
    flexShrink: 0,
  },
};
