/**
 * ORBIT API client — wraps all backend calls with Zod validation.
 */

import { z } from "zod";
import {
  Bar,
  VerdictObject,
  Position,
  ScoredEvent,
  ScorecardRow,
  StatusMessage,
  ExecuteResponse,
  CommandResponse,
} from "./types";
import type { ExecuteRequest, CommandRequest } from "./types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIMEOUT_MS = 10_000;
const IS_DEV: boolean =
  typeof import.meta !== "undefined" && import.meta.env.DEV;

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function log(...args: unknown[]): void {
  if (IS_DEV) {
    console.log("[ORBIT API]", ...args);
  }
}

async function request(
  url: string,
  schema: z.ZodTypeAny,
  init?: RequestInit,
): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, TIMEOUT_MS);

  try {
    log("->", init?.method ?? "GET", url);

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    if (init?.headers) {
      const initHeaders = init.headers as Record<string, string>;
      for (const [k, v] of Object.entries(initHeaders)) {
        headers[k] = v;
      }
    }

    const res = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "unknown error");
      throw new ApiError(res.status, `${String(res.status)}: ${text}`);
    }

    const json: unknown = await res.json();
    const parsed: unknown = schema.parse(json);

    log("<-", url, "OK");
    return parsed;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

type BarOutput = z.output<typeof Bar>;
type VerdictOutput = z.output<typeof VerdictObject>;
type PositionOutput = z.output<typeof Position>;
type ScoredEventOutput = z.output<typeof ScoredEvent>;
type ScorecardRowOutput = z.output<typeof ScorecardRow>;
type StatusMessageOutput = z.output<typeof StatusMessage>;
type ExecuteResponseOutput = z.output<typeof ExecuteResponse>;
type CommandResponseOutput = z.output<typeof CommandResponse>;

export async function fetchChart(ticker: string): Promise<BarOutput[]> {
  return (await request(`/api/chart/${ticker}`, z.array(Bar))) as BarOutput[];
}

export async function fetchVerdict(ticker: string): Promise<VerdictOutput> {
  return (await request(
    `/api/verdict/${ticker}`,
    VerdictObject,
  )) as VerdictOutput;
}

export async function fetchPositions(): Promise<PositionOutput[]> {
  return (await request(
    "/api/portfolio/positions",
    z.array(Position),
  )) as PositionOutput[];
}

export async function fetchEvents(
  ticker: string,
): Promise<ScoredEventOutput[]> {
  return (await request(
    `/api/events/${ticker}`,
    z.array(ScoredEvent),
  )) as ScoredEventOutput[];
}

export async function fetchRecentEvents(): Promise<ScoredEventOutput[]> {
  return (await request(
    "/api/events/recent",
    z.array(ScoredEvent),
  )) as ScoredEventOutput[];
}

export async function fetchScorecardBacktest(): Promise<ScorecardRowOutput[]> {
  return (await request(
    "/api/scorecard/backtest",
    z.array(ScorecardRow),
  )) as ScorecardRowOutput[];
}

export async function fetchScorecardLive(): Promise<ScorecardRowOutput[]> {
  return (await request(
    "/api/scorecard/live",
    z.array(ScorecardRow),
  )) as ScorecardRowOutput[];
}

export async function executeTradeAPI(
  body: ExecuteRequest,
): Promise<ExecuteResponseOutput> {
  return (await request("/api/trades/execute", ExecuteResponse, {
    method: "POST",
    body: JSON.stringify(body),
  })) as ExecuteResponseOutput;
}

export async function parseCommand(
  body: CommandRequest,
): Promise<CommandResponseOutput> {
  return (await request("/api/command/parse", CommandResponse, {
    method: "POST",
    body: JSON.stringify(body),
  })) as CommandResponseOutput;
}

export async function fetchStatus(): Promise<StatusMessageOutput> {
  return (await request("/api/status", StatusMessage)) as StatusMessageOutput;
}
