import type React from "react";

export default function Playbook(): React.ReactElement {
  return (
    <div style={styles.container}>
      <div className="panel-header">PLAYBOOK</div>
      <div style={styles.empty}>0 SAVED SCENARIOS</div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    fontFamily: "var(--font-mono)",
  },
  empty: {
    padding: "8px 12px",
    fontSize: "9px",
    letterSpacing: "0.1em",
    color: "var(--fg-dim)",
  },
};
