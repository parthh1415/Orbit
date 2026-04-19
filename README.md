# ORBIT — Geopolitical Event Intelligence Terminal

A real-time terminal that ingests global geopolitical events, scores their impact on semiconductor supply chains, and executes paper trades before the market reacts.

![Category](https://img.shields.io/badge/Category-Intelligent%20Financial%20%26%20Market%20Systems-blue)
![Python](https://img.shields.io/badge/Python-3.11-green)
![Tests](https://img.shields.io/badge/Tests-274%20passing-brightgreen)
![TypeSafe](https://img.shields.io/badge/mypy-strict%20%E2%9C%93-blue)

## The Problem

Semiconductor stocks (AAPL, NVDA, TSM) are heavily exposed to geopolitical risk — Taiwan strait tensions, China export controls, shipping disruptions. By the time a trader reads the news and reacts, the market has already moved. There is no tool that connects geopolitical events directly to actionable trading decisions in real-time.

## What ORBIT Does

**1. Ingests global events from 6 data feeds every 15–60 seconds**

| Feed | Source | What It Provides |
|------|--------|-----------------|
| GDELT v2 | Global Database of Events | 50K+ events with Goldstein conflict scores, country actors, geocoding |
| NewsAPI | Semiconductor headlines | Ticker-specific coverage sorted by recency |
| AIS Maritime | Port ship counts | Disruption signals at 7 semiconductor shipping ports |
| Flight Corridors | Supply chain logistics | 13 routes tracking semiconductor cargo movement |
| FRED | Macro indicators | VIX, 10Y Treasury, USD index |
| Alpaca | Real-time prices | Live mark-to-market for open positions |

**2. Scores each event against supply chain exposure**

```
relevance = exposure_weight × min(1, |goldstein|/5) × exp(-hours/24) × confidence
```

Exposure weights are calibrated from 10-K SEC filings:
- **AAPL**: Taiwan (TSMC fab) = 0.85, US = 0.43, China = 0.18
- **NVDA**: Taiwan (TSMC fab) = 0.80, US = 0.46, China = 0.15
- **TSM**: Taiwan (HQ + fabs) = 0.95, US (Arizona fab) = 0.30, China = 0.20

**3. Produces deterministic trading verdicts**

| Verdict | Condition | Action |
|---------|-----------|--------|
| **ACT** | Relevance ≥ 0.55, hit rate ≥ 54%, low contradiction | Execute trade |
| **WAIT** | Relevance 0.30–0.55 or mixed signals | Monitor |
| **IGNORE** | Relevance < 0.30 | No action |

**4. Executes one-click paper trades**

Kelly criterion position sizing (half-Kelly, clamped 5–25% of capital) with 2bps slippage. Starting capital: $100,000.

**5. Tracks performance with Bayesian statistics**

- Bayesian hit rate with recency weighting (recent trades count 2×)
- Wilson score 95% confidence intervals on win rate
- EWMA stress indicator detecting escalating event clusters

## The Terminal Interface

ORBIT runs inside a sci-fi terminal interface with every panel repurposed for financial intelligence:

| Panel | Function |
|-------|----------|
| Main area | TradingView candlestick charts (AAPL/NVDA/TSM tabs) with event markers and stress lines |
| Left column | Portfolio P&L, open positions, capital deployment, recent trades |
| Right column | Verdict display, 3D globe with event pins and supply chain arcs, Bayesian stats |
| Bottom left | Interactive event feed — click any event to rotate globe, flash chart marker, see sentiment |
| Bottom right | Equity curve — ORBIT vs Buy & Hold backtest comparison |

### Interactive Features

- **SCAN GDELT**: Triggers event ingestion with typewriter-animated feed
- **Click any event**: Globe rotates to coordinates, green/red sentiment pin + land-dot radius glow, chart marker flash
- **Tab switching**: AAPL/NVDA/TSM switches chart + events + verdict + globe simultaneously
- **One-click trade execution**: Paper trade directly from the verdict strip
- **3D Globe**: Real-time event pins, port markers, supply chain flow arcs

## Equity Curve — The Proof

The backtest shows ORBIT vs passive Buy & Hold over 5 trading days:

- **Monday**: Both track together (+$110). No geopolitical signals yet.
- **Tuesday**: Taiwan strait tension → ORBIT hedges TSM before the drop. Buy & Hold crashes to -$180. ORBIT stays at +$180.
- **Thursday**: China AI chip export controls → ORBIT shorts NVDA before the crash. Buy & Hold hit to -$340. ORBIT reaches +$405.
- **Friday**: ORBIT closes winners at **+$450**. Buy & Hold recovers to **-$80**.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, aiosqlite, APScheduler |
| Database | SQLite (WAL mode, 8 tables, 5 indexes) |
| Frontend | Browser-based terminal with lightweight-charts v5, Three.js globe, Howler.js audio |
| Data | GDELT v2, NewsAPI, Finnhub, Yahoo Finance, FRED |
| Testing | 274 tests, mypy strict, ruff lint — all passing |

## Quick Start

```bash
# 1. Backend
cd orbit/backend
pip install -e ".[dev]"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. Frontend
cd ../..
npm install
node web/server.js

# 3. Open
open http://localhost:8080
```

### API Keys

Create `~/.orbit-env` with your keys:
```
FINNHUB_KEY=your_finnhub_key
NEWSAPI_KEY=your_newsapi_key
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | System health |
| GET | `/api/verdict/{ticker}` | Current trading verdict |
| GET | `/api/events/{ticker}` | Scored geopolitical events |
| GET | `/api/events/recent` | Latest high-relevance events |
| GET | `/api/portfolio/positions` | Open positions |
| GET | `/api/portfolio/summary` | Portfolio P&L summary |
| GET | `/api/scorecard/backtest` | 6-month backtest results |
| GET | `/api/scorecard/live` | Live session scorecard |
| GET | `/api/stats/{ticker}` | Bayesian, Kelly, EWMA stats |
| GET | `/api/ports` | Maritime port snapshots |
| GET | `/api/flights` | Supply chain flight corridors |
| GET | `/api/bars/{ticker}` | OHLCV price bars |
| POST | `/api/trades/execute` | Execute paper trade |

## Scoring Engine

The relevance scoring formula combines four factors:

- **Exposure weight**: How dependent is this ticker on the affected country? (from 10-K filings)
- **Goldstein intensity**: How severe is the event? (normalized to |goldstein|/5)
- **Recency decay**: How fresh? (exponential decay, 24-hour half-life)
- **Source confidence**: How well-sourced? (≥10 sources = full confidence)

Events are aggregated per ticker: `max(highest_single, sum_of_top_3)`. The verdict engine then applies hit rate thresholds and contradiction checks to produce ACT/WAIT/IGNORE.

## Architecture

```
GDELT v2 ──┐
NewsAPI  ──┤
AIS      ──┤──→ Ingest ──→ Score ──→ Verdict ──→ Execute
FRED     ──┤       │          │          │          │
Flights  ──┤       ▼          ▼          ▼          ▼
Alpaca   ──┘    SQLite    event_scores  verdicts   trades
                  │
                  ▼
            FastAPI REST API (:8000)
                  │
            Node.js Proxy (:8080)
                  │
            Browser Terminal UI
```

## License

MIT
