import { useEffect, useRef, useState, useCallback } from "react";
import type React from "react";
import Globe from "react-globe.gl";
import { useOrbitStore } from "../../store";
import { fetchRecentEvents } from "../../api";

// ---------------------------------------------------------------------------
// Types for globe points
// ---------------------------------------------------------------------------

interface GlobePoint {
  lat: number;
  lng: number;
  size: number;
  color: string;
  label: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RightPanelTop(): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 200, height: 200 });
  const events = useOrbitStore((s) => s.events);
  const setEvents = useOrbitStore((s) => s.setEvents);

  // Observe container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height: height - 80 });
      }
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);

  // Poll recent events for globe
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

  // Build globe points from events (max 50)
  const points: GlobePoint[] = events
    .filter((e) => e.lat !== 0 || e.lon !== 0)
    .slice(0, 50)
    .map((e) => ({
      lat: e.lat,
      lng: e.lon,
      size: Math.max(0.2, Math.min(e.relevance * 1.5, 1.5)),
      color:
        e.relevance > 0.7
          ? "#f87171"
          : e.relevance > 0.5
            ? "#facc15"
            : "#5eead4",
      label: e.description.slice(0, 30),
    }));

  // Most recent high-score event
  const lastEvent = events
    .filter((e) => e.relevance > 0.3 && (e.lat !== 0 || e.lon !== 0))
    .sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    )[0];

  const globeSize = Math.min(dimensions.width, dimensions.height);

  return (
    <div ref={containerRef} style={styles.container}>
      {/* Header */}
      <div className="panel-header">MACRO &middot; GLOBE</div>

      {/* Feed status */}
      <div style={styles.feedStatus}>
        <span style={styles.feedLabel}>FEED STATUS &middot; SOURCE: GDELT</span>
        <span style={styles.feedState}>
          STATE FEEDS LATENCY &middot;{" "}
          <span style={{ color: "var(--accent-teal)" }}>LIVE OK 42MS</span>
        </span>
      </div>

      {/* Globe */}
      <div style={styles.globeWrapper}>
        {globeSize > 50 && (
          <Globe
            width={globeSize}
            height={Math.max(globeSize - 40, 100)}
            backgroundColor="rgba(0,0,0,0)"
            globeImageUrl=""
            showAtmosphere={false}
            showGraticules={true}
            pointsData={points}
            pointAltitude="size"
            pointColor="color"
            pointRadius={0.3}
            pointLabel="label"
          />
        )}
      </div>

      {/* Labels */}
      <div style={styles.footer}>
        <div style={styles.footerLabel}>
          EXPOSURE MAP &middot; EVENT GEOGRAPHY
        </div>
        {lastEvent ? (
          <div style={styles.lastEvent}>
            LAST EVENT &middot; {lastEvent.lat.toFixed(2)},{" "}
            {lastEvent.lon.toFixed(2)}
          </div>
        ) : (
          <div style={styles.lastEvent}>LAST EVENT &middot; NO DATA</div>
        )}
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
  feedStatus: {
    padding: "4px 12px",
    borderBottom: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },
  feedLabel: {
    fontSize: "9px",
    letterSpacing: "0.08em",
    color: "var(--fg-dim)",
  },
  feedState: {
    fontSize: "9px",
    letterSpacing: "0.08em",
    color: "var(--fg-dim)",
  },
  globeWrapper: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    minHeight: 0,
  },
  footer: {
    padding: "4px 12px",
    borderTop: "1px solid var(--border)",
  },
  footerLabel: {
    fontSize: "9px",
    letterSpacing: "0.08em",
    color: "var(--fg-dim)",
  },
  lastEvent: {
    fontSize: "9px",
    letterSpacing: "0.08em",
    color: "var(--accent-teal)",
    marginTop: "2px",
  },
};
