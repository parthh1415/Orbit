// ORBIT UI layer — wires ORBIT backend data into the existing eDEX-UI
// panels. Runs AFTER the eDEX renderer has fully initialized. Does NOT move,
// resize, or redesign any element. Only replaces label text and numeric values
// inside existing DOM nodes.
//
// Every DOM access is wrapped in a null guard so one broken selector never
// crashes the rest of the relabeling.

(function () {
    "use strict";

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    async function api(path) {
        try {
            var controller = new AbortController();
            var timer = setTimeout(function () { controller.abort(); }, 5000);
            var res = await fetch(path, { cache: "no-store", signal: controller.signal });
            clearTimeout(timer);
            if (!res.ok) return null;
            return await res.json();
        } catch (e) { return null; }
    }

    function $(sel) { return document.querySelector(sel); }
    function $id(id) { return document.getElementById(id); }

    function safeText(el, text) { if (el) el.innerText = String(text); }
    function safeHTML(el, html) { if (el) el.innerHTML = html; }

    function formatPnl(n) {
        if (n == null) return "--";
        var sign = n >= 0 ? "+" : "";
        return sign + "$" + Math.abs(n).toFixed(2);
    }

    // Fix 3: Update the RAM watcher dot grid to reflect capital deployment
    function updateCapitalDots(deployed) {
        var pointmap = $id("mod_ramwatcher_pointmap");
        if (!pointmap) return;
        var dots = pointmap.querySelectorAll("div.mod_ramwatcher_point");
        if (!dots || dots.length === 0) return;

        var totalDots = dots.length; // 440 dots
        var pct = Math.min(Math.max(deployed / 100000, 0), 1);
        var activeDots = Math.round(pct * totalDots);

        for (var i = 0; i < totalDots; i++) {
            if (i < activeDots) {
                dots[i].setAttribute("class", "mod_ramwatcher_point active");
            } else {
                dots[i].setAttribute("class", "mod_ramwatcher_point free");
            }
        }

        // Also update the swap bar to show deployment percentage
        var swapBar = $id("mod_ramwatcher_swapbar");
        if (swapBar) swapBar.value = Math.round(pct * 100);
        var swapText = $id("mod_ramwatcher_swaptext");
        if (swapText) safeText(swapText, (pct * 100).toFixed(1) + "%");
    }

    // Boot timestamp for uptime tracking
    var _orbitBootTime = Date.now();

    // -----------------------------------------------------------------------
    // Timeline Narrative Log
    // -----------------------------------------------------------------------
    var narrativeLog = [];          // {time:String, text:String, ts:Number}
    var NARRATIVE_MAX = 50;
    var _lastVerdictClass = {};     // per-ticker last verdict class
    var _lastTotalPnl = null;       // last polled total P&L
    var _seenEventDescs = {};       // dedup recent GDELT events

    function narrativePush(text) {
        // Build sim-clock time from the replay (use real wall-clock as fallback)
        var now = new Date();
        var hh = String(now.getHours()).length < 2 ? "0" + now.getHours() : String(now.getHours());
        var mm = String(now.getMinutes()).length < 2 ? "0" + now.getMinutes() : String(now.getMinutes());
        var timeStr = hh + ":" + mm;
        narrativeLog.push({ time: timeStr, text: text, ts: Date.now() });
        if (narrativeLog.length > NARRATIVE_MAX) narrativeLog.shift();
        // Append to ticker instead of narrative log div
        var inner = $id("orbit-ticker-inner");
        if (inner) {
            var entry = narrativeLog[narrativeLog.length - 1];
            var existing = inner.innerHTML || "";
            var narrativeSnippet = '  <span style="color:#555;">\u00b7\u00b7\u00b7</span>  ' +
                '<span style="color:#555;">' + entry.time + '</span> ' +
                '<span style="color:#888;">' + entry.text + '</span>';
            inner.innerHTML = existing + narrativeSnippet;
        }
    }

    // -----------------------------------------------------------------------
    // Left Panel relabeling
    // -----------------------------------------------------------------------
    function relabelLeft() {
        try {
            // "PANEL · SYSTEM" -> "BOOK · DESK"
            var h = $("#mod_column_left > h3.title");
            safeHTML(h, "<p>BOOK</p><p>DESK</p>");

            // --- Sysinfo: relabel ALL four divs in 2x2 grid ---
            // Each box ~80px wide. h2 values must be <= 6 chars.
            // Apply overflow protection to all sysinfo h2 elements
            var sysH2Style = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:'Fira Mono',monospace;";

            // Div 1: h1="2026", h2="APR 14"
            var now = new Date();
            var monthNames = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
            var sysDiv1H1 = $("#mod_sysinfo > div:first-child > h1");
            var sysDiv1H2 = $("#mod_sysinfo > div:first-child > h2");
            safeText(sysDiv1H1, String(now.getFullYear()));
            if (sysDiv1H2) sysDiv1H2.style.cssText = sysH2Style;
            var dayStr = now.getDate() < 10 ? "0" + now.getDate() : String(now.getDate());
            safeText(sysDiv1H2, monthNames[now.getMonth()] + " " + dayStr);

            // Div 2: h1="LIVE", h2="0:00"
            var sysDiv2H1 = $("#mod_sysinfo > div:nth-child(2) > h1");
            var sysDiv2H2 = $("#mod_sysinfo > div:nth-child(2) > h2");
            safeText(sysDiv2H1, "LIVE");
            if (sysDiv2H2) sysDiv2H2.style.cssText = sysH2Style;
            safeText(sysDiv2H2, "0:00");

            // Div 3: h1="MODE", h2="PAPER"
            var sysDiv3H1 = $("#mod_sysinfo > div:nth-child(3) > h1");
            var sysDiv3H2 = $("#mod_sysinfo > div:nth-child(3) > h2");
            safeText(sysDiv3H1, "MODE");
            if (sysDiv3H2) sysDiv3H2.style.cssText = sysH2Style;
            safeText(sysDiv3H2, "PAPER");

            // Div 4: h1="FEED", h2="LIVE"
            var sysDiv4H1 = $("#mod_sysinfo > div:nth-child(4) > h1");
            var sysDiv4H2 = $("#mod_sysinfo > div:nth-child(4) > h2");
            safeText(sysDiv4H1, "FEED");
            if (sysDiv4H2) sysDiv4H2.style.cssText = sysH2Style;
            safeText(sysDiv4H2, "LIVE");

            // Hardware inspector labels
            var hwInner = $id("mod_hardwareInspector_inner");
            if (hwInner) {
                var divs = hwInner.querySelectorAll("div");
                if (divs[0]) { safeText(divs[0].querySelector("h1"), "ACCOUNT"); safeText(divs[0].querySelector("h2"), "MAIN"); }
                if (divs[1]) { safeText(divs[1].querySelector("h1"), "BROKER"); safeText(divs[1].querySelector("h2"), "ALPACA"); }
                if (divs[2]) { safeText(divs[2].querySelector("h1"), "VENUE"); safeText(divs[2].querySelector("h2"), "SIM"); }
            }

            // CPU header -> POSITIONS (cleanly stacked: POSITIONS / PAPER BOOK)
            var cpuH1 = $("#mod_cpuinfo_innercontainer > h1");
            if (cpuH1) {
                cpuH1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
                safeHTML(cpuH1, "POSITIONS<i style='font-family:inherit;font-size:9px;color:#888;float:right;font-style:normal;'>PAPER BOOK</i>");
            }

            // CPU sub-counters and group labels — collapsed: "LONG · +$687" / "SHORT · 4 OPEN"
            var cpuGroups = document.querySelectorAll("#mod_cpuinfo_innercontainer > div > h1");
            if (cpuGroups[0]) {
                cpuGroups[0].style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
                cpuGroups[0].innerHTML = "LONG <span style='color:#555;'>\u00b7</span> <span id='mod_cpuinfo_usagecounter0' style='font-family:inherit;font-size:10px;color:#888;font-style:normal;'>+$0</span>";
            }
            if (cpuGroups[1]) {
                cpuGroups[1].style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
                cpuGroups[1].innerHTML = "SHORT <span style='color:#555;'>\u00b7</span> <span id='mod_cpuinfo_usagecounter1' style='font-family:inherit;font-size:10px;color:#888;font-style:normal;'>0 OPEN</span>";
            }

            // Fix 4: Hide CPU chart canvases and repurpose space for position details
            var canvas0 = $id("mod_cpuinfo_canvas_0");
            var canvas1 = $id("mod_cpuinfo_canvas_1");
            if (canvas0) canvas0.style.display = "none";
            if (canvas1) canvas1.style.display = "none";

            // Insert position detail containers where the canvases were
            if (canvas0 && canvas0.parentNode && !$id("orbit-pos-detail-0")) {
                var detail0 = document.createElement("div");
                detail0.id = "orbit-pos-detail-0";
                detail0.style.cssText = "font-family:'Fira Mono',monospace;font-size:9px;color:#666;padding:2px 4px;min-height:40px;overflow:hidden;";
                detail0.innerHTML = '<span style="color:#555;">NO LONG POSITIONS</span>';
                canvas0.parentNode.insertBefore(detail0, canvas0.nextSibling);
            }
            if (canvas1 && canvas1.parentNode && !$id("orbit-pos-detail-1")) {
                var detail1 = document.createElement("div");
                detail1.id = "orbit-pos-detail-1";
                detail1.style.cssText = "font-family:'Fira Mono',monospace;font-size:9px;color:#666;padding:2px 4px;min-height:40px;overflow:hidden;";
                detail1.innerHTML = '<span style="color:#555;">NO SHORT POSITIONS</span>';
                canvas1.parentNode.insertBefore(detail1, canvas1.nextSibling);
            }

            // --- TEMP/SPD/MAX/TASKS stat boxes -> VOL/TURN/DRAW/OPEN ---
            var statDivs = document.querySelectorAll("#mod_cpuinfo_innercontainer > div:last-child > div");
            var labels = ["VOL", "TURN", "DRAW", "OPEN"];
            var defaults = ["0.0%", "0.0x", "0.0%", "0"];
            for (var i = 0; i < Math.min(statDivs.length, 4); i++) {
                statDivs[i].style.cssText = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
                var h1 = statDivs[i].querySelector("h1");
                if (h1) {
                    h1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
                    if (h1.childNodes[0]) h1.childNodes[0].textContent = labels[i];
                }
                var iEl = statDivs[i].querySelector("i");
                if (iEl) {
                    iEl.style.cssText = "font-family:'Fira Mono',monospace;font-size:9px;color:#888;font-style:normal;";
                    iEl.innerText = defaults[i];
                }
            }

            // RAM -> CAPITAL (one line, nowrap, short format if needed)
            var ramH1 = $("#mod_ramwatcher_inner > h1");
            if (ramH1) {
                ramH1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
            }
            safeHTML(ramH1, "CAPITAL");

            // SWAP -> MARGIN
            var swapContainer = $id("mod_ramwatcher_swapcontainer");
            if (swapContainer) {
                swapContainer.style.cssText = (swapContainer.style.cssText || "") + ";white-space:nowrap;overflow:hidden;";
                var swapH1 = swapContainer.querySelector("h1");
                if (swapH1) {
                    swapH1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;";
                    safeText(swapH1, "MARGIN");
                }
                var swapTextEl = $id("mod_ramwatcher_swaptext");
                if (swapTextEl) {
                    swapTextEl.style.cssText = "font-family:'Fira Mono',monospace;font-size:9px;color:#e4e4e4;font-style:normal;";
                }
            }

            // Top processes -> Recent trades (header matches actual columns)
            var topH1 = $("#mod_toplist > h1");
            if (topH1) {
                topH1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
            }
            safeHTML(topH1, "RECENT TRADES<i style='font-family:inherit;font-size:9px;color:#888;font-style:normal;'>SYM | QTY | ENTRY | P&L</i>");
        } catch (e) { console.warn("ORBIT relabelLeft:", e); }
    }

    // -----------------------------------------------------------------------
    // Right Panel relabeling
    // -----------------------------------------------------------------------
    function relabelRight() {
        try {
            // "PANEL · NETWORK" -> "MACRO · GLOBE"
            var h = $("#mod_column_right > h3.title");
            safeHTML(h, "<p>MACRO</p><p>GLOBE</p>");

            // Network status -> Feed status
            var netH1 = $("#mod_netstat_inner > h1");
            if (netH1) netH1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
            safeHTML(netH1, "FEED STATUS<i style='font-family:inherit;font-size:9px;color:#888;font-style:normal;'>source: gdelt</i>");

            // State/IPv4/Ping labels
            var innerDivs = document.querySelectorAll("#mod_netstat_innercontainer > div");
            if (innerDivs[0]) safeText(innerDivs[0].querySelector("h1"), "STATE");
            if (innerDivs[1]) safeText(innerDivs[1].querySelector("h1"), "FEEDS");
            if (innerDivs[2]) safeText(innerDivs[2].querySelector("h1"), "LATENCY");
            if (innerDivs[0]) safeText(innerDivs[0].querySelector("h2"), "LIVE");
            if (innerDivs[1]) safeText(innerDivs[1].querySelector("h2"), "OK");

            // Globe labels
            var globeH1 = $("#mod_globe h1");
            safeHTML(globeH1, "EXPOSURE MAP<i>EVENT GEOGRAPHY</i>");
            var globeH2 = $("#mod_globe h2");
            safeHTML(globeH2, "LAST EVENT<i class='mod_globe_headerInfo'>0.0000, 0.0000</i>");
            // Cache the freshly-created element for pollEvents coordinate updates
            _cachedGlobeInfo = globeH2 ? globeH2.querySelector("i") : null;

            // Network traffic -> Event feed
            var connH1 = $("#mod_conninfo_innercontainer > h1");
            if (connH1) connH1.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;color:#ccc;white-space:nowrap;overflow:hidden;";
            safeHTML(connH1, "STATS");
            var connH2 = $("#mod_conninfo_innercontainer > h2");
            if (connH2) connH2.style.display = "none";

            // Add SCAN GDELT button right after the header
            var btnContainer = document.createElement("div");
            btnContainer.id = "orbit-scan-container";
            btnContainer.style.cssText = "text-align:center;padding:6px 0;";
            btnContainer.innerHTML = '<button id="orbit-scan-btn" style="background:#111;color:#5eead4;border:1px solid #5eead4;font-family:\'Fira Mono\',monospace;font-size:9px;padding:4px 14px;cursor:pointer;letter-spacing:0.08em;">SCAN GDELT</button>';
            var connContainer = document.getElementById("mod_conninfo_innercontainer");
            if (connContainer) {
                // Insert after the h1 header
                var connH1El = connContainer.querySelector("h1");
                if (connH1El && connH1El.nextSibling) {
                    connContainer.insertBefore(btnContainer, connH1El.nextSibling);
                } else {
                    connContainer.appendChild(btnContainer);
                }
            }

            // Hide the smoothie chart canvases permanently to free space for event cards
            var canvasTop = $id("mod_conninfo_canvas_top");
            var canvasBot = $id("mod_conninfo_canvas_bottom");
            if (canvasTop) canvasTop.style.display = "none";
            if (canvasBot) canvasBot.style.display = "none";
        } catch (e) { console.warn("ORBIT relabelRight:", e); }
    }

    // -----------------------------------------------------------------------
    // Bottom bar relabeling
    // -----------------------------------------------------------------------
    function relabelBottom() {
        try {
            // Filesystem header -> Event Feed
            var fsTitle = $("#filesystem > h3.title");
            if (fsTitle) safeHTML(fsTitle, "<p>EVENT</p><p>FEED</p>");

            // Replace fs_disp_container with event feed panel.
            // The original CSS forces display:grid with 8.5vh cells — override
            // to a simple block so our content fills the full 43vw × 25.5vh area.
            var fsDisp = $id("fs_disp_container");
            if (fsDisp) {
                fsDisp.style.cssText = "display:block !important;width:100%;height:100%;overflow-y:auto;padding:0;margin:0;position:relative;left:0;top:0;";

                // Override the child selector (div#fs_disp_container > *) that
                // applies cursor:pointer and fixed 8.5vh sizing from filesystem.css.
                // Without this, the orbit-bottom-events div gets a phantom pointer
                // zone and is clipped to an 8.5vh box.
                var overrideStyle = document.createElement("style");
                overrideStyle.textContent = "div#fs_disp_container > * { width: 100% !important; height: 100% !important; cursor: default !important; overflow-y: auto !important; animation: none !important; } div#fs_disp_container > *:active { animation: none !important; } div#fs_space_bar { display: none !important; }";
                document.head.appendChild(overrideStyle);

                fsDisp.innerHTML = '<div id="orbit-bottom-events" style="display:none;width:100%;height:100%;background:#000;overflow-y:auto;padding:6px 10px;font-family:\'Fira Mono\',monospace;font-size:10px;color:#888;box-sizing:border-box;"></div>';
                if (window.mods && window.mods.filesystem && window.mods.filesystem._timer) {
                    clearInterval(window.mods.filesystem._timer);
                }
            }

            // Status text
            var spaceH3 = $("#fs_space_bar h3");
            safeText(spaceH3, "ORBIT READY \u00b7 ALL FEEDS IDLE");

            // Hide the "Show disks" icon/exit display button
            var spaceH1 = $("#fs_space_bar h1");
            if (spaceH1) spaceH1.style.display = "none";
            var spaceProgress = $("#fs_space_bar progress");
            if (spaceProgress) spaceProgress.style.display = "none";
        } catch (e) { console.warn("ORBIT relabelBottom:", e); }
    }

    // -----------------------------------------------------------------------
    // Scrolling news ticker -- Bloomberg-style strip above the keyboard
    // -----------------------------------------------------------------------
    var _tickerStyleInjected = false;

    function injectTicker() {
        try {
            if ($id("orbit-ticker")) return;

            // Inject CSS keyframes once
            if (!_tickerStyleInjected) {
                var style = document.createElement("style");
                style.textContent =
                    "@keyframes orbit-ticker-scroll {" +
                    "  0%   { transform: translateX(100%); }" +
                    "  100% { transform: translateX(-100%); }" +
                    "}";
                document.head.appendChild(style);
                _tickerStyleInjected = true;
            }

            var ticker = document.createElement("div");
            ticker.id = "orbit-ticker";
            ticker.style.cssText =
                "height:16px;background:#000;overflow:hidden;white-space:nowrap;" +
                "font:9px 'Fira Mono',monospace;color:#666;letter-spacing:0.04em;" +
                "border-top:1px solid #111;border-bottom:1px solid #111;" +
                "position:fixed;top:0;left:0;right:0;z-index:9999;line-height:16px;";

            var inner = document.createElement("span");
            inner.id = "orbit-ticker-inner";
            inner.style.cssText =
                "display:inline-block;white-space:nowrap;padding-left:100%;" +
                "animation:orbit-ticker-scroll 30s linear infinite;";
            inner.textContent = "\u2014 ORBIT FEED IDLE \u2014";
            ticker.appendChild(inner);

            // Insert at the very top of the page (Bloomberg-style strip)
            if (document.body.firstChild) {
                document.body.insertBefore(ticker, document.body.firstChild);
            } else {
                document.body.appendChild(ticker);
            }
        } catch (e) { console.warn("ORBIT injectTicker:", e); }
    }

    function updateTicker(events) {
        var inner = $id("orbit-ticker-inner");
        if (!inner) return;
        if (!events || events.length === 0) {
            inner.textContent = "\u2014 ORBIT FEED IDLE \u2014";
            return;
        }

        var parts = [];
        var shown = events.slice(0, 20);
        for (var i = 0; i < shown.length; i++) {
            var ev = shown[i];
            var rel = (ev.relevance || 0).toFixed(2);
            var desc = (ev.description || "event").slice(0, 40);
            var dir = ev.implied_direction;
            var arrow = dir === "long" ? "\u25b2" : dir === "short" ? "\u25bc" : "\u2014";
            var sym = (ev.ticker || ev.symbol || "").toUpperCase();
            if (!sym) {
                if (ev.source_country === "TW" || ev.target_country === "TW") sym = "TSM";
                else if (ev.source_country === "US" || ev.target_country === "US") sym = "NVDA";
                else sym = "AAPL";
            }
            parts.push(arrow + " " + sym + " " + rel + " " + desc);
        }

        var html = "";
        for (var j = 0; j < parts.length; j++) {
            var p = parts[j];
            var arrowChar = p.charAt(0);
            var arrowColor = arrowChar === "\u25b2" ? "#5eead4" : arrowChar === "\u25bc" ? "#f87171" : "#555";
            html += '<span style="color:' + arrowColor + ';">' + arrowChar + '</span>' +
                '<span style="color:#777;">' + p.slice(1) + '</span>' +
                '  <span style="color:#333;">\u00b7\u00b7\u00b7</span>  ';
        }

        inner.innerHTML = html;

        // Adjust animation speed based on content length
        var charCount = parts.join("   ").length;
        var duration = Math.max(15, Math.round(charCount * 0.35));
        inner.style.animationDuration = duration + "s";
    }

    // -----------------------------------------------------------------------
    // Verdict strip -- injected ABOVE the chart tab bar
    // -----------------------------------------------------------------------
    function injectVerdictStrip() {
        try {
            var main = $id("main_shell");
            if (!main || $id("orbit-verdict-strip")) return;

            var strip = document.createElement("div");
            strip.id = "orbit-verdict-strip";
            strip.style.cssText = "height:36px;background:#000;border-bottom:1px solid #1f1f1f;font-family:'Fira Mono',monospace;font-size:10px;color:#666;display:flex;flex-direction:column;padding:0 8px;letter-spacing:0.04em;flex-shrink:0;overflow:hidden;";
            strip.innerHTML =
                '<div style="display:flex;align-items:center;justify-content:space-between;height:36px;flex-shrink:0;">' +
                    '<span id="orbit-verdict-text" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:\'Fira Mono\',monospace;font-size:10px;">[IDLE] NO ACTIVE VERDICT</span>' +
                    '<button id="orbit-execute-btn" style="background:#111;color:#666;border:1px solid #333;font-family:\'Fira Mono\',monospace;font-size:9px;padding:2px 10px;cursor:pointer;letter-spacing:0.08em;flex-shrink:0;margin-left:8px;" disabled>EXECUTE</button>' +
                '</div>';

            var tabs = $id("main_shell_tabs");
            if (tabs) main.insertBefore(strip, tabs);
            else {
                var title = main.querySelector("h3.title");
                if (title && title.nextSibling) main.insertBefore(strip, title.nextSibling);
                else main.prepend(strip);
            }
        } catch (e) { console.warn("ORBIT injectVerdictStrip:", e); }
    }

    // -----------------------------------------------------------------------
    // Scorecard strip -- injected at bottom of main_shell
    // -----------------------------------------------------------------------
    function injectScorecardStrip() {
        try {
            var main = $id("main_shell");
            if (!main || $id("orbit-scorecard-strip")) return;

            var strip = document.createElement("div");
            strip.id = "orbit-scorecard-strip";
            strip.style.cssText = "height:54px;background:#000;border-top:1px solid #1f1f1f;font-family:'Fira Mono',monospace;font-size:9px;color:#888;padding:3px 8px;letter-spacing:0.04em;line-height:1.6;flex-shrink:0;overflow:hidden;white-space:nowrap;";
            strip.innerHTML =
                '<div id="orbit-sc-backtest" style="color:#888;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:\'Fira Mono\',monospace;font-size:9px;"><span style="color:#ccc;">BACKTEST</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">6MO</span>  WIN --% \u00b7 -- TRADES</div>' +
                '<div id="orbit-sc-live" style="color:#888;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:\'Fira Mono\',monospace;font-size:9px;"><span style="color:#ccc;">LIVE</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">NOW</span>  WIN --% (n=0)</div>' +
                '<div id="orbit-sc-session" style="color:#888;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:\'Fira Mono\',monospace;font-size:9px;"><span style="color:#ccc;">SESSION</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">ROI</span> +$0 \u00b7 0 CLOSED \u00b7 0 OPEN</div>';

            main.appendChild(strip);
        } catch (e) { console.warn("ORBIT injectScorecardStrip:", e); }
    }

    // -----------------------------------------------------------------------
    // Live data polling
    // -----------------------------------------------------------------------
    var currentTicker = "AAPL";
    var currentDirection = null;   // "long" or "short" from last verdict
    var currentPrice = null;       // latest bar close price
    var allTickers = ["AAPL", "NVDA", "TSM"];
    var _cachedGlobeInfo = null;   // cached reference to i.mod_globe_headerInfo

    // -----------------------------------------------------------------------
    // Sound effect state — debounce to max 1 sound per 3 seconds
    // -----------------------------------------------------------------------
    var lastSoundTime = 0;
    var lastVerdictClass = null;       // tracks previous verdict to detect flips
    var lastEventCount = -1;           // tracks event count to detect new arrivals
    var lastScorecardCorrect = -1;     // tracks correct-outcome count
    var _soundMuted = false;

    function playSound(name) {
        if (_soundMuted) return;
        var now = Date.now();
        if (now - lastSoundTime < 3000) return;
        try {
            if (window.audioManager && window.audioManager[name]) {
                window.audioManager[name].play();
                lastSoundTime = now;
            }
        } catch (e) { /* sound play failed, ignore */ }
    }

    // Store latest verdict data so the execute modal can use it
    var latestVerdict = {
        ticker: null, direction: null, price: null,
        verdict_class: null, relevance_score: null, verdict_object: null
    };

    // Resolve top_event: if it is a raw GDELT ID, fetch a real description
    // from the events endpoint; otherwise show a generic label.
    async function resolveTopEvent(meta, ticker) {
        var raw = meta.top_event || "";
        if (!raw || /^GDELT event/i.test(raw)) {
            try {
                var evts = await api("/api/events/" + ticker);
                if (evts && evts.length > 0 && evts[0].description) {
                    return evts[0].description.slice(0, 50);
                }
            } catch (e) { /* fall through */ }
            return "GEOPOLITICAL EVENT DETECTED";
        }
        return raw.slice(0, 50);
    }

    async function pollVerdict() {
        var strip = $id("orbit-verdict-text");
        var btn = $id("orbit-execute-btn");
        if (!strip) return;

        // Poll all 3 tickers and pick the most actionable verdict
        var bestData = null;
        var bestTicker = null;
        var bestPriority = -1;

        for (var t = 0; t < allTickers.length; t++) {
            var tk = allTickers[t];
            var d = await api("/api/verdict/" + tk);
            if (!d) continue;
            var vc2 = (d.verdict_class || "").toLowerCase();
            var pri = 0;
            if (vc2 === "strong_buy" || vc2 === "strong_sell") pri = 3;
            else if (vc2 === "buy" || vc2 === "sell") pri = 2;
            else if (vc2 === "hold") pri = 1;
            if (pri > bestPriority ||
                (pri === bestPriority && (d.relevance_score || 0) > ((bestData && bestData.relevance_score) || 0))) {
                bestData = d; bestTicker = tk; bestPriority = pri;
            }
        }

        // Fall back to the active tab ticker if nothing found
        if (!bestData) {
            bestData = await api("/api/verdict/" + currentTicker);
            bestTicker = currentTicker;
        }
        if (!bestData) return;

        var displayTicker = bestTicker;
        var vc = (bestData.verdict_class || "").toLowerCase();
        var dir = bestData.direction === "long" ? "\u25b2" : bestData.direction === "short" ? "\u25bc" : "\u2014";
        var score = (bestData.relevance_score || 0).toFixed(2);
        var meta = bestData.verdict_object || {};

        // Persist for the execute modal
        currentDirection = bestData.direction || null;
        latestVerdict.ticker = displayTicker;
        latestVerdict.direction = bestData.direction || null;
        latestVerdict.verdict_class = vc;
        latestVerdict.relevance_score = bestData.relevance_score || 0;
        latestVerdict.verdict_object = meta;

        // Fetch latest price
        try {
            var bars = await api("/api/bars/" + displayTicker);
            if (bars && bars.length > 0) {
                currentPrice = bars[bars.length - 1].close || bars[bars.length - 1].c || null;
                latestVerdict.price = currentPrice;
            }
        } catch (e) { /* price stays null */ }

        var isAct = (vc === "strong_buy" || vc === "buy" || vc === "sell" || vc === "strong_sell");
        var isWait = (vc === "hold");
        var stripEl = $id("orbit-verdict-strip");

        // Sound: detect verdict class flips
        var prevWasAct = (lastVerdictClass === "strong_buy" || lastVerdictClass === "buy" ||
                          lastVerdictClass === "sell" || lastVerdictClass === "strong_sell");
        if (lastVerdictClass !== null && vc !== lastVerdictClass) {
            if (isAct && !prevWasAct) {
                playSound("alarm");   // flipped to ACT from non-ACT
            } else if (isWait && prevWasAct) {
                playSound("info");    // flipped to WAIT from ACT
            }
        }
        lastVerdictClass = vc;

        if (isAct) {
            // --- ACT: prominent, eye-catching ---------------------------------
            var color = (vc === "buy" || vc === "strong_buy") ? "#5eead4" : "#f87171";
            var topEvent = await resolveTopEvent(meta, displayTicker);

            var midParts = ["SCORE " + score];
            if (meta.exposure_code)  midParts.push("EXPOSURE " + meta.exposure_code + " " + (meta.exposure_weight || "--"));
            if (meta.hit_rate)       midParts.push("HIT " + meta.hit_rate);
            if (meta.n_analogs)      midParts.push("n=" + meta.n_analogs);

            if (stripEl) {
                stripEl.style.background = (vc === "buy" || vc === "strong_buy")
                    ? "rgba(94,234,212,0.06)" : "rgba(248,113,113,0.06)";
                stripEl.style.borderBottom = "1px solid " + color + "44";
            }

            strip.innerHTML =
                '<span style="color:' + color + ';font-weight:bold;text-shadow:0 0 6px ' + color + '44;">' +
                '[ACT ' + dir + ' ' + displayTicker + ']</span>' +
                '  <span style="color:#aaa;">' + midParts.join(" \u00b7 ") + '</span>';

            if (btn) {
                btn.disabled = false;
                btn.style.color = "#000"; btn.style.background = color;
                btn.style.borderColor = color; btn.style.fontWeight = "bold";
                btn.style.display = ""; btn.textContent = "EXECUTE " + dir + " " + displayTicker;
            }

        } else if (isWait) {
            // --- WAIT: yellow text, button disabled ---------------------------
            var contraCount = meta.contradicting_count || "0";
            var contraText = contraCount === "1"
                ? "1 contradicting signal"
                : contraCount + " contradicting signals";

            if (stripEl) {
                stripEl.style.background = "#000";
                stripEl.style.borderBottom = "1px solid #1f1f1f";
            }

            strip.innerHTML =
                '<span style="color:#facc15;">[WAIT \u2014 ' + displayTicker + ']</span>' +
                '  <span style="color:#888;">monitoring \u00b7 ' + contraText + '</span>';

            if (btn) {
                btn.disabled = true; btn.style.color = "#555"; btn.style.background = "#111";
                btn.style.borderColor = "#333"; btn.style.fontWeight = "normal";
                btn.style.display = ""; btn.textContent = "EXECUTE";
            }

        } else {
            // --- IGNORE: dim gray, no button ----------------------------------
            if (stripEl) {
                stripEl.style.background = "#000";
                stripEl.style.borderBottom = "1px solid #1f1f1f";
            }

            strip.innerHTML =
                '<span style="color:#555;">[IGNORE \u2014 ' + displayTicker + ']</span>' +
                '  <span style="color:#444;">no material events above 0.30</span>';

            if (btn) {
                btn.disabled = true; btn.style.display = "none";
            }
        }

        // --- Narrative: push a VERDICT line when verdict class changes for a ticker ---
        var prevClass = _lastVerdictClass[displayTicker] || "";
        if (vc && vc !== prevClass) {
            _lastVerdictClass[displayTicker] = vc;
            var dirLabel = (bestData.direction === "long") ? "LONG" : (bestData.direction === "short") ? "SHORT" : "--";
            var vcLabel = vc.toUpperCase().replace("_", " ");
            var nParts = ["VERDICT: " + vcLabel + " " + dirLabel + " " + displayTicker];
            if (meta.exposure_code) nParts.push("TW " + (meta.exposure_weight || "--"));
            if (meta.n_analogs) nParts.push(meta.n_analogs + " analogs");
            if (meta.hit_rate) nParts.push(meta.hit_rate + " hit");
            narrativePush(nParts.join(" \u00b7 "));
        }
    }

    async function pollPositions() {
        var positions = await api("/api/portfolio/positions");
        if (!positions) return;

        // Filter out ghost trades with 0 or falsy size_shares
        var activePositions = positions.filter(function (p) {
            return p.size_shares && p.size_shares !== 0;
        });

        safeText($id("mod_cpuinfo_usagecounter1"), activePositions.length + " OPEN");

        var totalPnl = 0;
        activePositions.forEach(function (p) { totalPnl += (p.unrealized_pnl || 0); });
        var shortTotalPnl = totalPnl >= 0 ? "+$" + Math.abs(totalPnl).toFixed(0) : "-$" + Math.abs(totalPnl).toFixed(0);
        safeText($id("mod_cpuinfo_usagecounter0"), shortTotalPnl);

        // --- Narrative: push P&L line when change exceeds $100 ---
        if (_lastTotalPnl !== null && Math.abs(totalPnl - _lastTotalPnl) > 100) {
            var pnlParts = [];
            activePositions.forEach(function (p) {
                var pPnl = p.unrealized_pnl || 0;
                var pTicker = p.ticker || "??";
                var pSign = pPnl >= 0 ? "+" : "";
                pnlParts.push(pTicker + " " + pSign + "$" + Math.abs(pPnl).toFixed(0));
            });
            var correctStr = totalPnl > 0 ? "CORRECT \u2713" : "WRONG \u2717";
            narrativePush("P&L " + formatPnl(totalPnl) + " \u00b7 " + pnlParts.join(" \u00b7 ") + " \u00b7 " + correctStr);
        }
        _lastTotalPnl = totalPnl;

        var summary = await api("/api/portfolio/summary");
        if (summary) {
            var deployed = summary.capital_deployed || 0;

            // Fix 3: Update capital dot grid to reflect deployment percentage
            updateCapitalDots(deployed);

            // Update stat boxes: VOL / TURN / DRAW / OPEN
            var volVal = (summary.volatility != null) ? (summary.volatility * 100).toFixed(1) + "%" : "0.0%";
            var turnVal = (summary.turnover != null) ? summary.turnover.toFixed(1) + "x" : "0.0x";
            var drawVal = (summary.drawdown != null) ? (summary.drawdown * 100).toFixed(1) + "%" : "0.0%";
            safeText($id("mod_cpuinfo_temp"), volVal);
            safeText($id("mod_cpuinfo_speed_min"), turnVal);
            safeText($id("mod_cpuinfo_speed_max"), drawVal);
            safeText($id("mod_cpuinfo_tasks"), String(activePositions.length));

            // Task 2A: Hide stat box container when all values are zero
            var statContainer = document.querySelector("#mod_cpuinfo_innercontainer > div:last-child");
            if (statContainer) {
                var allZero = (volVal === "0.0%" && turnVal === "0.0x" && drawVal === "0.0%" && activePositions.length === 0);
                statContainer.style.display = allZero ? "none" : "";
            }
        }

        // Fix 4: Update position detail panels replacing the hidden canvases
        // Format: AAPL 45 @ $197.80 -> $263.36 (+$2,950.20)
        var longs = [];
        var shorts = [];
        activePositions.forEach(function (p) {
            if (p.direction === "short") shorts.push(p);
            else longs.push(p);
        });

        function formatPosLine(p) {
            var pnl = p.unrealized_pnl || 0;
            var c = pnl >= 0 ? "#5eead4" : "#f87171";
            var ticker = (p.ticker || "--").toString();
            var qty = String(p.size_shares || p.qty || "--");
            var entry = (p.entry_price != null) ? Number(p.entry_price).toFixed(2) : "--";
            var pnlVal = Math.abs(pnl).toFixed(0);
            var pnlStr = (pnl >= 0 ? "+" : "-") + pnlVal;
            return '<div style="font:9px \'Fira Mono\',monospace;color:#888;white-space:nowrap;line-height:1.6;">' +
                '<span style="color:#ccc;display:inline-block;width:40px;">' + ticker + '</span>' +
                '<span style="display:inline-block;width:30px;text-align:right;">' + qty + '</span>' +
                '<span style="color:#555;"> @</span>' +
                '<span style="display:inline-block;width:55px;text-align:right;">' + entry + '</span>' +
                ' <span style="color:' + c + ';display:inline-block;width:50px;text-align:right;">' + pnlStr + '</span></div>';
        }

        var detail0 = $id("orbit-pos-detail-0");
        if (detail0) {
            if (longs.length === 0) {
                detail0.innerHTML = '<span style="color:#555;font-size:9px;">NO LONG POSITIONS</span>';
            } else {
                detail0.innerHTML = longs.map(formatPosLine).join("");
            }
        }
        var detail1 = $id("orbit-pos-detail-1");
        if (detail1) {
            if (shorts.length === 0) {
                detail1.innerHTML = '<span style="color:#555;font-size:9px;">NO SHORT POSITIONS</span>';
            } else {
                detail1.innerHTML = shorts.map(formatPosLine).join("");
            }
        }

        // Populate Recent Trades table with open positions
        // Columns: ticker | size | entry | P&L
        // Filter out ghost trades with 0 or falsy size_shares
        var table = $id("mod_toplist_table");
        if (table) {
            table.innerHTML = "";
            var tdBase = "font-family:'Fira Mono',monospace;font-size:9px;padding:1px 4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
            activePositions.slice(0, 3).forEach(function (p) {
                var tr = document.createElement("tr");
                var pnl = p.unrealized_pnl || 0;
                var pnlColor = pnl >= 0 ? "#5eead4" : "#f87171";
                var price = (p.entry_price != null) ? "$" + Number(p.entry_price).toFixed(2) : "--";
                var size = p.size_shares || p.qty || "--";
                tr.innerHTML =
                    '<td style="' + tdBase + 'width:40px;color:#ccc;">' + (p.ticker || "--") + '</td>' +
                    '<td style="' + tdBase + 'width:30px;text-align:right;color:#888;">' + size + '</td>' +
                    '<td style="' + tdBase + 'width:55px;text-align:right;color:#666;">' + price + '</td>' +
                    '<td style="' + tdBase + 'width:60px;text-align:right;color:' + pnlColor + ';">' + formatPnl(pnl) + '</td>';
                table.appendChild(tr);
            });
        }
    }

    function safeFix(val, decimals) {
        if (val == null || typeof val !== "number" || isNaN(val)) return "--";
        return val.toFixed(decimals);
    }

    // Fix 1 & 6: Aggregated scorecard across all tickers with fallbacks
    async function pollScorecard() {
        var bt = await api("/api/scorecard/backtest");
        if (bt && bt.length > 0) {
            var totalTrades = 0;
            var weightedWinSum = 0;
            var totalWeight = 0;
            var sharpeSum = 0;
            var sharpeCount = 0;
            var avgReturnSum = 0;
            var avgReturnCount = 0;

            bt.forEach(function (r) {
                var trades = r.total_trades || 0;
                totalTrades += trades;
                if (r.win_rate != null && typeof r.win_rate === "number" && !isNaN(r.win_rate)) {
                    weightedWinSum += r.win_rate * trades;
                    totalWeight += trades;
                }
                if (r.sharpe != null && typeof r.sharpe === "number" && !isNaN(r.sharpe)) {
                    sharpeSum += r.sharpe;
                    sharpeCount++;
                }
                if (r.avg_return != null && typeof r.avg_return === "number" && !isNaN(r.avg_return)) {
                    avgReturnSum += r.avg_return;
                    avgReturnCount++;
                }
            });

            var winStr = totalWeight > 0 ? (weightedWinSum / totalWeight).toFixed(1) : "--";
            var sharpeStr = sharpeCount > 0 ? (sharpeSum / sharpeCount).toFixed(2) : "N/A";
            var avgRetStr = avgReturnCount > 0 ? (avgReturnSum / avgReturnCount).toFixed(1) : "--";

            // Wilson confidence interval for aggregate backtest win rate
            var btCiStr = "";
            if (totalWeight > 0 && totalTrades > 0) {
                var btP = (weightedWinSum / totalWeight) / 100;
                var btN = totalTrades;
                var btZ = 1.96;
                var btCenter = (btP + btZ * btZ / (2 * btN)) / (1 + btZ * btZ / btN);
                var btMargin = btZ * Math.sqrt((btP * (1 - btP) + btZ * btZ / (4 * btN)) / btN) / (1 + btZ * btZ / btN);
                var btLower = Math.max(0, btCenter - btMargin);
                var btUpper = Math.min(1, btCenter + btMargin);
                btCiStr = " [" + Math.round(btLower * 100) + "-" + Math.round(btUpper * 100) + "]";
            }

            // Format: BACKTEST · 6MO  WIN 57.1% [52-62] · 316 TRADES
            safeHTML($id("orbit-sc-backtest"),
                '<span style="color:#ccc;">BACKTEST</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">6MO</span>  WIN ' + winStr + '%' + btCiStr + ' \u00b7 ' + totalTrades + ' TRADES');
        }

        var live = await api("/api/scorecard/live");
        if (live && live.length > 0) {
            // Sound: detect new correct outcomes in live scorecard
            var correctCount = 0;
            live.forEach(function (l) { correctCount += (l.correct_outcomes || l.total_trades || 0); });
            if (lastScorecardCorrect >= 0 && correctCount > lastScorecardCorrect) {
                playSound("folder");
            }
            lastScorecardCorrect = correctCount;

            var lTotalTrades = 0;
            var lWeightedWinSum = 0;
            var lTotalWeight = 0;
            var lSharpeSum = 0;
            var lSharpeCount = 0;
            var lTotalWins = 0;

            live.forEach(function (l) {
                var trades = l.total_trades || 0;
                lTotalTrades += trades;
                lTotalWins += (l.wins || 0);
                if (l.win_rate != null && typeof l.win_rate === "number" && !isNaN(l.win_rate)) {
                    lWeightedWinSum += l.win_rate * trades;
                    lTotalWeight += trades;
                }
                if (l.sharpe != null && typeof l.sharpe === "number" && !isNaN(l.sharpe)) {
                    lSharpeSum += l.sharpe;
                    lSharpeCount++;
                }
            });

            // Fix 1: Fallback handling for sharpe and avg_return
            var lWinStr = lTotalWeight > 0 ? (lWeightedWinSum / lTotalWeight).toFixed(1) : "--";
            var lSharpeStr = lSharpeCount > 0 ? (lSharpeSum / lSharpeCount).toFixed(2) : "N/A";

            // Wilson CI for live: use backend fields if present, else show "early"
            var liveCiStr = "";
            var hasLiveCi = false;
            live.forEach(function (l) {
                if (l.wilson_lower != null && l.wilson_upper != null) hasLiveCi = true;
            });
            if (hasLiveCi && lTotalTrades > 0) {
                // Compute aggregate Wilson CI client-side from combined wins/trades
                var lP = lTotalWins / lTotalTrades;
                var lZ = 1.96;
                var lCenter = (lP + lZ * lZ / (2 * lTotalTrades)) / (1 + lZ * lZ / lTotalTrades);
                var lMargin = lZ * Math.sqrt((lP * (1 - lP) + lZ * lZ / (4 * lTotalTrades)) / lTotalTrades) / (1 + lZ * lZ / lTotalTrades);
                var lLower = Math.max(0, lCenter - lMargin);
                var lUpper = Math.min(1, lCenter + lMargin);
                liveCiStr = " [" + Math.round(lLower * 100) + "-" + Math.round(lUpper * 100) + "]";
            } else if (lTotalTrades > 0) {
                liveCiStr = " (n=" + lTotalTrades + " early)";
            }

            // Format: LIVE · NOW  WIN 60.0% (n=5 early)
            safeHTML($id("orbit-sc-live"),
                '<span style="color:#ccc;">LIVE</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">NOW</span>  WIN ' + lWinStr + '%' + liveCiStr);
        } else {
            // Show the live line even with no data
            safeHTML($id("orbit-sc-live"), '<span style="color:#ccc;">LIVE</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">NOW</span>  WIN --% (n=0)');
        }
    }

    // Fix 2: Poll session data from portfolio summary for the session row
    async function pollSession() {
        var summary = await api("/api/portfolio/summary");
        var positions = await api("/api/portfolio/positions");
        var closedCount = 0;
        var openCount = 0;
        var realizedPnl = 0;

        if (summary) {
            realizedPnl = summary.realized_pnl || 0;
            closedCount = summary.closed_positions || 0;
        }
        if (positions) {
            openCount = positions.length;
        }

        // Short P&L: +$449 instead of +$449.00
        var shortPnl = realizedPnl >= 0 ? "+$" + Math.abs(realizedPnl).toFixed(0) : "-$" + Math.abs(realizedPnl).toFixed(0);

        // Format: SESSION · ROI +$449 · 5 CLOSED · 4 OPEN
        safeHTML($id("orbit-sc-session"),
            '<span style="color:#ccc;">SESSION</span> <span style="color:#555;">\u00b7</span> <span style="color:#ccc;">ROI</span> ' + shortPnl + ' \u00b7 ' + closedCount + ' CLOSED \u00b7 ' + openCount + ' OPEN');
    }

    async function pollEvents() {
        var events = await api("/api/events/recent");
        if (!events) events = [];

        // --- Fix 3 & 4: Fetch verdict top_event and prepend as high-relevance card ---
        var verdictTopEvent = null;
        var verdictActCount = 0;
        var verdictWaitCount = 0;
        for (var ti = 0; ti < allTickers.length; ti++) {
            try {
                var vd = await api("/api/verdict/" + allTickers[ti]);
                if (vd) {
                    var vc = (vd.verdict_class || "").toLowerCase();
                    var isVAct = (vc === "strong_buy" || vc === "buy" || vc === "sell" || vc === "strong_sell");
                    var isVWait = (vc === "hold");
                    if (isVAct) verdictActCount++;
                    else if (isVWait) verdictWaitCount++;
                    // Capture the best verdict's top_event as a synthetic event card
                    if (isVAct && !verdictTopEvent && vd.verdict_object) {
                        var topEvt = vd.verdict_object.top_event || vd.verdict_object.description || null;
                        if (topEvt) {
                            verdictTopEvent = {
                                description: topEvt,
                                relevance: vd.relevance_score || 0.75,
                                implied_direction: vd.direction || null,
                                source_country: vd.verdict_object.source_country || null,
                                target_country: vd.verdict_object.target_country || null,
                                lat: vd.verdict_object.lat || null,
                                lon: vd.verdict_object.lon || null,
                                created_at: null,
                                _synthetic: true
                            };
                        }
                    }
                }
            } catch (e) { /* skip ticker */ }
        }

        // Count events from the feed
        var actCount = verdictActCount, waitCount = verdictWaitCount;
        var highRelCount = 0;
        events.forEach(function (e) {
            if (e.relevance >= 0.55) { actCount++; highRelCount++; }
            else if (e.relevance >= 0.30) waitCount++;
        });

        // Sound: new high-relevance event arrived (>0.55)
        if (lastEventCount >= 0 && highRelCount > lastEventCount) {
            playSound("scan");
        }
        lastEventCount = highRelCount;

        // conninfo area is now STATS panel — don't overwrite it here

        // Build display list: prepend verdict top_event, then feed events
        var displayEvents = [];
        if (verdictTopEvent) displayEvents.push(verdictTopEvent);
        events.forEach(function (ev) { displayEvents.push(ev); });

        // --- Narrative: push GDELT line for high-relevance unseen events ---
        displayEvents.forEach(function (ev) {
            if ((ev.relevance || 0) >= 0.55) {
                var desc = (ev.description || "event").slice(0, 45);
                var evKey = desc.replace(/\s+/g, " ").toLowerCase();
                if (!_seenEventDescs[evKey]) {
                    _seenEventDescs[evKey] = true;
                    var evDir2 = ev.implied_direction === "long" ? "\u25b2" : ev.implied_direction === "short" ? "\u25bc" : "";
                    var countries2 = "";
                    if (ev.source_country || ev.target_country) {
                        countries2 = " " + (ev.source_country || "??") + "\u2192" + (ev.target_country || "??");
                    }
                    narrativePush("GDELT: " + desc + " \u2192 SCORE " + (ev.relevance || 0).toFixed(2) + countries2 + " " + evDir2);
                }
            }
        });
        // Cap seen-events map to prevent unbounded growth
        var seenKeys = Object.keys(_seenEventDescs);
        if (seenKeys.length > 100) {
            for (var sk = 0; sk < seenKeys.length - 50; sk++) {
                delete _seenEventDescs[seenKeys[sk]];
            }
        }

        // Hide smoothie canvases in conninfo (stats panel owns this area now)
        var connCanvases = document.querySelectorAll("#mod_conninfo_innercontainer canvas");
        if (connCanvases) connCanvases.forEach(function (c) { c.style.display = "none"; });

        // --- Fix 2: Update globe last event coords from highest-relevance event ---
        var bestEvent = null;
        var bestRelevance = -1;
        displayEvents.forEach(function (ev) {
            if ((ev.relevance || 0) > bestRelevance && (ev.lat || ev.lon)) {
                bestRelevance = ev.relevance || 0;
                bestEvent = ev;
            }
        });
        // Fallback: use the first event with any lat/lon
        if (!bestEvent) {
            for (var ei = 0; ei < displayEvents.length; ei++) {
                if (displayEvents[ei].lat || displayEvents[ei].lon) {
                    bestEvent = displayEvents[ei];
                    break;
                }
            }
        }
        if (bestEvent) {
            var evLat = bestEvent.lat || 0;
            var evLon = bestEvent.lon || 0;
            // Use cached reference; re-query if stale or missing from DOM
            if (!_cachedGlobeInfo || !_cachedGlobeInfo.parentNode) {
                _cachedGlobeInfo = $("i.mod_globe_headerInfo");
            }
            // Fallback: try broader selector if class-based lookup fails
            if (!_cachedGlobeInfo) {
                var globeH2 = $("#mod_globe h2");
                if (globeH2) {
                    _cachedGlobeInfo = globeH2.querySelector("i");
                }
            }
            safeText(_cachedGlobeInfo, evLat.toFixed(4) + ", " + evLon.toFixed(4));

            // Globe rotation: only nudge on genuinely NEW events (not every poll)
            // Let the globe spin freely otherwise via its built-in dayLength rotation
            if ((evLat !== 0 || evLon !== 0) && window.mods && window.mods.globe && window.mods.globe.globe) {
                var evKey = evLat.toFixed(2) + "," + evLon.toFixed(2);
                if (evKey !== window._lastGlobeEventKey) {
                    window._lastGlobeEventKey = evKey;
                    // Gentle nudge toward event longitude (don't snap)
                    var targetAngle = (-evLon * Math.PI / 180) + Math.PI;
                    var current = window.mods.globe.globe.cameraAngle || 0;
                    // Interpolate 30% toward target so it doesn't jerk
                    window.mods.globe.globe.cameraAngle = current + (targetAngle - current) * 0.3;
                }
            }
        }

        // Update scrolling ticker with scored events
        updateTicker(displayEvents);

        // --- Supply chain visualization: trigger on high-relevance events ---
        // Check verdict-based triggers (ticker known from verdict loop)
        for (var sci = 0; sci < allTickers.length; sci++) {
            try {
                var scTicker = allTickers[sci];
                var scVerdict = await api("/api/verdict/" + scTicker);
                if (!scVerdict) continue;
                var scVc = (scVerdict.verdict_class || "").toLowerCase();
                var scRel = scVerdict.relevance_score || 0;
                var scIsAct = (scVc === "strong_buy" || scVc === "buy" || scVc === "sell" || scVc === "strong_sell");
                if (scIsAct && scRel > 0.55) {
                    var scMeta = scVerdict.verdict_object || {};
                    var scKey = scTicker + ":" + (scMeta.top_event || scVc) + ":" + scRel.toFixed(2);
                    if (!_seenSupplyChainEvents[scKey]) {
                        _seenSupplyChainEvents[scKey] = Date.now();
                        highlightSupplyChain(scTicker, scMeta.lat || null, scMeta.lon || null);
                        break; // one chain at a time
                    }
                }
            } catch (e) {}
        }

        // Also check feed events for high relevance
        displayEvents.forEach(function (ev) {
            if ((ev.relevance || 0) > 0.55 && ev.description) {
                var evKey = (ev.description || "").slice(0, 30) + ":" + (ev.relevance || 0).toFixed(2);
                if (!_seenSupplyChainEvents[evKey]) {
                    _seenSupplyChainEvents[evKey] = Date.now();
                    // Match event to a ticker based on country or default to current
                    var evTicker = currentTicker;
                    if (ev.source_country === "TW" || ev.target_country === "TW") {
                        evTicker = "TSM";
                    }
                    highlightSupplyChain(evTicker, ev.lat || null, ev.lon || null);
                }
            }
        });

        // Prune old dedup keys (older than 60 seconds) to allow re-trigger
        var scNow = Date.now();
        Object.keys(_seenSupplyChainEvents).forEach(function (k) {
            if (scNow - _seenSupplyChainEvents[k] > 60000) {
                delete _seenSupplyChainEvents[k];
            }
        });
    }

    // -----------------------------------------------------------------------
    // Event Heatmap — 26 cells for 15-min windows of the trading day
    // -----------------------------------------------------------------------
    // -----------------------------------------------------------------------
    // Bottom event feed — shows scored events in the large area left of keyboard
    // This gives events much more room than the cramped right panel
    // -----------------------------------------------------------------------
    var _feedFirstLoad = true;
    var _typewriterActive = false;

    async function typewriterFeed(container, rows) {
        if (_typewriterActive) return;  // don't re-animate on poll refresh
        _typewriterActive = true;

        for (var ri = 0; ri < rows.length; ri++) {
            var row = rows[ri];
            var rowDiv = document.createElement("div");
            rowDiv.style.cssText = row.style;
            rowDiv.setAttribute("data-ts", row.timestamp || "");
            rowDiv.setAttribute("data-ticker", row.ticker || "");
            rowDiv.setAttribute("data-lat", row.lat || "");
            rowDiv.setAttribute("data-lon", row.lon || "");
            rowDiv.setAttribute("data-rel", row.rel || "");
            rowDiv.setAttribute("data-desc", row.rawDesc || "");
            rowDiv.setAttribute("data-dir", row.direction || "long");
            rowDiv.style.cursor = "pointer";

            // Score + ticker appear instantly
            var prefix = document.createElement("span");
            prefix.innerHTML = row.prefix;  // colored score + ticker
            rowDiv.appendChild(prefix);

            // Description types in character by character
            var descSpan = document.createElement("span");
            descSpan.style.cssText = "color:#888;font-size:11px;";
            rowDiv.appendChild(descSpan);

            // Blinking cursor
            var cursor = document.createElement("span");
            cursor.style.cssText = "color:#5eead4;animation:blink 0.5s step-end infinite;";
            cursor.innerText = "\u2588";
            rowDiv.appendChild(cursor);

            container.appendChild(rowDiv);

            // Type the description
            var desc = row.description;
            for (var ci = 0; ci < desc.length; ci++) {
                descSpan.innerText += desc[ci];
                await new Promise(function(r) { setTimeout(r, 25); });  // 25ms per char
            }

            // Remove cursor, add time
            cursor.remove();
            if (row.timeText) {
                var timeSpan = document.createElement("span");
                timeSpan.style.cssText = "color:#555;font-size:9px;float:right;";
                timeSpan.innerText = row.timeText;
                rowDiv.appendChild(timeSpan);
            }

            // Pause between rows
            await new Promise(function(r) { setTimeout(r, 200); });
        }
        _typewriterActive = false;
    }

    async function pollBottomEvents() {
        var container = $id("orbit-bottom-events");
        if (!container) return;

        // Don't overwrite while typewriter is animating
        if (_typewriterActive) return;

        var events = await api("/api/events/" + currentTicker);
        if (!events || events.length === 0) {
            // Fallback to recent across all tickers
            events = await api("/api/events/recent");
        }
        if (!events || events.length === 0) return;

        // Show up to 8 events with more detail (we have room here)
        var shown = events.slice(0, 8);

        // Build row data objects
        var rows = [];
        for (var idx = 0; idx < shown.length; idx++) {
            var ev = shown[idx];
            var dir = ev.implied_direction === "long" ? "\u25b2" : ev.implied_direction === "short" ? "\u25bc" : "\u2014";
            var rel = (ev.relevance || 0).toFixed(2);
            var scoreColor = ev.relevance >= 0.55 ? "#5eead4" : ev.relevance >= 0.30 ? "#facc15" : "#555";
            var desc = (ev.description || "").slice(0, 55);
            var ticker = ev.ticker || currentTicker;
            var countries = "";
            if (ev.countries && ev.countries.length > 0) {
                countries = " [" + ev.countries.slice(0, 3).join(",") + "]";
            }
            var ts = "";
            if (ev.timestamp) {
                var d = new Date(ev.timestamp);
                var diff = (Date.now() - d.getTime()) / 1000;
                if (diff < 60) ts = Math.floor(diff) + "s";
                else if (diff < 3600) ts = Math.floor(diff / 60) + "m";
                else ts = Math.floor(diff / 3600) + "h";
            }

            var rowBg = idx === 0 ? "background:#111;" : "";
            var rowStyle = "padding:4px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" +
                "border-bottom:1px solid transparent;border-image:linear-gradient(to right, #5eead4, transparent) 1;" +
                rowBg;

            var prefixHtml = '<span style="color:' + scoreColor + ';font-size:14px;font-weight:bold;">' + dir + ' ' + rel + '</span>' +
                ' <span style="color:#e4e4e4;font-size:12px;">' + ticker + '</span> ';

            var descWithCountries = desc + countries;

            rows.push({
                prefix: prefixHtml,
                description: descWithCountries,
                timeText: ts,
                style: rowStyle,
                timestamp: ev.timestamp ? Math.floor(new Date(ev.timestamp).getTime() / 1000) : 0,
                ticker: ev.ticker || currentTicker,
                lat: ev.lat || "",
                lon: ev.lon || "",
                rel: (ev.relevance || 0).toFixed(2),
                rawDesc: (ev.description || "").slice(0, 55),
                direction: ev.implied_direction || "long"
            });
        }

        if (_feedFirstLoad) {
            // First call after SCAN: use typewriter animation
            _feedFirstLoad = false;

            // Preserve the EVENT FEED header
            var header = container.querySelector("div:first-child");
            var headerHtml = header ? header.outerHTML : "";
            container.innerHTML = headerHtml;

            typewriterFeed(container, rows).then(function () {
                // After typewriter finishes, append summary line
                var actCount = 0, waitCount = 0;
                events.forEach(function (e) {
                    if (e.relevance >= 0.55) actCount++;
                    else if (e.relevance >= 0.30) waitCount++;
                });
                var summaryDiv = document.createElement("div");
                summaryDiv.style.cssText = "padding:4px 0;color:#555;font-size:9px;margin-top:4px;";
                summaryDiv.innerHTML = 'SHOWING ' + shown.length + ' OF ' + events.length + ' \u00b7 ' +
                    '<span style="color:#5eead4">ACT ' + actCount + '</span> \u00b7 ' +
                    '<span style="color:#facc15">WAIT ' + waitCount + '</span>';
                container.appendChild(summaryDiv);
            });
        } else {
            // Subsequent polls: update innerHTML directly (no re-animation)
            var html = "";

            // Preserve the EVENT FEED header
            var hdr = container.querySelector("div:first-child");
            if (hdr) html = hdr.outerHTML;

            for (var ri = 0; ri < rows.length; ri++) {
                var row = rows[ri];
                html += '<div style="' + row.style + 'cursor:pointer;"' +
                    ' data-ts="' + (row.timestamp || '') + '"' +
                    ' data-ticker="' + (row.ticker || '') + '"' +
                    ' data-lat="' + (row.lat || '') + '"' +
                    ' data-lon="' + (row.lon || '') + '"' +
                    ' data-rel="' + (row.rel || '') + '"' +
                    ' data-dir="' + (row.direction || 'long') + '"' +
                    ' data-desc="' + (row.rawDesc || '').replace(/"/g, '&quot;') + '">';
                html += row.prefix;
                html += '<span style="color:#888;font-size:11px;">' + row.description + '</span>';
                if (row.timeText) html += '<span style="color:#555;font-size:9px;float:right;">' + row.timeText + '</span>';
                html += '</div>';
            }

            // Summary line at bottom
            var actCount2 = 0, waitCount2 = 0;
            events.forEach(function (e) {
                if (e.relevance >= 0.55) actCount2++;
                else if (e.relevance >= 0.30) waitCount2++;
            });
            html += '<div style="padding:4px 0;color:#555;font-size:9px;margin-top:4px;">';
            html += 'SHOWING ' + shown.length + ' OF ' + events.length + ' \u00b7 ';
            html += '<span style="color:#5eead4">ACT ' + actCount2 + '</span> \u00b7 ';
            html += '<span style="color:#facc15">WAIT ' + waitCount2 + '</span>';
            html += '</div>';

            container.innerHTML = html;
        }
    }

    // -----------------------------------------------------------------------
    // Stats panel — Bayesian + Kelly + EWMA below the globe
    // -----------------------------------------------------------------------
    async function pollStats() {
        var data = await api("/api/stats/" + currentTicker);
        if (!data) return;
        var container = $id("mod_conninfo_innercontainer");
        if (!container) return;

        // Hide canvases
        container.querySelectorAll("canvas").forEach(function (c) { c.style.display = "none"; });

        // Find or create stats div (insert AFTER the scan button container)
        var statsDiv = $id("orbit-stats-panel");
        if (!statsDiv) {
            statsDiv = document.createElement("div");
            statsDiv.id = "orbit-stats-panel";
            statsDiv.style.cssText = "font-family:'Fira Mono',monospace;font-size:10px;padding:4px 6px;line-height:1.8;";
            var scanContainer = $id("orbit-scan-container");
            if (scanContainer && scanContainer.nextSibling) {
                container.insertBefore(statsDiv, scanContainer.nextSibling);
            } else if (scanContainer) {
                container.appendChild(statsDiv);
            } else {
                container.appendChild(statsDiv);
            }
        }

        var b = data.bayesian || {};
        var k = data.kelly || {};
        var e = data.ewma || {};

        var effHit = ((b.effective_hit_rate || 0) * 100).toFixed(1);
        var ciLo = ((b.lower_95 || 0) * 100).toFixed(0);
        var ciHi = ((b.upper_95 || 0) * 100).toFixed(0);
        var kellyPct = ((k.kelly_fraction || 0) * 100).toFixed(0);
        var kellyShares = k.recommended_shares || 0;
        var kellyDollars = (k.recommended_dollars || 0).toFixed(0);
        var stress = (e.current_stress || 0).toFixed(3);
        var stressColor = e.is_escalating ? "#f87171" : "#5eead4";
        var stressArrow = e.is_escalating ? "\u2191" : "\u2192";

        statsDiv.innerHTML =
            '<div style="color:#888;">CONFIDENCE</div>' +
            '<div style="color:#5eead4;font-size:12px;">' + effHit + '% <span style="color:#555;font-size:9px;">[' + ciLo + '-' + ciHi + ']</span></div>' +
            '<div style="color:#888;margin-top:4px;">KELLY SIZE</div>' +
            '<div style="color:#ccc;">' + kellyShares + ' sh <span style="color:#555;">$' + kellyDollars + ' (' + kellyPct + '%)</span></div>' +
            '<div style="color:#888;margin-top:4px;">STRESS</div>' +
            '<div style="color:' + stressColor + ';">' + stress + ' ' + stressArrow + '</div>';
    }

    // -----------------------------------------------------------------------
    // SCAN GDELT button — triggers event feed in bottom-left panel
    // -----------------------------------------------------------------------
    var _scanTriggered = false;

    function triggerScan() {
        if (_scanTriggered) return;
        _scanTriggered = true;

        // Change button text
        var btn = document.getElementById("orbit-scan-btn");
        if (btn) {
            btn.innerText = "SCANNING...";
            btn.style.color = "#facc15";
            btn.style.borderColor = "#facc15";
            btn.disabled = true;
        }

        // After 1 second "scan", show the event feed
        setTimeout(function() {
            // Show the bottom-left event feed container
            var evContainer = document.getElementById("orbit-bottom-events");
            if (evContainer) evContainer.style.display = "";

            // Inject blink CSS for typewriter cursor
            if (!document.getElementById('orbit-blink-css')) {
                var blinkStyle = document.createElement('style');
                blinkStyle.id = 'orbit-blink-css';
                blinkStyle.textContent = '@keyframes blink { 50% { opacity: 0; } }';
                document.head.appendChild(blinkStyle);
            }

            // Add a header to the event feed
            var header = document.createElement("div");
            header.style.cssText = "font-family:'Fira Mono',monospace;font-size:12px;color:#ccc;padding:0 0 4px 0;border-bottom:1px solid #1f1f1f;margin-bottom:6px;letter-spacing:0.08em;";
            header.innerText = "EVENT FEED";
            evContainer.insertBefore(header, evContainer.firstChild);

            // Load events
            pollBottomEvents();

            // Start polling now
            setInterval(pollBottomEvents, 10000);

            // Update button
            if (btn) {
                btn.innerText = "LIVE \u00b7 SCANNING";
                btn.style.color = "#5eead4";
                btn.style.borderColor = "#333";
            }
        }, 1000);
    }

    async function pollStatus() {
        var status = await api("/api/status");
        var h3 = $("#fs_space_bar h3");
        if (!h3) return;
        if (!status) { safeText(h3, "REPLAY \u00b7 0 FEEDS \u00b7 0 EVENTS \u00b7 IDLE"); return; }

        // Clean format: "REPLAY · 4 FEEDS · 53K EVENTS · 2M AGO · 3H LATENCY"
        var mode = status.mode ? String(status.mode).toUpperCase() : "REPLAY";
        var feedCount = status.active_feeds || status.feed_count || 0;
        var eventCount = status.events_scored || status.event_count || status.events || 0;
        var eventStr = eventCount >= 1000 ? Math.round(eventCount / 1000) + "K" : String(eventCount);

        var parts = [mode, feedCount + " FEEDS", eventStr + " EVENTS"];

        if (status.last_event_age != null) {
            var age = status.last_event_age;
            var ageStr = age < 60 ? age + "S AGO" : Math.floor(age / 60) + "M AGO";
            parts.push(ageStr);
        }
        if (status.latency_ms != null) {
            var lat = status.latency_ms;
            var latStr = lat >= 3600000 ? Math.floor(lat / 3600000) + "H" : lat >= 60000 ? Math.floor(lat / 60000) + "M" : lat + "MS";
            parts.push(latStr + " LATENCY");
        }

        var line = parts.join(" \u00b7 ");
        h3.style.cssText = "font-family:'Fira Mono',monospace;font-size:9px;color:#888;text-transform:uppercase;letter-spacing:0.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
        safeText(h3, line);
    }

    // -----------------------------------------------------------------------
    // Supply chain visualization -- ports + flight corridors on the globe
    // -----------------------------------------------------------------------
    var portPins = [];
    var flightMarkers = [];

    async function pollPorts() {
        var ports = await api("/api/ports");
        if (!ports || !window.mods || !window.mods.globe || !window.mods.globe.globe) return;

        var globe = window.mods.globe.globe;

        // Remove old port pins
        portPins.forEach(function (p) { try { p.remove(); } catch (e) {} });
        portPins = [];

        ports.forEach(function (port) {
            try {
                var label = ((port.location || port.name || "???").slice(0, 3)).toUpperCase() + " " + (port.ship_count || 0);
                var pin = globe.addPin(port.lat, port.lon, label, 1.3);
                portPins.push(pin);
            } catch (e) {}
        });
    }

    async function pollFlights() {
        var routes = await api("/api/flights");
        if (!routes || !window.mods || !window.mods.globe || !window.mods.globe.globe) return;

        var globe = window.mods.globe.globe;

        // Remove old flight markers
        flightMarkers.forEach(function (m) { try { m.remove(); } catch (e) {} });
        flightMarkers = [];

        // Add connected marker pairs for each flight route (draws arc lines)
        routes.forEach(function (route) {
            try {
                if (!route.active) return;
                var m1 = globe.addMarker(route.origin_lat, route.origin_lon, "", false);
                var m2 = globe.addMarker(route.dest_lat, route.dest_lon, "", true);
                flightMarkers.push(m1, m2);
            } catch (e) {}
        });

        // connH2 is now updated exclusively by pollEvents to avoid race condition
    }

    // -----------------------------------------------------------------------
    // Supply chain flow visualization
    // -----------------------------------------------------------------------
    var _supplyChainMarkers = [];   // markers currently on the globe
    var _supplyChainTimer = null;   // setTimeout handle for cleanup
    var _seenSupplyChainEvents = {}; // dedup so we don\'t re-trigger every poll

    var SUPPLY_CHAINS = {
        AAPL: [
            { lat: 25.03, lon: 121.56, label: "TSMC" },
            { lat: 22.54, lon: 114.06, label: "FOXCONN" },
            { lat: 37.33, lon: -121.89, label: "APPLE HQ" }
        ],
        NVDA: [
            { lat: 25.03, lon: 121.56, label: "TSMC" },
            { lat: 37.33, lon: -121.89, label: "NVIDIA HQ" }
        ],
        TSM: [
            { lat: 24.80, lon: 120.97, label: "TSMC HSINCHU" },
            { lat: 33.45, lon: -112.07, label: "TSMC PHOENIX" }
        ]
    };

    function clearSupplyChainMarkers() {
        _supplyChainMarkers.forEach(function (m) {
            try { m.remove(); } catch (e) {}
        });
        _supplyChainMarkers = [];
        _supplyChainTimer = null;
    }

    function highlightSupplyChain(ticker, eventLat, eventLon) {
        if (!window.mods || !window.mods.globe || !window.mods.globe.globe) return;
        var globe = window.mods.globe.globe;

        var chain = SUPPLY_CHAINS[ticker];
        if (!chain) return;

        // Clear any existing supply chain visualization
        clearSupplyChainMarkers();
        if (_supplyChainTimer) {
            clearTimeout(_supplyChainTimer);
            _supplyChainTimer = null;
        }

        // Place event origin pin if coords are valid and differ from chain start
        if (eventLat && eventLon) {
            var dist = Math.abs(eventLat - chain[0].lat) + Math.abs(eventLon - chain[0].lon);
            if (dist > 0.5) {
                try {
                    var originPin = globe.addPin(eventLat, eventLon, "EVENT", 1.8);
                    _supplyChainMarkers.push(originPin);
                } catch (e) {}
            }
        }

        // Add connected markers along the supply chain
        for (var i = 0; i < chain.length; i++) {
            try {
                var node = chain[i];
                var connected = (i > 0); // first node starts the chain; subsequent draw lines
                var marker = globe.addMarker(node.lat, node.lon, node.label, connected);
                _supplyChainMarkers.push(marker);
            } catch (e) {}
        }

        // Supply chain visual on the globe is sufficient; no narrative push
        // to keep the log clean (verdicts, P&L, high-relevance events only).

        // Remove chain markers after 10 seconds
        _supplyChainTimer = setTimeout(clearSupplyChainMarkers, 10000);
    }

    // -----------------------------------------------------------------------
    // Execute button handler
    // -----------------------------------------------------------------------
    function setupExecuteButton() {
        var btn = $id("orbit-execute-btn");
        if (!btn) return;

        btn.addEventListener("click", function () {
            if (btn.disabled) return;

            // Derive trade parameters from stored verdict state
            var tradeTicker = latestVerdict.ticker || currentTicker;
            var dir = latestVerdict.direction || currentDirection || "long";
            var side = dir === "long" ? "BUY" : "SELL";
            var sizeShares = 100;
            var price = latestVerdict.price || currentPrice || 0;
            var slippageBps = 2;
            var slippageMult = dir === "long" ? 1.0002 : 0.9998;
            var estFill = price > 0 ? (price * slippageMult).toFixed(2) : "--";
            var notional = price > 0 ? "$" + (price * sizeShares).toFixed(2) : "--";
            var priceStr = price > 0 ? "$" + price.toFixed(2) : "--";

            // Build the HTML body for the custom modal
            var htmlBody = '<h5 style="text-align:left;white-space:pre;font-family:\'Fira Mono\',monospace;line-height:1.8;">' +
                'DIRECTION   ' + side + '\n' +
                'TICKER      ' + tradeTicker + '\n' +
                'SIZE        ' + sizeShares + ' SHARES (' + notional + ' NOTIONAL)\n' +
                'PRICE       ' + priceStr + '\n' +
                'SLIPPAGE    ' + slippageBps + ' BPS\n' +
                'EST FILL    $' + estFill +
                '</h5>';

            // Store trade params on window so the eval'd onclick can access them
            window.__orbitPendingTrade = {
                ticker: tradeTicker,
                direction: dir,
                size_shares: sizeShares
            };

            // Build the confirm action string.
            // The action is eval'd from an onclick attribute so it runs in
            // global scope — use window-level helpers for modal close and
            // position refresh.
            var confirmAction =
                "fetch('/api/trades/execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(window.__orbitPendingTrade)})" +
                ".then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})" +
                ".then(function(d){" +
                    "if(window.audioManager&&window.audioManager.granted)window.audioManager.granted.play();" +
                    "var h3=document.querySelector('#fs_space_bar h3');" +
                    "if(h3)h3.innerText='TRADE EXECUTED \u00b7 '+window.__orbitPendingTrade.ticker+' '+window.__orbitPendingTrade.direction.toUpperCase()+' '+window.__orbitPendingTrade.size_shares+' SHARES';" +
                    "if(window.__orbitPollPositions)window.__orbitPollPositions();" +
                "})" +
                ".catch(function(e){" +
                    "if(window.audioManager&&window.audioManager.denied)window.audioManager.denied.play();" +
                    "var h3=document.querySelector('#fs_space_bar h3');" +
                    "if(h3)h3.innerText='TRADE FAILED \u00b7 '+e.message;" +
                "})" +
                ".finally(function(){var k=Object.keys(window.modals);if(k.length)window.modals[k[k.length-1]].close();});";

            // Use the existing eDEX modal system
            if (typeof Modal !== "undefined") {
                new Modal({
                    type: "custom",
                    title: "EXECUTE PAPER TRADE",
                    html: htmlBody,
                    buttons: [
                        { label: "CANCEL", action: "window.modals[Object.keys(window.modals).pop()].close();" },
                        { label: "CONFIRM", action: confirmAction }
                    ]
                });
            }
        });
    }

    // -----------------------------------------------------------------------
    // Tab switch hook
    // -----------------------------------------------------------------------
    // -----------------------------------------------------------------------
    // Globe rotation — smooth fly-to on tab switch
    // -----------------------------------------------------------------------
    // Primary exposure regions per ticker (where the globe should face)
    var TICKER_GLOBE_TARGETS = {
        AAPL: { lat: 25.03, lon: 121.56, label: "TAIWAN (TSMC)" },     // TSMC fab = AAPL's critical dependency
        NVDA: { lat: 25.03, lon: 121.56, label: "TAIWAN (TSMC)" },     // TSMC fab for NVDA chips too
        TSM:  { lat: 24.80, lon: 120.97, label: "HSINCHU (TSM HQ)" },  // TSM headquarters
    };
    var _globeAnimTimer = null;

    function flyGlobeTo(lon, duration) {
        if (!window.mods || !window.mods.globe || !window.mods.globe.globe) return;
        var globe = window.mods.globe.globe;
        var startAngle = globe.cameraAngle || 0;
        var targetAngle = (-lon * Math.PI / 180) + Math.PI;

        // Normalize both to [0, 2PI] then find shortest path
        var TWO_PI = 2 * Math.PI;
        startAngle = ((startAngle % TWO_PI) + TWO_PI) % TWO_PI;
        targetAngle = ((targetAngle % TWO_PI) + TWO_PI) % TWO_PI;
        var diff = targetAngle - startAngle;
        if (diff > Math.PI) diff -= TWO_PI;
        if (diff < -Math.PI) diff += TWO_PI;
        targetAngle = startAngle + diff;

        var startTime = Date.now();
        if (_globeAnimTimer) cancelAnimationFrame(_globeAnimTimer);

        function step() {
            var elapsed = Date.now() - startTime;
            var t = Math.min(elapsed / duration, 1);
            // Ease-in-out cubic
            var ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
            globe.cameraAngle = startAngle + (targetAngle - startAngle) * ease;
            if (t < 1) {
                _globeAnimTimer = requestAnimationFrame(step);
            } else {
                _globeAnimTimer = null;
            }
        }
        step();
    }

    // Sentiment flash — colored pin + land-dot radius glow (green/red)
    // for 5 seconds, then restore. Gives instant visual feedback on the globe.
    var _sentimentPin = null;
    var _sentimentTimer = null;
    var _savedTileColors = null; // backup of original color values

    function flashSentimentPin(lat, lon, direction) {
        if (!window.mods || !window.mods.globe || !window.mods.globe.globe) return;
        var globe = window.mods.globe.globe;

        // Remove any previous sentiment pin and restore tile colors
        if (_sentimentPin) {
            try { _sentimentPin.remove(); } catch (e) {}
            _sentimentPin = null;
        }
        if (_sentimentTimer) {
            clearTimeout(_sentimentTimer);
            _restoreTileColors(globe);
            _sentimentTimer = null;
        }

        var isBullish = (direction === "long");
        var pinColor = isBullish ? "#22c55e" : "#ef4444";
        var label = isBullish ? "\u25b2 BULLISH" : "\u25bc BEARISH";

        // --- 1. Colored pin ---
        var pin = globe.addPin(lat, lon, label, 1.8);
        if (!pin) return;

        try {
            if (pin.line && pin.line.material && pin.line.material.color) {
                pin.line.material.color.setStyle(pinColor);
                pin.line.material.needsUpdate = true;
            }
            if (pin.topSprite && pin.topSprite.material) {
                if (pin.topSprite.material.color) pin.topSprite.material.color.setStyle(pinColor);
                pin.topSprite.material.needsUpdate = true;
            }
            if (pin.labelSprite && pin.labelSprite.material) {
                if (pin.labelSprite.material.color) pin.labelSprite.material.color.setStyle(pinColor);
                pin.labelSprite.material.needsUpdate = true;
            }
        } catch (e) {}

        // --- 2. Color land dots in a radius ---
        try {
            _colorTilesInRadius(globe, lat, lon, isBullish);
        } catch (e) { console.warn("ORBIT tile color error:", e); }

        _sentimentPin = pin;

        // Remove after 5 seconds
        _sentimentTimer = setTimeout(function () {
            try { pin.remove(); } catch (e) {}
            _restoreTileColors(globe);
            if (_sentimentPin === pin) _sentimentPin = null;
            _sentimentTimer = null;
        }, 5000);
    }

    function _colorTilesInRadius(globe, eventLat, eventLon, isBullish) {
        if (!globe.hexGrid || !globe.hexGrid.geometry) return;
        var colors = globe.hexGrid.geometry.attributes.color.array;
        var tiles = globe.tiles;
        if (!tiles || tiles.length === 0) return;

        // Save original colors so we can restore later
        _savedTileColors = new Float32Array(colors.length);
        _savedTileColors.set(colors);

        // Sentiment color: green (0.133, 0.773, 0.369) or red (0.937, 0.267, 0.267)
        var cr = isBullish ? 0.133 : 0.937;
        var cg = isBullish ? 0.773 : 0.267;
        var cb = isBullish ? 0.369 : 0.267;

        var RADIUS_DEG = 12; // ~12 degrees = ~1300 km radius
        var rSq = RADIUS_DEG * RADIUS_DEG;

        // grid.json lat convention is negated vs standard geographic lat
        // (getLatLon: lat = 180*acos(y/r)/PI - 90, so positive grid lat = negative y = southern hemisphere)
        // Pins use mapPoint which uses standard convention, so negate eventLat for tile comparison.
        var gridLat = -eventLat;

        for (var i = 0; i < tiles.length; i++) {
            var t = tiles[i];
            var dLat = t.lat - gridLat;
            var dLon = t.lon - eventLon;
            // Wrap longitude difference
            if (dLon > 180) dLon -= 360;
            if (dLon < -180) dLon += 360;
            var distSq = dLat * dLat + dLon * dLon;

            if (distSq < rSq) {
                // Intensity fades from center (1.0) to edge (0.3)
                var fade = 1.0 - 0.7 * (distSq / rSq);
                // Each tile = 4 triangles × 3 vertices × 3 color components = 36 floats
                var base = i * 36;
                for (var v = 0; v < 36; v += 3) {
                    // Blend: original × (1-fade) + sentiment × fade
                    colors[base + v]     = colors[base + v] * (1 - fade) + cr * fade;
                    colors[base + v + 1] = colors[base + v + 1] * (1 - fade) + cg * fade;
                    colors[base + v + 2] = colors[base + v + 2] * (1 - fade) + cb * fade;
                }
            }
        }

        globe.hexGrid.geometry.attributes.color.needsUpdate = true;
    }

    function _restoreTileColors(globe) {
        if (!_savedTileColors || !globe.hexGrid || !globe.hexGrid.geometry) return;
        var colors = globe.hexGrid.geometry.attributes.color.array;
        colors.set(_savedTileColors);
        globe.hexGrid.geometry.attributes.color.needsUpdate = true;
        _savedTileColors = null;
    }

    // Called whenever the active ticker changes (tab click or programmatic switch)
    function onTickerSwitch(newTicker) {
        if (newTicker === currentTicker) return;
        currentTicker = newTicker;
        pollVerdict();
        pollBottomEvents();

        // Smooth globe rotation to ticker's primary exposure region
        var target = TICKER_GLOBE_TARGETS[newTicker];
        if (target) {
            flyGlobeTo(target.lon, 1200);
            safeText(_cachedGlobeInfo, target.lat.toFixed(4) + ", " + target.lon.toFixed(4));
            setTimeout(function () {
                highlightSupplyChain(newTicker, target.lat, target.lon);
            }, 600);
        }
    }

    function hookTabs() {
        // Use a delegated click listener on the tab bar instead of wrapping
        // window.focusShellTab. stock-charts.js overwrites focusShellTab in
        // its mount() — a race condition that silently drops our wrapper.
        // A click listener is immune to that race.
        var tickers = ["AAPL", "NVDA", "TSM"];
        var tabBar = $id("main_shell_tabs");
        if (!tabBar) return;

        tabBar.addEventListener("click", function (e) {
            var li = e.target.closest("li");
            if (!li) return;
            var tabs = tabBar.querySelectorAll("li");
            var n = -1;
            for (var i = 0; i < tabs.length; i++) {
                if (tabs[i] === li) { n = i; break; }
            }
            if (n < 0 || n >= tickers.length) return;
            onTickerSwitch(tickers[n]);
        });
    }

    // -----------------------------------------------------------------------
    // Boot
    // -----------------------------------------------------------------------
    async function boot() {
        // Wait for eDEX UI mods
        for (var i = 0; i < 120 && !window.mods; i++) {
            await new Promise(function (r) { setTimeout(r, 500); });
        }
        if (!window.mods) { console.warn("ORBIT: eDEX UI not ready"); return; }

        // Wait for eDEX keyboard animation to fully settle (animation_state_1
        // → animation_state_2 → class cleared = ~1.6s after initUI). By the
        // time window.mods is set the animation is done, but give an extra
        // beat so any final CSS transitions complete before we inject DOM.
        await new Promise(function (r) { setTimeout(r, 300); });

        // Hide the aesthetic keyboard entirely — reserved for future use
        var kbSection = document.getElementById("keyboard");
        if (kbSection) kbSection.style.display = "none";

        // Kill eDEX system-monitor updaters so they stop overwriting
        // ORBIT's trading-desk data every 2 seconds.
        try {
            if (window.mods.toplist) {
                clearInterval(window.mods.toplist.listUpdater);
                window.mods.toplist.listUpdater = null;
                window.mods.toplist.updateList = function () {};
            }
            if (window.mods.ramwatcher) {
                if (window.mods.ramwatcher.infoUpdater) clearInterval(window.mods.ramwatcher.infoUpdater);
                window.mods.ramwatcher.updateInfo = function () {};
                window.mods.ramwatcher.currentlyUpdating = true; // block any in-flight call
            }
            if (window.mods.cpuinfo) {
                // Correct property names from cpuinfo.class.js
                if (window.mods.cpuinfo.loadUpdater) clearInterval(window.mods.cpuinfo.loadUpdater);
                if (window.mods.cpuinfo.tempUpdater) clearInterval(window.mods.cpuinfo.tempUpdater);
                if (window.mods.cpuinfo.speedUpdater) clearInterval(window.mods.cpuinfo.speedUpdater);
                if (window.mods.cpuinfo.tasksUpdater) clearInterval(window.mods.cpuinfo.tasksUpdater);
                // Override all update methods to no-ops
                window.mods.cpuinfo.updateCPUload = function () {};
                window.mods.cpuinfo.updateCPUtemp = function () {};
                window.mods.cpuinfo.updateCPUspeed = function () {};
                window.mods.cpuinfo.updateCPUtasks = function () {};
            }
            if (window.mods.sysinfo) {
                // sysinfo.class.js uses uptimeUpdater, batteryUpdater, and recursive setTimeout in updateDate
                if (window.mods.sysinfo.uptimeUpdater) clearInterval(window.mods.sysinfo.uptimeUpdater);
                if (window.mods.sysinfo.batteryUpdater) clearInterval(window.mods.sysinfo.batteryUpdater);
                // Override all update methods to prevent them from resetting labels
                window.mods.sysinfo.updateDate = function () {};
                window.mods.sysinfo.updateUptime = function () {};
                window.mods.sysinfo.updateBattery = function () {};
            }
            if (window.mods.hardwareInspector && window.mods.hardwareInspector.infoUpdater) {
                clearInterval(window.mods.hardwareInspector.infoUpdater);
            }
            if (window.mods.conninfo) {
                if (window.mods.conninfo.infoUpdater) clearInterval(window.mods.conninfo.infoUpdater);
                window.mods.conninfo.updateInfo = function () {};
            }
            if (window.mods.netstat) {
                if (window.mods.netstat.infoUpdater) clearInterval(window.mods.netstat.infoUpdater);
                window.mods.netstat.updateInfo = function () {};
            }
            // Kill globe updaters so they stop overwriting our coords / offline state
            if (window.mods.globe) {
                if (window.mods.globe.locUpdater) {
                    clearInterval(window.mods.globe.locUpdater);
                    window.mods.globe.locUpdater = null;
                }
                if (window.mods.globe.connsUpdater) {
                    clearInterval(window.mods.globe.connsUpdater);
                    window.mods.globe.connsUpdater = null;
                }
                window.mods.globe.updateLoc = function () {};
                window.mods.globe.updateConns = function () {};
            }
        } catch (e) { console.warn("ORBIT: error killing eDEX updaters:", e); }

        // --- Fix 1: Remove OFFLINE overlay from globe and conninfo ---
        // Force netstat.offline = false permanently via property descriptor
        if (window.mods.netstat) {
            window.mods.netstat.offline = false;
            try {
                Object.defineProperty(window.mods.netstat, "offline", {
                    get: function () { return false; },
                    set: function () {},
                    configurable: true
                });
            } catch (e) { console.warn("ORBIT: could not lock netstat.offline:", e); }
        }
        // Remove offline class and hide OFFLINE h3 text on globe
        var globeDiv = $("div#mod_globe");
        if (globeDiv) globeDiv.setAttribute("class", "");
        var offlineH3Globe = $("div#mod_globe h3");
        if (offlineH3Globe) offlineH3Globe.style.display = "none";
        // Also remove offline state from conninfo
        var conninfoDiv = $("div#mod_conninfo");
        if (conninfoDiv) conninfoDiv.setAttribute("class", "");
        var offlineH3Conn = $("div#mod_conninfo h3");
        if (offlineH3Conn) offlineH3Conn.style.display = "none";
        // Keep removing offline class and hiding OFFLINE h3 every second
        // because eDEX's updateLoc re-adds it
        setInterval(function () {
            var gd = $("div#mod_globe");
            if (gd) gd.classList.remove("offline");
            var gh3 = $("div#mod_globe h3");
            if (gh3) gh3.style.display = "none";
            var cd = $("div#mod_conninfo");
            if (cd) cd.classList.remove("offline");
            var ch3 = $("div#mod_conninfo h3");
            if (ch3) ch3.style.display = "none";
            // Force netstat.offline to false
            if (window.mods && window.mods.netstat) {
                try {
                    Object.defineProperty(window.mods.netstat, "offline", {
                        get: function () { return false; },
                        set: function () {},
                        configurable: true
                    });
                } catch (e) {}
            }
        }, 1000);

        // Relabel all panels
        relabelLeft();
        relabelRight();
        relabelBottom();

        // Re-relabel sysinfo and stat boxes every 2s to fight residual eDEX timers
        setInterval(function () {
            // Kill sysinfo updaters again in case they were re-registered
            if (window.mods && window.mods.sysinfo) {
                window.mods.sysinfo.updateDate = function () {};
                window.mods.sysinfo.updateUptime = function () {};
                window.mods.sysinfo.updateBattery = function () {};
            }
            // Re-apply all 4 sysinfo divs to prevent eDEX timer overwrites
            // Each h2 value must be <= 6 characters to fit the ~80px box
            var rNow = new Date();
            var rMonths = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
            var rDay = rNow.getDate() < 10 ? "0" + rNow.getDate() : String(rNow.getDate());
            var rDiv1H1 = $("#mod_sysinfo > div:first-child > h1");
            var rDiv1H2 = $("#mod_sysinfo > div:first-child > h2");
            if (rDiv1H1) safeText(rDiv1H1, String(rNow.getFullYear()));
            if (rDiv1H2) safeText(rDiv1H2, rMonths[rNow.getMonth()] + " " + rDay);
            var rDiv2H1 = $("#mod_sysinfo > div:nth-child(2) > h1");
            var rDiv2H2 = $("#mod_sysinfo > div:nth-child(2) > h2");
            if (rDiv2H1 && rDiv2H1.innerText !== "LIVE") safeText(rDiv2H1, "LIVE");
            // Compute short uptime H:MM (max 6 chars)
            var rUptimeSec = Math.floor((Date.now() - _orbitBootTime) / 1000);
            var rUptimeH = Math.floor(rUptimeSec / 3600);
            var rUptimeM = Math.floor((rUptimeSec % 3600) / 60);
            var rUptimeStr = rUptimeH + ":" + (rUptimeM < 10 ? "0" : "") + rUptimeM;
            if (rDiv2H2) safeText(rDiv2H2, rUptimeStr);
            var sysDiv3H1 = $("#mod_sysinfo > div:nth-child(3) > h1");
            var sysDiv3H2 = $("#mod_sysinfo > div:nth-child(3) > h2");
            if (sysDiv3H1 && sysDiv3H1.innerText !== "MODE") safeText(sysDiv3H1, "MODE");
            if (sysDiv3H2 && sysDiv3H2.innerText !== "PAPER") safeText(sysDiv3H2, "PAPER");
            var sysDiv4H1 = $("#mod_sysinfo > div:nth-child(4) > h1");
            var sysDiv4H2 = $("#mod_sysinfo > div:nth-child(4) > h2");
            if (sysDiv4H1 && sysDiv4H1.innerText !== "FEED") safeText(sysDiv4H1, "FEED");
            if (sysDiv4H2 && sysDiv4H2.innerText !== "LIVE") safeText(sysDiv4H2, "LIVE");
            // Re-apply stat box labels (VOL/TURN/DRAW/OPEN)
            var sDivs = document.querySelectorAll("#mod_cpuinfo_innercontainer > div:last-child > div");
            var sLabels = ["VOL", "TURN", "DRAW", "OPEN"];
            for (var si = 0; si < Math.min(sDivs.length, 4); si++) {
                var sh1 = sDivs[si].querySelector("h1");
                if (sh1 && sh1.childNodes[0] && sh1.childNodes[0].textContent !== sLabels[si]) {
                    sh1.childNodes[0].textContent = sLabels[si];
                }
            }
        }, 2000);

        // Inject verdict + scorecard strips + ticker
        injectVerdictStrip();
        injectScorecardStrip();
        injectTicker();

        // Wire interactions
        setTimeout(setupExecuteButton, 500);
        hookTabs();

        // Wire SCAN GDELT button click handler (delegate since button is created by pollStats)
        document.addEventListener("click", function (e) {
            if (e.target && e.target.id === "orbit-scan-btn") {
                triggerScan();
            }
        });

        // Wire click-to-jump on event feed rows (delegated)
        document.addEventListener("click", function (e) {
            var row = e.target.closest("[data-ts]");
            if (!row || !row.closest("#orbit-bottom-events")) return;

            var ticker = row.getAttribute("data-ticker") || currentTicker;
            var ts = row.getAttribute("data-ts");
            var lat = row.getAttribute("data-lat");
            var lon = row.getAttribute("data-lon");

            // Switch ticker tab if the event belongs to a different ticker
            var tickers = ["AAPL", "NVDA", "TSM"];
            var tabIdx = tickers.indexOf(ticker);
            if (tabIdx >= 0 && ticker !== currentTicker) {
                // Switch chart pane via stock-charts' focusShellTab
                if (window.focusShellTab) window.focusShellTab(tabIdx);
                // Update ORBIT state (event feed, verdict, globe)
                onTickerSwitch(ticker);
            }

            // Flash the clicked row for visual feedback
            var origBg = row.style.backgroundColor || "";
            row.style.backgroundColor = "#1a3a2a";
            row.style.transition = "background-color 0.3s";
            setTimeout(function () { row.style.backgroundColor = origBg; }, 600);

            // Play sound immediately (don't let errors below block it)
            try { playSound("folder"); } catch (e) {}

            // Fly globe — use event coords if available, else ticker's primary exposure
            try {
                var useLat = (lat && parseFloat(lat) !== 0) ? parseFloat(lat) : (TICKER_GLOBE_TARGETS[ticker] || {}).lat || 25.03;
                var useLon = (lon && parseFloat(lon) !== 0) ? parseFloat(lon) : (TICKER_GLOBE_TARGETS[ticker] || {}).lon || 121.56;
                flyGlobeTo(useLon, 800);
                if (!_cachedGlobeInfo || !_cachedGlobeInfo.parentNode) {
                    _cachedGlobeInfo = $("i.mod_globe_headerInfo");
                }
                if (!_cachedGlobeInfo) {
                    var globeH2 = $("#mod_globe h2");
                    if (globeH2) _cachedGlobeInfo = globeH2.querySelector("i");
                }
                safeText(_cachedGlobeInfo, useLat.toFixed(4) + ", " + useLon.toFixed(4));

                // Sentiment flash pin — green for bullish (long), red for bearish (short)
                var evDir = row.getAttribute("data-dir") || "long";
                flashSentimentPin(useLat, useLon, evDir);
            } catch (e) { console.warn("ORBIT globe error:", e); }

            // Supply chain highlight
            try { highlightSupplyChain(ticker, null, null); } catch (e) {}

            // Flash chart marker
            try {
                var rel = parseFloat(row.getAttribute("data-rel") || "0");
                var dir = row.getAttribute("data-dir") || "long";
                if (ts && window.__PrismCharts && window.__PrismCharts.flashEventMarker) {
                    window.__PrismCharts.flashEventMarker(ticker, parseInt(ts), rel, dir);
                }
            } catch (e) { console.warn("ORBIT chart flash error:", e); }
        });

        // Task 2H: Empty tabs -> "+"
        var tab3 = document.getElementById("shell_tab3");
        var tab4 = document.getElementById("shell_tab4");
        if (tab3) { tab3.innerHTML = "<p>+</p>"; tab3.style.opacity = "0.2"; }
        if (tab4) { tab4.innerHTML = "<p>+</p>"; tab4.style.opacity = "0.2"; }

        // Expose pollPositions so the modal's onclick (eval'd in global scope)
        // can refresh positions immediately after a trade executes.
        window.__orbitPollPositions = pollPositions;

        // Initial data load
        pollVerdict();
        pollPositions();
        pollScorecard();
        pollSession();
        pollEvents();
        pollStatus();
        pollPorts();
        pollFlights();
        pollStats();

        // Polling loops
        setInterval(pollVerdict, 5000);
        setInterval(pollPositions, 5000);
        setInterval(pollScorecard, 15000);
        setInterval(pollSession, 10000);   // session row updates every 10s
        setInterval(pollEvents, 5000);
        setInterval(pollStatus, 10000);
        setInterval(pollPorts, 30000);
        setInterval(pollFlights, 60000);
        setInterval(pollStats, 5000);

        // Wire session summary overlay hotkey
        setupSessionSummaryOverlay();

        // Wire mute toggle hotkey (M)
        setupMuteToggle();

        console.log("ORBIT: UI layer active");
    }

    // -----------------------------------------------------------------------
    // Session Summary Overlay  (press S to toggle)
    // -----------------------------------------------------------------------
    var _summaryOverlay = null;
    var _summaryVisible = false;

    function setupSessionSummaryOverlay() {
        document.addEventListener("keydown", function (e) {
            // Don't trigger when typing in an input/textarea
            var tag = (document.activeElement && document.activeElement.tagName || "").toLowerCase();
            if (tag === "input" || tag === "textarea" || tag === "select") return;
            if (document.activeElement && document.activeElement.isContentEditable) return;

            if (e.key === "s" || e.key === "S") {
                e.preventDefault();
                toggleSessionSummary();
            }
        });
    }

    async function toggleSessionSummary() {
        if (_summaryVisible) {
            // Hide
            if (_summaryOverlay && _summaryOverlay.parentNode) {
                _summaryOverlay.parentNode.removeChild(_summaryOverlay);
            }
            _summaryOverlay = null;
            _summaryVisible = false;
            return;
        }

        // Show -- fetch data from all three endpoints in parallel
        var statusData = null;
        var portfolioData = null;
        var scorecardData = null;

        try {
            var results = await Promise.all([
                api("/api/status"),
                api("/api/portfolio/summary"),
                api("/api/scorecard/live")
            ]);
            statusData = results[0];
            portfolioData = results[1];
            scorecardData = results[2];
        } catch (e) { /* proceed with nulls */ }

        // --- Derive stats ---
        var eventsScored = 0;
        if (statusData) {
            eventsScored = statusData.events_scored
                || statusData.event_count
                || statusData.events
                || 0;
        }

        var tradesExecuted = 0;
        var sessionPnlPct = 0;
        var alphaPct = 0;
        var actCount = 0;
        var waitCount = 0;
        var ignoreCount = 0;

        if (portfolioData) {
            tradesExecuted = portfolioData.total_trades
                || portfolioData.trades_executed
                || portfolioData.trade_count
                || 0;
            if (tradesExecuted === 0) {
                tradesExecuted = (portfolioData.closed_positions || 0)
                    + (portfolioData.open_positions || 0);
            }
            sessionPnlPct = portfolioData.session_pnl_pct
                || portfolioData.pnl_pct
                || portfolioData.return_pct
                || 0;
            alphaPct = portfolioData.alpha_vs_spy
                || portfolioData.alpha
                || 0;
            actCount = portfolioData.act_count || 0;
            waitCount = portfolioData.wait_count || 0;
            ignoreCount = portfolioData.ignore_count || 0;
        }

        var verdictsIssued = actCount + waitCount + ignoreCount;

        // Live scorecard: derive win rate
        var winRate = 0;
        if (scorecardData && scorecardData.length > 0) {
            var scTotalTrades = 0;
            var weightedWin = 0;
            scorecardData.forEach(function (s) {
                var t = s.total_trades || 0;
                scTotalTrades += t;
                if (s.win_rate != null && typeof s.win_rate === "number" && !isNaN(s.win_rate)) {
                    weightedWin += s.win_rate * t;
                }
            });
            if (scTotalTrades > 0) winRate = weightedWin / scTotalTrades;
            // If no trade-level counts came from portfolio, use scorecard totals
            if (tradesExecuted === 0) tradesExecuted = scTotalTrades;
        }

        // --- Format helpers ---
        function fmtPct(v) {
            if (v == null || isNaN(v)) return "--";
            var sign = v >= 0 ? "+" : "";
            return sign + Math.abs(v).toFixed(1) + "%";
        }
        function fmtWinPct(v) {
            if (v == null || isNaN(v)) return "--";
            return Math.round(v) + "%";
        }
        function pad(label, value, totalWidth) {
            var gap = totalWidth - label.length - String(value).length;
            if (gap < 1) gap = 1;
            var spaces = "";
            for (var i = 0; i < gap; i++) spaces += " ";
            return label + spaces + value;
        }

        var W = 36;
        var lines = [
            "",
            "       ORBIT SESSION SUMMARY",
            "       \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "",
            pad("       EVENTS SCORED", String(eventsScored), W),
            pad("       VERDICTS ISSUED", String(verdictsIssued), W),
            pad("         ACT", String(actCount), W),
            pad("         WAIT", String(waitCount), W),
            pad("         IGNORE", String(ignoreCount), W),
            pad("       TRADES EXECUTED", String(tradesExecuted), W),
            pad("       WIN RATE", fmtWinPct(winRate), W),
            pad("       SESSION P&L", fmtPct(sessionPnlPct), W),
            pad("       ALPHA vs SPY", fmtPct(alphaPct), W),
            "",
            "       press S to close",
            ""
        ];

        // Build overlay DOM
        var overlay = document.createElement("div");
        overlay.id = "orbit-session-summary-overlay";
        overlay.style.cssText =
            "position:fixed;top:0;left:0;right:0;bottom:0;" +
            "z-index:99999;" +
            "background:rgba(0,0,0,0.95);" +
            "display:flex;align-items:center;justify-content:center;" +
            "font-family:'Fira Mono',monospace;font-size:14px;" +
            "color:#e4e4e4;letter-spacing:0.1em;";

        var box = document.createElement("pre");
        box.style.cssText =
            "margin:0;padding:0;" +
            "font-family:inherit;font-size:inherit;" +
            "color:inherit;letter-spacing:inherit;" +
            "line-height:1.8;white-space:pre;";
        box.textContent = lines.join("\n");

        overlay.appendChild(box);
        document.body.appendChild(overlay);
        _summaryOverlay = overlay;
        _summaryVisible = true;
    }

    // -----------------------------------------------------------------------
    // Mute Toggle  (press M to toggle sound on/off)
    // -----------------------------------------------------------------------
    var _muteStatusTimer = null;

    function setupMuteToggle() {
        document.addEventListener("keydown", function (e) {
            // Don't trigger when typing in an input/textarea
            var tag = (document.activeElement && document.activeElement.tagName || "").toLowerCase();
            if (tag === "input" || tag === "textarea" || tag === "select") return;
            if (document.activeElement && document.activeElement.isContentEditable) return;

            if (e.key === "m" || e.key === "M") {
                e.preventDefault();
                _soundMuted = !_soundMuted;
                showMuteStatus(_soundMuted ? "SOUND MUTED" : "SOUND ON");
            }
        });
    }

    function showMuteStatus(msg) {
        var h3 = $("#fs_space_bar h3");
        if (!h3) return;
        var prev = h3.innerText;
        safeText(h3, msg);
        if (_muteStatusTimer) clearTimeout(_muteStatusTimer);
        _muteStatusTimer = setTimeout(function () {
            _muteStatusTimer = null;
            // Restore by re-polling status (overwrites with live data)
            pollStatus();
        }, 2000);
    }

    window.__orbitMute = function () { _soundMuted = !_soundMuted; };

    window.__orbitBoot = boot;
})();
