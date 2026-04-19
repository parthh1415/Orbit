import { create } from "zustand";
import type {
  VerdictObject,
  Bar,
  ScoredEvent,
  Position,
  ScorecardRow,
  Trade,
  StatusMessage,
} from "./types";

// ---------------------------------------------------------------------------
// Ticker type
// ---------------------------------------------------------------------------

export type Ticker = "AAPL" | "NVDA" | "TSM";

export const TICKERS: readonly Ticker[] = ["AAPL", "NVDA", "TSM"] as const;

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

interface OrbitState {
  /* Selection */
  selectedTicker: Ticker;

  /* Data */
  currentVerdict: VerdictObject | null;
  chartData: Bar[];
  events: ScoredEvent[];
  positions: Position[];
  scorecardBacktest: ScorecardRow[];
  scorecardLive: ScorecardRow[];
  recentTrades: Trade[];
  systemStatus: StatusMessage | null;

  /* UI */
  selectedEventId: string | null;

  /* Actions */
  setTicker: (t: Ticker) => void;
  setVerdict: (v: VerdictObject | null) => void;
  setChartData: (d: Bar[]) => void;
  setEvents: (e: ScoredEvent[]) => void;
  setPositions: (p: Position[]) => void;
  setScorecardBacktest: (s: ScorecardRow[]) => void;
  setScorecardLive: (s: ScorecardRow[]) => void;
  setRecentTrades: (t: Trade[]) => void;
  setSystemStatus: (s: StatusMessage | null) => void;
  setSelectedEventId: (id: string | null) => void;
}

export const useOrbitStore = create<OrbitState>()((set) => ({
  /* Defaults */
  selectedTicker: "AAPL",
  currentVerdict: null,
  chartData: [],
  events: [],
  positions: [],
  scorecardBacktest: [],
  scorecardLive: [],
  recentTrades: [],
  systemStatus: null,
  selectedEventId: null,

  /* Actions */
  setTicker: (t) => {
    set({ selectedTicker: t });
  },
  setVerdict: (v) => {
    set({ currentVerdict: v });
  },
  setChartData: (d) => {
    set({ chartData: d });
  },
  setEvents: (e) => {
    set({ events: e });
  },
  setPositions: (p) => {
    set({ positions: p });
  },
  setScorecardBacktest: (s) => {
    set({ scorecardBacktest: s });
  },
  setScorecardLive: (s) => {
    set({ scorecardLive: s });
  },
  setRecentTrades: (t) => {
    set({ recentTrades: t });
  },
  setSystemStatus: (s) => {
    set({ systemStatus: s });
  },
  setSelectedEventId: (id) => {
    set({ selectedEventId: id });
  },
}));
