/**
 * ORBIT Zod schemas — mirrors backend Pydantic models exactly.
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export const DirectionEnum = z.enum(["long", "short", "flat"]);
export type DirectionEnum = z.infer<typeof DirectionEnum>;

export const VerdictClass = z.enum([
  "strong_buy",
  "buy",
  "hold",
  "sell",
  "strong_sell",
]);
export type VerdictClass = z.infer<typeof VerdictClass>;

// ---------------------------------------------------------------------------
// Domain models (match SQLite tables)
// ---------------------------------------------------------------------------

export const ScoredEvent = z.object({
  id: z.string(),
  source: z.string(),
  timestamp: z.string(),
  description: z.string(),
  cameo_code: z.string().default(""),
  goldstein_score: z.number().default(0),
  num_sources: z.number().int().default(1),
  lat: z.number().default(0),
  lon: z.number().default(0),
  countries: z.array(z.string()).default([]),
  sentiment: z.number().default(0),
  metadata: z.record(z.string(), z.string()).default({}),
  ticker: z.string().default(""),
  relevance: z.number().default(0),
  implied_direction: DirectionEnum.default("flat"),
  computed_at: z.string().nullable().default(null),
});
export type ScoredEvent = z.infer<typeof ScoredEvent>;

export const VerdictObject = z.object({
  id: z.string(),
  ticker: z.string(),
  verdict_class: VerdictClass.default("hold"),
  direction: DirectionEnum.default("flat"),
  relevance_score: z.number().default(0),
  issued_at: z.string(),
  verdict_object: z.record(z.string(), z.string()).default({}),
});
export type VerdictObject = z.infer<typeof VerdictObject>;

export const Trade = z.object({
  id: z.string(),
  verdict_id: z.string(),
  ticker: z.string(),
  direction: DirectionEnum,
  size_shares: z.number().int(),
  entry_price: z.number(),
  exit_price: z.number().nullable().default(null),
  executed_at: z.string(),
  closed_at: z.string().nullable().default(null),
  realized_pnl: z.number().nullable().default(null),
});
export type Trade = z.infer<typeof Trade>;

export const OutcomeRecord = z.object({
  event_id: z.string(),
  verdict_id: z.string(),
  trade_id: z.string(),
  horizon: z.string(),
  forward_return: z.number(),
  directionally_correct: z.boolean(),
  computed_at: z.string(),
});
export type OutcomeRecord = z.infer<typeof OutcomeRecord>;

export const Bar = z.object({
  ticker: z.string(),
  timestamp: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().int(),
});
export type Bar = z.infer<typeof Bar>;

export const PortSnapshot = z.object({
  location: z.string(),
  lat: z.number(),
  lon: z.number(),
  ship_count: z.number().int(),
  timestamp: z.string(),
});
export type PortSnapshot = z.infer<typeof PortSnapshot>;

// ---------------------------------------------------------------------------
// Scorecard / dashboard helpers
// ---------------------------------------------------------------------------

export const ScorecardRow = z.object({
  ticker: z.string(),
  total_trades: z.number().int(),
  wins: z.number().int(),
  losses: z.number().int(),
  win_rate: z.number(),
  avg_return: z.number(),
  sharpe: z.number(),
});
export type ScorecardRow = z.infer<typeof ScorecardRow>;

export const StatusMessage = z.object({
  level: z.string(),
  message: z.string(),
  timestamp: z.string(),
});
export type StatusMessage = z.infer<typeof StatusMessage>;

export const Position = z.object({
  ticker: z.string(),
  direction: DirectionEnum,
  size_shares: z.number().int(),
  entry_price: z.number(),
  current_price: z.number(),
  unrealized_pnl: z.number(),
});
export type Position = z.infer<typeof Position>;

// ---------------------------------------------------------------------------
// Request / Response models
// ---------------------------------------------------------------------------

export const ExecuteRequest = z.object({
  ticker: z.string(),
  direction: DirectionEnum,
  size_shares: z.number().int(),
});
export type ExecuteRequest = z.infer<typeof ExecuteRequest>;

export const ExecuteResponse = z.object({
  success: z.boolean(),
  trade_id: z.string(),
  message: z.string(),
});
export type ExecuteResponse = z.infer<typeof ExecuteResponse>;

export const CommandRequest = z.object({
  command: z.string(),
});
export type CommandRequest = z.infer<typeof CommandRequest>;

export const CommandResponse = z.object({
  success: z.boolean(),
  output: z.string(),
});
export type CommandResponse = z.infer<typeof CommandResponse>;
