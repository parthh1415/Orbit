import { useState, useRef } from "react";
import type React from "react";
import { useOrbitStore } from "../../store";
import { parseCommand } from "../../api";

// ---------------------------------------------------------------------------
// Keyboard layout (aesthetic only)
// ---------------------------------------------------------------------------

const KB_ROWS: readonly (readonly string[])[] = [
  [
    "ESC",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
  ],
  ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "BKSP"],
  ["TAB", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "\\"],
  ["CAPS", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "ENTER"],
  ["SHIFT", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "SHIFT"],
  ["CTRL", "FN", "ALT", "", "ALT GR", "CTRL"],
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BottomBar(): React.ReactElement {
  const systemStatus = useOrbitStore((s) => s.systemStatus);
  const [commandText, setCommandText] = useState("");
  const [commandOutput, setCommandOutput] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (): void => {
    const trimmed = commandText.trim();
    if (!trimmed) return;

    parseCommand({ command: trimmed })
      .then((res) => {
        setCommandOutput(res.output);
        setCommandText("");
      })
      .catch(() => {
        setCommandOutput("ERROR: COMMAND FAILED");
      });
  };

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === "Enter") {
      handleSubmit();
    }
  };

  return (
    <div style={styles.container}>
      {/* Top section: playbook + status */}
      <div style={styles.topRow}>
        <div style={styles.playbook}>
          <span style={styles.playbookLabel}>PLAYBOOK</span>
          <span style={styles.playbookCount}>0 SAVED VIEWS</span>
        </div>
        <div style={styles.statusArea}>
          {commandOutput ? (
            <span style={styles.cmdOutput}>&gt; {commandOutput}</span>
          ) : systemStatus ? (
            <span
              style={{
                ...styles.statusText,
                color:
                  systemStatus.level === "error"
                    ? "var(--accent-coral)"
                    : systemStatus.level === "warning"
                      ? "var(--accent-yellow)"
                      : "var(--accent-teal)",
              }}
            >
              [{systemStatus.level.toUpperCase()}] {systemStatus.message}
            </span>
          ) : (
            <span style={styles.statusText}>ORBIT READY</span>
          )}
        </div>
      </div>

      {/* Keyboard aesthetic */}
      <div style={styles.keyboard}>
        {KB_ROWS.map((row, ri) => (
          <div key={ri} style={styles.kbRow}>
            {row.map((key, ki) => {
              // The empty string in row 5 is where the command input goes
              if (key === "" && ri === 5) {
                return (
                  <div key={ki} style={styles.inputWrapper}>
                    <input
                      ref={inputRef}
                      type="text"
                      value={commandText}
                      onChange={(e) => {
                        setCommandText(e.target.value);
                      }}
                      onKeyDown={handleKeyDown}
                      placeholder="COMMAND..."
                      style={styles.commandInput}
                      spellCheck={false}
                      autoComplete="off"
                    />
                  </div>
                );
              }
              return (
                <div
                  key={ki}
                  style={{
                    ...styles.key,
                    ...(key.length > 2 ? styles.keyWide : {}),
                  }}
                >
                  {key}
                </div>
              );
            })}
          </div>
        ))}
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
    padding: "8px 12px",
    gap: "6px",
    overflow: "hidden",
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
    flexShrink: 0,
  },
  playbook: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  playbookLabel: {
    fontSize: "10px",
    fontWeight: 500,
    letterSpacing: "0.1em",
    color: "var(--fg-dim)",
  },
  playbookCount: {
    fontSize: "9px",
    color: "var(--fg-dim)",
    letterSpacing: "0.08em",
  },
  statusArea: {
    flex: 1,
    textAlign: "right",
  },
  statusText: {
    fontSize: "9px",
    letterSpacing: "0.08em",
    color: "var(--accent-teal)",
  },
  cmdOutput: {
    fontSize: "10px",
    color: "var(--fg-primary)",
    letterSpacing: "0.04em",
    fontFamily: "var(--font-mono)",
  },
  keyboard: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    justifyContent: "center",
    overflow: "hidden",
  },
  kbRow: {
    display: "flex",
    gap: "2px",
    justifyContent: "center",
  },
  key: {
    minWidth: "24px",
    height: "22px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: "1px solid var(--border)",
    fontSize: "8px",
    letterSpacing: "0.04em",
    color: "var(--fg-dim)",
    fontFamily: "var(--font-mono)",
    padding: "0 4px",
    userSelect: "none",
    flexShrink: 0,
  },
  keyWide: {
    minWidth: "42px",
    padding: "0 6px",
  },
  inputWrapper: {
    flex: 1,
    maxWidth: "400px",
    height: "22px",
    display: "flex",
    alignItems: "center",
  },
  commandInput: {
    width: "100%",
    height: "100%",
    fontFamily: "var(--font-mono)",
    fontSize: "10px",
    letterSpacing: "0.06em",
    background: "transparent",
    border: "1px solid var(--accent-teal)",
    color: "var(--accent-teal)",
    padding: "0 8px",
    outline: "none",
    textTransform: "uppercase" as const,
  },
};
