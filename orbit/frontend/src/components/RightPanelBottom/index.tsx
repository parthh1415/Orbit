import { useEffect, useCallback, useMemo } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { fetchRecentEvents } from "../../api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "JUST NOW";
  if (mins < 60) return `${String(mins)}M AGO`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${String(hrs)}H AGO`;
  const days = Math.floor(hrs / 24);
  return `${String(days)}D AGO`;
}

function verdictTag(direction: string, relevance: number): string {
  if (relevance < 0.2) return "IGNORE";
  if (relevance < 0.5) return "WAIT";
  return direction === "long" || direction === "short" ? "ACT" : "WAIT";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RightPanelBottom(): React.ReactElement {
  const events = useOrbitStore((s) => s.events);
  const setEvents = useOrbitStore((s) => s.setEvents);
  const selectedEventId = useOrbitStore((s) => s.selectedEventId);
  const setSelectedEventId = useOrbitStore((s) => s.setSelectedEventId);

  const loadEvents = useCallback(() => {
    fetchRecentEvents()
      .then((evts) => {
        setEvents(evts);
      })
      .catch(() => {
        /* silent */
      });
  }, [setEvents]);

  useEffect(() => {
    loadEvents();
    const id = setInterval(loadEvents, 10000);
    return () => {
      clearInterval(id);
    };
  }, [loadEvents]);

  // Count verdicts
  const counts = useMemo(() => {
    let act = 0;
    let wait = 0;
    let ignore = 0;
    for (const e of events) {
      const tag = verdictTag(e.implied_direction, e.relevance);
      if (tag === "ACT") act++;
      else if (tag === "WAIT") wait++;
      else ignore++;
    }
    return { act, wait, ignore, total: events.length };
  }, [events]);

  // Top 4 high-score events
  const topEvents = useMemo(
    () => [...events].sort((a, b) => b.relevance - a.relevance).slice(0, 4),
    [events],
  );

  return (
    <div style={styles.container}>
      {/* Header */}
      <div className="panel-header">EVENT FEED</div>

      {/* Counts */}
      <div style={styles.counts}>
        <span>
          <span style={{ color: "var(--accent-teal)" }}>ACT {counts.act}</span>{" "}
          <span style={{ color: "var(--accent-yellow)" }}>
            WAIT {counts.wait}
          </span>
        </span>
        <span style={styles.countSecondary}>
          IGNORE {counts.ignore} &middot; {counts.total} TOTAL THIS SESSION
        </span>
      </div>

      {/* Event Cards */}
      <div style={styles.cardList}>
        {topEvents.map((e) => {
          const tag = verdictTag(e.implied_direction, e.relevance);
          const tagColor =
            tag === "ACT"
              ? e.implied_direction === "short"
                ? "var(--accent-coral)"
                : "var(--accent-teal)"
              : tag === "WAIT"
                ? "var(--accent-yellow)"
                : "var(--fg-dim)";
          const isSelected = selectedEventId === e.id;

          return (
            <div
              key={e.id}
              style={{
                ...styles.card,
                borderLeftColor: tagColor,
                background: isSelected
                  ? "rgba(255,255,255,0.03)"
                  : "transparent",
              }}
              onClick={() => {
                setSelectedEventId(isSelected ? null : e.id);
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(ev) => {
                if (ev.key === "Enter" || ev.key === " ") {
                  setSelectedEventId(isSelected ? null : e.id);
                }
              }}
            >
              <div style={styles.cardHeader}>
                <span style={{ color: tagColor }}>
                  [{e.implied_direction === "short" ? "\u25BC" : "\u25B2"}]
                </span>
                <span style={styles.cardDesc}>
                  {e.description.slice(0, 60)}
                </span>
                <span style={styles.cardScore}>{e.relevance.toFixed(2)}</span>
              </div>
              <div style={styles.cardMeta}>
                {e.countries.slice(0, 2).map((c) => (
                  <span key={c} style={styles.countryTag}>
                    {c}
                  </span>
                ))}
                <span style={styles.cardTime}>{timeAgo(e.timestamp)}</span>
              </div>

              {/* Expanded detail */}
              {isSelected && (
                <div style={styles.cardDetail}>
                  <div>
                    SOURCE: {e.source} &middot; CAMEO: {e.cameo_code}
                  </div>
                  <div>
                    GOLDSTEIN: {e.goldstein_score.toFixed(1)} &middot;
                    SENTIMENT: {e.sentiment.toFixed(2)}
                  </div>
                  <div>
                    LAT: {e.lat.toFixed(2)} LON: {e.lon.toFixed(2)} &middot;
                    SOURCES: {e.num_sources}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {topEvents.length === 0 && <div style={styles.empty}>NO EVENTS</div>}
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
    height: "100%",
    overflow: "hidden",
  },
  counts: {
    padding: "6px 12px",
    borderBottom: "1px solid var(--border)",
    fontSize: "10px",
    letterSpacing: "0.08em",
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  countSecondary: {
    color: "var(--fg-dim)",
    fontSize: "9px",
  },
  cardList: {
    flex: 1,
    overflow: "auto",
    padding: "4px 0",
  },
  card: {
    padding: "6px 12px",
    borderLeft: "2px solid var(--border)",
    borderBottom: "1px solid var(--border)",
    cursor: "pointer",
    transition: "background 0.15s",
  },
  cardHeader: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "10px",
  },
  cardDesc: {
    flex: 1,
    color: "var(--fg-primary)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  cardScore: {
    color: "var(--fg-bright)",
    fontWeight: 500,
    flexShrink: 0,
  },
  cardMeta: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    marginTop: "2px",
    fontSize: "9px",
  },
  countryTag: {
    color: "var(--fg-dim)",
    border: "1px solid var(--border)",
    padding: "0 4px",
    fontSize: "8px",
    letterSpacing: "0.06em",
  },
  cardTime: {
    color: "var(--fg-dim)",
    marginLeft: "auto",
    fontSize: "8px",
  },
  cardDetail: {
    marginTop: "4px",
    padding: "4px 0",
    fontSize: "9px",
    color: "var(--fg-dim)",
    lineHeight: 1.6,
    borderTop: "1px solid var(--border)",
  },
  empty: {
    padding: "12px",
    color: "var(--fg-dim)",
    fontSize: "9px",
    letterSpacing: "0.1em",
    textAlign: "center",
  },
};
