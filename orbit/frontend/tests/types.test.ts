/**
 * Tests for ORBIT Zod schemas in types.ts.
 */
import { describe, expect, it } from "vitest";
import {
  Bar,
  CommandRequest,
  CommandResponse,
  DirectionEnum,
  ExecuteRequest,
  ExecuteResponse,
  OutcomeRecord,
  PortSnapshot,
  Position,
  ScorecardRow,
  ScoredEvent,
  StatusMessage,
  Trade,
  VerdictClass,
  VerdictObject,
} from "../src/types";

// ---------------------------------------------------------------------------
// Enum schemas
// ---------------------------------------------------------------------------

describe("DirectionEnum", () => {
  it("accepts valid values", () => {
    expect(DirectionEnum.parse("long")).toBe("long");
    expect(DirectionEnum.parse("short")).toBe("short");
    expect(DirectionEnum.parse("flat")).toBe("flat");
  });

  it("rejects invalid values", () => {
    expect(() => DirectionEnum.parse("up")).toThrow();
  });
});

describe("VerdictClass", () => {
  it("accepts all five values", () => {
    const values = ["strong_buy", "buy", "hold", "sell", "strong_sell"];
    for (const v of values) {
      expect(VerdictClass.parse(v)).toBe(v);
    }
  });
});

// ---------------------------------------------------------------------------
// ScoredEvent
// ---------------------------------------------------------------------------

describe("ScoredEvent", () => {
  const minimal = {
    id: "e1",
    source: "newsapi",
    timestamp: "2025-01-01T00:00:00Z",
    description: "Test event",
  };

  it("parses minimal payload with defaults", () => {
    const ev = ScoredEvent.parse(minimal);
    expect(ev.id).toBe("e1");
    expect(ev.countries).toEqual([]);
    expect(ev.implied_direction).toBe("flat");
    expect(ev.computed_at).toBeNull();
  });

  it("parses full payload", () => {
    const ev = ScoredEvent.parse({
      ...minimal,
      cameo_code: "0211",
      goldstein_score: 3.4,
      num_sources: 5,
      lat: 34.0,
      lon: -118.0,
      countries: ["US", "CN"],
      sentiment: 0.75,
      metadata: { key: "val" },
      ticker: "AAPL",
      relevance: 0.9,
      implied_direction: "long",
      computed_at: "2025-01-01T00:00:00Z",
    });
    expect(ev.countries).toEqual(["US", "CN"]);
    expect(ev.ticker).toBe("AAPL");
  });
});

// ---------------------------------------------------------------------------
// VerdictObject
// ---------------------------------------------------------------------------

describe("VerdictObject", () => {
  it("parses with defaults", () => {
    const v = VerdictObject.parse({
      id: "v1",
      ticker: "NVDA",
      issued_at: "2025-01-01T00:00:00Z",
    });
    expect(v.verdict_class).toBe("hold");
    expect(v.direction).toBe("flat");
    expect(v.verdict_object).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Trade
// ---------------------------------------------------------------------------

describe("Trade", () => {
  it("parses open trade", () => {
    const t = Trade.parse({
      id: "t1",
      verdict_id: "v1",
      ticker: "TSM",
      direction: "long",
      size_shares: 100,
      entry_price: 95.0,
      executed_at: "2025-01-01T00:00:00Z",
    });
    expect(t.exit_price).toBeNull();
    expect(t.closed_at).toBeNull();
    expect(t.realized_pnl).toBeNull();
  });

  it("parses closed trade", () => {
    const t = Trade.parse({
      id: "t2",
      verdict_id: "v1",
      ticker: "TSM",
      direction: "short",
      size_shares: 50,
      entry_price: 100.0,
      exit_price: 90.0,
      executed_at: "2025-01-01T00:00:00Z",
      closed_at: "2025-01-02T00:00:00Z",
      realized_pnl: 500.0,
    });
    expect(t.realized_pnl).toBe(500.0);
  });
});

// ---------------------------------------------------------------------------
// OutcomeRecord
// ---------------------------------------------------------------------------

describe("OutcomeRecord", () => {
  it("parses valid payload", () => {
    const o = OutcomeRecord.parse({
      event_id: "e1",
      verdict_id: "v1",
      trade_id: "t1",
      horizon: "1d",
      forward_return: 0.02,
      directionally_correct: true,
      computed_at: "2025-01-01T00:00:00Z",
    });
    expect(o.directionally_correct).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Bar
// ---------------------------------------------------------------------------

describe("Bar", () => {
  it("parses OHLCV bar", () => {
    const b = Bar.parse({
      ticker: "AAPL",
      timestamp: "2025-01-01T00:00:00Z",
      open: 150.0,
      high: 155.0,
      low: 149.0,
      close: 153.0,
      volume: 1000000,
    });
    expect(b.close).toBe(153.0);
  });
});

// ---------------------------------------------------------------------------
// PortSnapshot
// ---------------------------------------------------------------------------

describe("PortSnapshot", () => {
  it("parses port data", () => {
    const p = PortSnapshot.parse({
      location: "Shanghai",
      lat: 31.2,
      lon: 121.5,
      ship_count: 42,
      timestamp: "2025-01-01T00:00:00Z",
    });
    expect(p.ship_count).toBe(42);
  });
});

// ---------------------------------------------------------------------------
// ScorecardRow
// ---------------------------------------------------------------------------

describe("ScorecardRow", () => {
  it("parses scorecard data", () => {
    const r = ScorecardRow.parse({
      ticker: "AAPL",
      total_trades: 10,
      wins: 7,
      losses: 3,
      win_rate: 0.7,
      avg_return: 0.015,
      sharpe: 1.5,
    });
    expect(r.win_rate).toBe(0.7);
  });
});

// ---------------------------------------------------------------------------
// StatusMessage
// ---------------------------------------------------------------------------

describe("StatusMessage", () => {
  it("parses status payload", () => {
    const s = StatusMessage.parse({
      level: "info",
      message: "System online",
      timestamp: "2025-01-01T00:00:00Z",
    });
    expect(s.level).toBe("info");
  });
});

// ---------------------------------------------------------------------------
// Position
// ---------------------------------------------------------------------------

describe("Position", () => {
  it("parses position summary", () => {
    const p = Position.parse({
      ticker: "NVDA",
      direction: "long",
      size_shares: 200,
      entry_price: 800.0,
      current_price: 850.0,
      unrealized_pnl: 10000.0,
    });
    expect(p.unrealized_pnl).toBe(10000.0);
  });
});

// ---------------------------------------------------------------------------
// ExecuteRequest / ExecuteResponse
// ---------------------------------------------------------------------------

describe("ExecuteRequest", () => {
  it("parses valid request", () => {
    const r = ExecuteRequest.parse({
      ticker: "AAPL",
      direction: "long",
      size_shares: 10,
    });
    expect(r.ticker).toBe("AAPL");
  });

  it("rejects invalid direction", () => {
    expect(() =>
      ExecuteRequest.parse({
        ticker: "AAPL",
        direction: "up",
        size_shares: 10,
      }),
    ).toThrow();
  });
});

describe("ExecuteResponse", () => {
  it("parses valid response", () => {
    const r = ExecuteResponse.parse({
      success: true,
      trade_id: "t1",
      message: "ok",
    });
    expect(r.success).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// CommandRequest / CommandResponse
// ---------------------------------------------------------------------------

describe("CommandRequest", () => {
  it("parses command", () => {
    const r = CommandRequest.parse({ command: "status" });
    expect(r.command).toBe("status");
  });
});

describe("CommandResponse", () => {
  it("parses response", () => {
    const r = CommandResponse.parse({ success: true, output: "all good" });
    expect(r.output).toBe("all good");
  });
});
