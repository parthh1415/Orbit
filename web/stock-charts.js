// Stock chart component — live candlesticks via lightweight-charts v5.
// Replaces the TradingView iframe embed. Loaded with <script defer> so it
// doesn't block page boot; lightweight-charts itself is lazy-loaded on the
// first pane init and reused across panes.
//
// Data plan:
//   Historical backfill  → Yahoo Finance chart API via a public CORS-friendly
//                          proxy (allorigins.win/raw). One fetch per symbol,
//                          cached on the pane. Daily OHLC, ~6 months.
//   Live tick updates    → Finnhub /quote poll per symbol (its O/H/L/C fields
//                          track the session), merged into today's forming
//                          candle and pushed via series.update() each tick.
//
// Integration contract:
//   window.__PrismCharts.mount({ tabsEl, inner, symbols })
// where `tabsEl` is <ul id="main_shell_tabs"> and `inner` is
// #main_shell_innercontainer. Each `symbols[i]` is { ticker, finnhub, yahoo }.

(function () {
    "use strict";

    // === Config ===========================================================
    const FINNHUB_KEY = (window.__ENV && window.__ENV.FINNHUB_KEY) || "";
    const POLL_MS = 5000;           // /quote poll cadence per symbol
    const HISTORY_RANGE = "6mo";    // Yahoo range for backfill
    const HISTORY_INTERVAL = "1d";  // Yahoo interval for backfill

    // Colors come from the active theme's CSS variables (populated by
    // _loadTheme()), so a settings.json theme switch propagates to charts.
    function themeColors() {
        const cs = getComputedStyle(document.documentElement);
        const r = (cs.getPropertyValue("--color_r") || "255").trim();
        const g = (cs.getPropertyValue("--color_g") || "255").trim();
        const b = (cs.getPropertyValue("--color_b") || "255").trim();
        const fg = `rgb(${r}, ${g}, ${b})`;
        return {
            bg: "#000000",
            fg,
            grid: `rgba(${r}, ${g}, ${b}, 0.08)`,
            border: `rgba(${r}, ${g}, ${b}, 0.25)`,
            up: fg,
            down: `rgba(${r}, ${g}, ${b}, 0.35)`,
        };
    }

    // === Lib loader =======================================================
    let libPromise = null;
    function loadLib() {
        if (window.LightweightCharts) return Promise.resolve(window.LightweightCharts);
        if (libPromise) return libPromise;
        libPromise = new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = "src/node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js";
            s.async = true;
            s.onload = () => resolve(window.LightweightCharts);
            s.onerror = () => reject(new Error("failed to load lightweight-charts"));
            document.head.appendChild(s);
        });
        return libPromise;
    }

    // === Data layer =======================================================
    // Yahoo returns trading-day timestamps for the last `range` interval.
    // Proxied through our local server at /api/chart/:symbol to avoid CORS.
    async function fetchHistory(yahooSym) {
        const url = `/api/chart/${encodeURIComponent(yahooSym)}?interval=${HISTORY_INTERVAL}&range=${HISTORY_RANGE}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error("history " + res.status);
        const j = await res.json();
        const result = j && j.chart && j.chart.result && j.chart.result[0];
        if (!result) throw new Error("history: empty result");
        const ts = result.timestamp || [];
        const q = (result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
        const o = q.open || [], h = q.high || [], l = q.low || [], c = q.close || [];
        // Yahoo occasionally returns null holes for non-trading days — skip them.
        const bars = [];
        for (let i = 0; i < ts.length; i++) {
            if (o[i] == null || h[i] == null || l[i] == null || c[i] == null) continue;
            bars.push({ time: ts[i], open: +o[i], high: +h[i], low: +l[i], close: +c[i] });
        }
        bars.sort((a, b) => a.time - b.time);
        // lightweight-charts rejects duplicate timestamps on setData — dedupe.
        const dedup = [];
        for (const bar of bars) {
            if (dedup.length && dedup[dedup.length - 1].time === bar.time) dedup[dedup.length - 1] = bar;
            else dedup.push(bar);
        }
        return dedup;
    }

    async function fetchQuote(symbol) {
        if (!FINNHUB_KEY) return null;
        const url = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol)}&token=${FINNHUB_KEY}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error("quote " + res.status);
        const j = await res.json();
        if (typeof j.c !== "number" || !j.t) return null;
        // c=current, h=day high, l=day low, o=day open.
        return { time: j.t, open: +j.o, high: +j.h, low: +j.l, close: +j.c };
    }

    // Fetch OHLCV bars from the ORBIT backend. During replay mode the backend
    // inserts bars with recent timestamps; these will be newer than Yahoo
    // historical candles and extend the chart in real-time.
    // Returns [{time (unix s), open, high, low, close}, ...] sorted ascending.
    async function fetchBackendBars(ticker) {
        const url = `/api/bars/${encodeURIComponent(ticker)}?limit=100`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) return [];
        const arr = await res.json();
        if (!Array.isArray(arr) || arr.length === 0) return [];
        return arr.map(function (b) {
            // The backend returns ISO-8601 timestamps — convert to unix seconds.
            var ts = typeof b.timestamp === "number"
                ? b.timestamp
                : Math.floor(new Date(b.timestamp).getTime() / 1000);
            return { time: alignDay(ts), open: +b.open, high: +b.high, low: +b.low, close: +b.close };
        }).sort(function (a, b) { return a.time - b.time; });
    }

    // Align a unix-seconds timestamp to 00:00:00 UTC of that day (daily bar).
    function alignDay(unix) {
        return Math.floor(unix / 86400) * 86400;
    }

    // Build lightweight-charts markers from ORBIT event objects.
    // High-relevance (>=0.55) → circle, size 2; medium (>=0.30) → arrow, size 1.
    function buildEventMarkers(events) {
        if (!Array.isArray(events) || events.length === 0) return [];
        return events.filter(function (e) { return e.relevance >= 0.30; }).map(function (e) {
            var high = e.relevance >= 0.55;
            var isShort = e.implied_direction === 'short';
            var shape;
            if (high) {
                shape = 'circle';
            } else {
                shape = isShort ? 'arrowDown' : 'arrowUp';
            }
            return {
                time: Math.floor(new Date(e.timestamp).getTime() / 1000),
                position: isShort ? 'aboveBar' : 'belowBar',
                color: high ? '#5eead4' : '#facc15',
                shape: shape,
                size: high ? 2 : 1,
                text: e.relevance.toFixed(2),
            };
        }).sort(function (a, b) { return a.time - b.time; });
    }

    // === Chart pane =======================================================
    function createPane(container, finnhubSym, yahooSym) {
        const pane = {
            container, finnhubSym, yahooSym,
            chart: null, series: null,
            bars: [], timer: null, resizeObs: null,
            initialized: false, destroyed: false,
            priceLines: [],
            _queuedLines: null,
            _currentMarkers: [],
        };

        // Supports TP/SL overlays via createPriceLine() (preserved from the
        // previous chart's contract; queue until the series exists).
        pane.addPriceLine = (opts) => {
            if (!pane.series) { pane._queuedLines = (pane._queuedLines || []).concat(opts); return null; }
            const line = pane.series.createPriceLine(opts);
            pane.priceLines.push(line);
            return line;
        };

        pane.init = async () => {
            if (pane.initialized || pane.destroyed) return;
            pane.initialized = true;

            const LC = await loadLib();
            if (pane.destroyed) return;

            const theme = themeColors();

            if (!FINNHUB_KEY) {
                container.innerHTML =
                    '<div style="position:absolute;inset:0;display:flex;align-items:center;' +
                    'justify-content:center;color:' + theme.fg + ';font-family:var(--font_main);' +
                    'text-align:center;padding:2vh;letter-spacing:0.2em;font-size:1.4vh;">' +
                    'NO FINNHUB API KEY</div>';
                return;
            }

            pane.chart = LC.createChart(container, {
                width: container.clientWidth,
                height: container.clientHeight,
                layout: { background: { type: "solid", color: theme.bg }, textColor: theme.fg },
                grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
                rightPriceScale: { borderColor: theme.border },
                timeScale: {
                    borderColor: theme.border,
                    timeVisible: true,
                    secondsVisible: false,
                    rightOffset: 4,
                    fixLeftEdge: false,
                    fixRightEdge: false,
                },
                crosshair: { mode: 1 },
            });

            // v5 API: addSeries(SeriesDefinition, options).
            pane.series = pane.chart.addSeries(LC.CandlestickSeries, {
                upColor: "#22c55e",
                downColor: "#ef4444",
                borderUpColor: "#22c55e",
                borderDownColor: "#ef4444",
                wickUpColor: "#22c55e",
                wickDownColor: "#ef4444",
            });

            // Apply queued TP/SL price lines now that the series is ready.
            if (pane._queuedLines) {
                for (const opts of pane._queuedLines) {
                    pane.priceLines.push(pane.series.createPriceLine(opts));
                }
                pane._queuedLines = null;
            }

            // Apply queued trade entry lines.
            if (pane._queuedTradeLines) {
                pane._tradeLines = pane._tradeLines || [];
                for (const opts of pane._queuedTradeLines) {
                    pane._tradeLines.push(pane.series.createPriceLine(opts));
                }
                pane._queuedTradeLines = null;
            }

            // Historical backfill: single setData() per the rules.
            try {
                const hist = await fetchHistory(pane.yahooSym);
                if (pane.destroyed) return;
                pane.bars = hist;
                if (hist.length) pane.series.setData(hist);

                // ORBIT event markers — overlay geopolitical events on the chart.
                try {
                    var events = await fetch('/api/events/' + pane.yahooSym).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; });
                    var markers = buildEventMarkers(events);
                    if (markers.length > 0) {
                        pane.series.setMarkers(markers);
                        pane._currentMarkers = markers;
                    }
                } catch (_evtErr) { /* ORBIT events non-fatal — skip markers silently */ }

                // Show EWMA stress as a horizontal price line on the candlestick series.
                // A line series doesn't work here because all events share one date
                // (replay day) — the line collapses to a single dot. A price line
                // spans the full chart width and updates cleanly.
                pane._stressLine = null;
                try {
                    var statsResp = await fetch('/api/stats/' + pane.finnhubSym).then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; });
                    if (statsResp && statsResp.ewma && statsResp.ewma.current_stress > 0) {
                        // Map stress (0-1) to a price level near the bottom of the chart
                        var lastBar = pane.bars[pane.bars.length - 1];
                        if (lastBar) {
                            // Place stress line relative to price range
                            var priceRange = lastBar.high - lastBar.low;
                            var stressPrice = lastBar.low - priceRange * 0.05; // just below candles
                            pane._stressLine = pane.series.createPriceLine({
                                price: stressPrice,
                                color: statsResp.ewma.is_escalating ? 'rgba(248, 113, 113, 0.7)' : 'rgba(250, 204, 21, 0.5)',
                                lineWidth: 1,
                                lineStyle: 1, // dashed
                                axisLabelVisible: true,
                                title: 'STRESS ' + statsResp.ewma.current_stress.toFixed(2) + (statsResp.ewma.is_escalating ? ' ↑' : ''),
                            });
                        }
                    }
                } catch (e) { /* ignore */ }

                pane.chart.timeScale().fitContent();
            } catch (e) {
                console.warn("history fetch failed for " + pane.yahooSym + ":", e.message);
            }

            // Seed today's forming bar from /quote so the latest candle
            // reflects current session even before the first poll tick.
            try {
                const q = await fetchQuote(pane.finnhubSym);
                if (q && !pane.destroyed) mergeQuote(pane, q);
            } catch (e) { /* non-fatal */ }

            // ResizeObserver keeps the chart sized to its container; no
            // window resize listener per the rules.
            pane.resizeObs = new ResizeObserver((entries) => {
                if (!pane.chart) return;
                const rect = entries[0].contentRect;
                pane.chart.applyOptions({
                    width: Math.floor(rect.width),
                    height: Math.floor(rect.height),
                });
            });
            pane.resizeObs.observe(container);

            // Live ticks: merge /quote AND ORBIT backend bars into the
            // chart. Whichever source has newer data wins.
            pane.timer = setInterval(async () => {
                if (pane.destroyed) return;

                // 1. Finnhub /quote — updates today's forming candle.
                try {
                    const q = await fetchQuote(pane.finnhubSym);
                    if (q && !pane.destroyed) mergeQuote(pane, q);
                } catch (e) { /* transient — skip tick */ }

                // 2. ORBIT backend /api/bars — picks up replay-injected bars
                //    that are newer than the latest bar on the chart.
                if (pane.destroyed) return;
                try {
                    const backendBars = await fetchBackendBars(pane.finnhubSym);
                    if (pane.destroyed || backendBars.length === 0) return;
                    const lastTime = pane.bars.length ? pane.bars[pane.bars.length - 1].time : 0;
                    for (const bar of backendBars) {
                        if (bar.time > lastTime) {
                            // New bar beyond anything on the chart — append.
                            pane.bars.push(bar);
                            pane.series.update(bar);
                        } else if (bar.time === lastTime) {
                            // Same timestamp — update in place if backend has fresher data.
                            pane.bars[pane.bars.length - 1] = bar;
                            pane.series.update(bar);
                        }
                        // Bars older than the chart tip are ignored (historical).
                    }
                } catch (e) { /* backend unreachable — rely on Finnhub alone */ }

                // 3. Periodically refresh ORBIT event markers (every 30s = 6 × 5s).
                if (!pane._markerRefreshCount) pane._markerRefreshCount = 0;
                pane._markerRefreshCount++;
                if (pane._markerRefreshCount % 6 === 0) {
                    try {
                        var evts = await fetch('/api/events/' + pane.yahooSym).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; });
                        var mkrs = buildEventMarkers(evts);
                        if (!pane.destroyed && mkrs.length > 0) {
                            pane.series.setMarkers(mkrs);
                            pane._currentMarkers = mkrs;
                        }
                    } catch (_mr) { /* marker refresh non-fatal */ }
                }

                // Update stress price line periodically (every 30s)
                if (pane._stressLine && pane._markerRefreshCount && pane._markerRefreshCount % 6 === 0) {
                    try {
                        var stResp = await fetch('/api/stats/' + pane.finnhubSym).then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; });
                        if (stResp && stResp.ewma) {
                            pane.series.removePriceLine(pane._stressLine);
                            var lastB = pane.bars[pane.bars.length - 1];
                            if (lastB) {
                                var pRange = lastB.high - lastB.low;
                                pane._stressLine = pane.series.createPriceLine({
                                    price: lastB.low - pRange * 0.05,
                                    color: stResp.ewma.is_escalating ? 'rgba(248, 113, 113, 0.7)' : 'rgba(250, 204, 21, 0.5)',
                                    lineWidth: 1, lineStyle: 1, axisLabelVisible: true,
                                    title: 'STRESS ' + stResp.ewma.current_stress.toFixed(2) + (stResp.ewma.is_escalating ? ' \u2191' : ''),
                                });
                            }
                        }
                    } catch (e) {}
                }
            }, POLL_MS);
        };

        pane.destroy = () => {
            pane.destroyed = true;
            if (pane.timer) { clearInterval(pane.timer); pane.timer = null; }
            if (pane.resizeObs) { pane.resizeObs.disconnect(); pane.resizeObs = null; }
            if (pane.chart) { try { pane.chart.remove(); } catch (e) {} pane.chart = null; }
        };

        return pane;
    }

    // Fold a live /quote (O/H/L/C for today's session) into the forming
    // daily candle. If it's the same day as the last historical bar we
    // update in place; if it's a new day we append.
    function mergeQuote(pane, q) {
        const t = alignDay(q.time);
        const bar = { time: t, open: q.open, high: q.high, low: q.low, close: q.close };
        const last = pane.bars[pane.bars.length - 1];
        if (!last || t > last.time) {
            pane.bars.push(bar);
        } else if (t === last.time) {
            pane.bars[pane.bars.length - 1] = bar;
        } else {
            // Out-of-order (shouldn't happen) — ignore.
            return;
        }
        pane.series.update(bar);
    }

    // === Trade entry markers ================================================
    // Module-scoped reference to panes so addTradeLine / clearTradeLines can
    // look up a pane by ticker without being inside mount()'s closure.
    var _panes = [];

    function findPane(ticker) {
        var t = (ticker || "").toUpperCase();
        for (var i = 0; i < _panes.length; i++) {
            if ((_panes[i].finnhubSym || "").toUpperCase() === t) return _panes[i];
        }
        return null;
    }

    // Add a horizontal price line at the entry price after a trade executes.
    function addTradeLine(ticker, price, direction) {
        var pane = findPane(ticker);
        if (!pane) { console.warn("addTradeLine: no pane for " + ticker); return null; }
        var opts = {
            price: price,
            color: direction === "long" ? "#5eead4" : "#f87171",
            lineWidth: 1,
            lineStyle: 2,          // dashed
            axisLabelVisible: true,
            title: direction === "long" ? "BUY" : "SELL",
        };
        if (!pane.series) {
            // Series not ready yet — queue it.
            pane._queuedTradeLines = (pane._queuedTradeLines || []).concat(opts);
            return null;
        }
        var line = pane.series.createPriceLine(opts);
        pane._tradeLines = pane._tradeLines || [];
        pane._tradeLines.push(line);
        return line;
    }

    // Remove all trade entry lines for a given ticker.
    function clearTradeLines(ticker) {
        var pane = findPane(ticker);
        if (!pane) return;
        if (pane._tradeLines && pane.series) {
            for (var i = 0; i < pane._tradeLines.length; i++) {
                try { pane.series.removePriceLine(pane._tradeLines[i]); } catch (_) {}
            }
        }
        pane._tradeLines = [];
        // Also clear any queued lines that haven't been drawn yet.
        pane._queuedTradeLines = [];
    }

    // === Live marker flash ==================================================
    // Flash a temporary white marker on the chart at the given event's timestamp,
    // then after 2 seconds replace it with a normal-colored permanent marker.
    function flashEventMarker(ticker, unixTime, relevance, direction) {
        var pane = findPane(ticker);
        if (!pane || !pane.series || !pane.initialized) return;

        // Use the last bar's timestamp so marker appears on a visible candle.
        // lightweight-charts only renders markers at timestamps that have a
        // corresponding bar — using alignDay(unixTime) can miss if no bar
        // exists at that day-aligned timestamp.
        var lastBar = pane.bars[pane.bars.length - 1];
        var markerTime = lastBar ? lastBar.time : alignDay(unixTime);

        // Get existing markers
        var existing = pane._currentMarkers || [];

        // Add a bright flash marker
        var flashMarker = {
            time: markerTime,
            position: direction === 'short' ? 'aboveBar' : 'belowBar',
            color: '#ffffff',  // white flash
            shape: 'circle',
            size: 3,  // bigger than normal
            text: '\u2605 ' + relevance.toFixed(2),
        };

        var withFlash = existing.concat([flashMarker]);
        withFlash.sort(function(a, b) { return a.time - b.time; });

        try {
            pane.series.setMarkers(withFlash);
        } catch(e) {}

        // After 2 seconds, revert to normal markers (remove the flash)
        setTimeout(function() {
            try {
                // Rebuild normal markers
                var normal = existing.slice();
                // Replace the flash with a normal-colored marker
                normal.push({
                    time: markerTime,
                    position: direction === 'short' ? 'aboveBar' : 'belowBar',
                    color: relevance >= 0.55 ? '#5eead4' : '#facc15',
                    shape: 'circle',
                    size: 2,
                    text: relevance.toFixed(2),
                });
                normal.sort(function(a, b) { return a.time - b.time; });
                pane.series.setMarkers(normal);
                pane._currentMarkers = normal;
            } catch(e) {}
        }, 2000);
    }

    // === Mount ============================================================
    // Total tab slots in the eDEX UI (main_shell_tabs has 5 <li> elements).
    var TOTAL_TAB_SLOTS = 5;

    async function mount({ tabsEl, inner, symbols }) {
        if (!tabsEl || !inner || !Array.isArray(symbols) || symbols.length === 0) return;

        // Rename active tabs to ticker labels.
        symbols.forEach((s, i) => {
            const li = document.getElementById("shell_tab" + i);
            if (li) li.innerHTML = "<p>" + s.ticker + "</p>";
        });

        // Dim the unused / empty tab slots so they look inactive and
        // don't mislead the user into thinking there's a chart behind them.
        for (let i = symbols.length; i < TOTAL_TAB_SLOTS; i++) {
            const li = document.getElementById("shell_tab" + i);
            if (li) {
                li.innerHTML = "<p>EMPTY</p>";
                li.style.opacity = "0.25";
                li.style.pointerEvents = "none";
            }
        }

        // Pre-size containers so the canvas mounts without layout shift.
        inner.innerHTML = symbols.map((s, i) => (
            '<div class="stock_chart' + (i === 0 ? " active" : "") + '"' +
            ' id="stock_chart' + i + '"' +
            ' style="position:absolute;inset:0;width:100%;height:100%;' + (i === 0 ? "" : "display:none;") + '"></div>'
        )).join("");

        const style = document.createElement("style");
        style.textContent =
            "#main_shell_innercontainer { padding: 0 !important; overflow: hidden; position: relative; }" +
            "#main_shell_innercontainer .stock_chart { background: #000; }";
        document.head.appendChild(style);

        const panes = symbols.map((s, i) => createPane(
            document.getElementById("stock_chart" + i),
            s.finnhub || s.ticker,
            s.yahoo || s.finnhub || s.ticker,
        ));
        // Expose panes to module-scoped helpers (addTradeLine, etc.).
        _panes = panes;

        // IntersectionObserver-gated init: panes start unrealized and only
        // build their chart when first visible (display:none containers
        // don't trigger, so hidden tabs stay dormant until switched to).
        const io = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    const idx = Number(entry.target.id.replace("stock_chart", ""));
                    if (panes[idx]) panes[idx].init();
                    io.unobserve(entry.target);
                }
            }
        }, { root: null, threshold: 0.01 });
        panes.forEach(p => io.observe(p.container));

        window.currentTerm = 0;
        window.focusShellTab = function (n) {
            // Guard: empty / out-of-range tabs are no-ops (no crash).
            if (n < 0 || n >= panes.length) return;
            window.currentTerm = n;
            document.querySelectorAll("#main_shell_tabs > li").forEach((li, i) => {
                if (i < panes.length) {
                    li.className = i === n ? "active" : "";
                }
                // Empty tabs (i >= panes.length) keep their dimmed state untouched.
            });
            panes.forEach((p, i) => {
                p.container.style.display = i === n ? "block" : "none";
            });
            if (!panes[n].initialized) panes[n].init();
        };

        return { panes };
    }

    window.__PrismCharts = { mount, addTradeLine, clearTradeLines, flashEventMarker };
})();
