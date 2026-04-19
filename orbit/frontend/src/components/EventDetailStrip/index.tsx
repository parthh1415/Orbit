import { useMemo } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";

export default function EventDetailStrip(): React.ReactElement {
  const events = useOrbitStore((s) => s.events);
  const selectedEventId = useOrbitStore((s) => s.selectedEventId);
  const setSelectedEventId = useOrbitStore((s) => s.setSelectedEventId);

  const event = useMemo(
    () => events.find((e) => e.id === selectedEventId) ?? null,
    [events, selectedEventId],
  );

  if (!event) {
    return <div className="EventDetailStrip" />;
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.title}>EVENT DETAIL</span>
        <button
          type="button"
          style={styles.closeBtn}
          onClick={() => {
            setSelectedEventId(null);
          }}
        >
          [X]
        </button>
      </div>
      <div style={styles.body}>
        <div style={styles.row}>
          <span style={styles.label}>ID</span>
          <span style={styles.value}>{event.id}</span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>SOURCE</span>
          <span style={styles.value}>{event.source}</span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>TIMESTAMP</span>
          <span style={styles.value}>{event.timestamp}</span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>DESCRIPTION</span>
          <span style={styles.value}>{event.description}</span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>CAMEO</span>
          <span style={styles.value}>{event.cameo_code || "\u2014"}</span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>GOLDSTEIN</span>
          <span style={styles.value}>{event.goldstein_score.toFixed(1)}</span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>SENTIMENT</span>
          <span
            style={{
              ...styles.value,
              color:
                event.sentiment >= 0
                  ? "var(--accent-teal)"
                  : "var(--accent-coral)",
            }}
          >
            {event.sentiment.toFixed(3)}
          </span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>RELEVANCE</span>
          <span style={{ ...styles.value, color: "var(--fg-bright)" }}>
            {event.relevance.toFixed(3)}
          </span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>DIRECTION</span>
          <span
            style={{
              ...styles.value,
              color:
                event.implied_direction === "long"
                  ? "var(--accent-teal)"
                  : event.implied_direction === "short"
                    ? "var(--accent-coral)"
                    : "var(--fg-dim)",
            }}
          >
            {event.implied_direction.toUpperCase()}
          </span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>LOCATION</span>
          <span style={styles.value}>
            {event.lat.toFixed(2)}, {event.lon.toFixed(2)}
          </span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>COUNTRIES</span>
          <span style={styles.value}>
            {event.countries.join(", ") || "\u2014"}
          </span>
        </div>
        <div style={styles.row}>
          <span style={styles.label}>SOURCES</span>
          <span style={styles.value}>{event.num_sources}</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: "var(--bg)",
    border: "1px solid var(--border)",
    fontFamily: "var(--font-mono)",
    fontSize: "10px",
    maxHeight: "200px",
    overflow: "auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 12px",
    borderBottom: "1px solid var(--border)",
  },
  title: {
    fontSize: "10px",
    fontWeight: 500,
    letterSpacing: "0.1em",
    color: "var(--fg-dim)",
  },
  closeBtn: {
    fontFamily: "var(--font-mono)",
    fontSize: "9px",
    background: "transparent",
    border: "none",
    color: "var(--fg-dim)",
    cursor: "pointer",
  },
  body: {
    padding: "6px 12px",
    display: "flex",
    flexDirection: "column",
    gap: "3px",
  },
  row: {
    display: "flex",
    gap: "8px",
  },
  label: {
    width: "90px",
    flexShrink: 0,
    color: "var(--fg-dim)",
    letterSpacing: "0.06em",
    fontSize: "9px",
  },
  value: {
    color: "var(--fg-primary)",
    wordBreak: "break-word" as const,
  },
};
