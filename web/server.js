// ORBIT server — serves the PRISM/eDEX-UI frontend, proxies Yahoo Finance
// chart data, AND proxies /api/* to the ORBIT FastAPI backend at port 8000.
//
//   node web/server.js          →  http://127.0.0.1:8080
//
// Endpoints:
//   GET /*                      →  static file from repo root
//   GET /api/chart/:symbol      →  Yahoo Finance OHLC (proxied)
//   GET|POST /api/*             →  ORBIT FastAPI backend (proxied to :8000)

const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const url = require("url");

const PORT = 8080;
const ROOT = path.resolve(__dirname, "..");
// Load env from multiple locations (first found wins)
[path.join(ROOT, ".env"), path.join(require("os").homedir(), ".orbit-env")].forEach(p => {
    if (fs.existsSync(p)) { fs.readFileSync(p, "utf-8").split("\n").forEach(line => {
        const [key, ...val] = line.split("=");
        if (key && val.length && !process.env[key.trim()]) process.env[key.trim()] = val.join("=").trim();
    }); }
});

const MIME = {
    ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
    ".css": "text/css", ".json": "application/json", ".png": "image/png",
    ".jpg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ico": "image/x-icon",
};

function serveStatic(req, res) {
    let fp = path.join(ROOT, decodeURIComponent(url.parse(req.url).pathname));
    if (fp.endsWith("/") || fp === ROOT) fp = path.join(fp, "index.html");
    if (!fp.startsWith(ROOT)) { res.writeHead(403); res.end(); return; }
    fs.stat(fp, (err, stat) => {
        if (err || !stat.isFile()) { res.writeHead(404, { "Content-Type": "text/plain" }); res.end("Not found"); return; }
        const ext = path.extname(fp).toLowerCase();
        res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
        fs.createReadStream(fp).pipe(res);
    });
}

function proxyChart(req, res, symbol) {
    const range = url.parse(req.url, true).query.range || "6mo";
    const interval = url.parse(req.url, true).query.interval || "1d";
    const target = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${interval}&range=${range}`;
    const opts = { headers: { "User-Agent": "Mozilla/5.0" } };
    https.get(target, opts, (upstream) => {
        res.writeHead(upstream.statusCode, {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        });
        upstream.pipe(res);
    }).on("error", (e) => {
        res.writeHead(502, { "Content-Type": "text/plain" }); res.end("upstream error: " + e.message);
    });
}

// Proxy any /api/* request (except /api/chart/) to the ORBIT FastAPI backend.
const BACKEND = "http://127.0.0.1:8000";

function proxyToBackend(req, res) {
    const opts = url.parse(BACKEND + req.url);
    opts.method = req.method;
    opts.headers = Object.assign({}, req.headers, { host: "127.0.0.1:8000" });

    const proxy = http.request(opts, (upstream) => {
        res.writeHead(upstream.statusCode, upstream.headers);
        upstream.pipe(res);
    });
    proxy.on("error", (e) => {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "backend unreachable: " + e.message }));
    });
    req.pipe(proxy);
}

http.createServer((req, res) => {
    const parsed = url.parse(req.url, true);
    // Yahoo chart proxy (keeps existing PRISM stock chart working)
    if (parsed.pathname === "/env.js") { res.writeHead(200, { "Content-Type": "text/javascript" }); res.end("window.__ENV={FINNHUB_KEY:" + JSON.stringify(process.env.FINNHUB_KEY || "") + "};"); return; }
    const chartMatch = parsed.pathname.match(/^\/api\/chart\/([A-Za-z0-9.^=-]+)$/);
    if (chartMatch) return proxyChart(req, res, chartMatch[1]);
    // All other /api/* routes → ORBIT FastAPI backend
    if (parsed.pathname.startsWith("/api/")) return proxyToBackend(req, res);
    serveStatic(req, res);
}).listen(PORT, "127.0.0.1", () => {
    console.log("ORBIT server → http://127.0.0.1:" + PORT);
});
