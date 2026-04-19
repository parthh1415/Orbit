// Shim to let the Electron renderer code run inside a plain browser.
// Provides a fake `require()`, Node globals, and stubs for Node/Electron APIs.
// The real backend is intentionally absent: the terminal, file system, network
// monitors, etc. will render but do nothing.

(function () {
    "use strict";

    const USER_DATA = "web/userData";
    const SRC_DIR = "src";

    // ---- path polyfill ----------------------------------------------------
    const pathShim = {
        sep: "/",
        delimiter: ":",
        join: function (...parts) {
            const out = [];
            for (const p of parts) {
                if (p === undefined || p === null || p === "") continue;
                out.push(String(p));
            }
            return pathShim.normalize(out.join("/"));
        },
        normalize: function (p) {
            if (!p) return ".";
            const isAbs = p.startsWith("/");
            const parts = p.split("/").filter(Boolean);
            const stack = [];
            for (const part of parts) {
                if (part === ".") continue;
                if (part === "..") { stack.pop(); continue; }
                stack.push(part);
            }
            return (isAbs ? "/" : "") + stack.join("/");
        },
        resolve: function (...parts) { return pathShim.join(...parts); },
        basename: function (p, ext) {
            p = String(p || "");
            const i = p.lastIndexOf("/");
            let b = i === -1 ? p : p.slice(i + 1);
            if (ext && b.endsWith(ext)) b = b.slice(0, -ext.length);
            return b;
        },
        dirname: function (p) {
            p = String(p || "");
            const i = p.lastIndexOf("/");
            return i === -1 ? "." : (i === 0 ? "/" : p.slice(0, i));
        },
        extname: function (p) {
            p = String(p || "");
            const b = pathShim.basename(p);
            const i = b.lastIndexOf(".");
            return i <= 0 ? "" : b.slice(i);
        },
        parse: function (p) {
            const dir = pathShim.dirname(p);
            const base = pathShim.basename(p);
            const ext = pathShim.extname(p);
            return { root: "", dir, base, name: base.slice(0, base.length - ext.length), ext };
        },
        isAbsolute: function (p) { return String(p || "").startsWith("/"); },
    };

    // ---- synchronous XHR helper ------------------------------------------
    function fetchSync(url) {
        try {
            const xhr = new XMLHttpRequest();
            xhr.open("GET", url, false);
            xhr.send(null);
            if (xhr.status >= 200 && xhr.status < 300) return xhr.responseText;
        } catch (e) { /* ignore */ }
        return null;
    }

    const fsCache = Object.create(null);
    const fsDirCache = Object.create(null);

    function primeCache(logicalPath, data) { fsCache[logicalPath] = data; }
    function primeDir(logicalPath, entries) { fsDirCache[logicalPath] = entries; }

    // ---- fs polyfill ------------------------------------------------------
    const fsShim = {
        readFileSync: function (p, opts) {
            const key = pathShim.normalize(String(p));
            let data = fsCache[key];
            if (data === undefined) {
                data = fetchSync(key);
                if (data !== null) fsCache[key] = data;
            }
            if (data === undefined || data === null) {
                throw new Error("ENOENT (shim): " + key);
            }
            return data;
        },
        readFile: function (p, optOrCb, cb) {
            const callback = typeof optOrCb === "function" ? optOrCb : cb;
            try { const d = fsShim.readFileSync(p); callback && callback(null, d); }
            catch (e) { callback && callback(e); }
        },
        writeFileSync: function () { /* no-op: web is read-only */ },
        writeFile: function (_p, _d, _o, cb) { (typeof _o === "function" ? _o : cb) && (typeof _o === "function" ? _o : cb)(null); },
        existsSync: function (p) {
            const key = pathShim.normalize(String(p));
            return fsCache[key] !== undefined || fsDirCache[key] !== undefined;
        },
        readdirSync: function (p) {
            const key = pathShim.normalize(String(p));
            return fsDirCache[key] || [];
        },
        readdir: function (p, cb) { try { cb(null, fsShim.readdirSync(p)); } catch (e) { cb(e); } },
        mkdirSync: function () {},
        mkdir: function (_p, cb) { cb && cb(null); },
        statSync: function () { return { isDirectory: () => false, isFile: () => true, size: 0, mtime: new Date() }; },
        lstatSync: function () { return fsShim.statSync(); },
        watch: function () { return { close: () => {}, on: () => {} }; },
        watchFile: function () {},
        unwatchFile: function () {},
        readlink: function (_p, cb) { cb && cb(new Error("readlink not supported in browser")); },
        createReadStream: function () { return { on: () => {}, pipe: () => {}, close: () => {} }; },
        promises: {},
    };

    // ---- os polyfill ------------------------------------------------------
    const osShim = {
        platform: () => "darwin",
        type: () => "Darwin",
        arch: () => "x64",
        release: () => "0.0.0",
        hostname: () => "web",
        homedir: () => "/",
        tmpdir: () => "/tmp",
        uptime: () => Math.floor(performance.now() / 1000),
        cpus: () => [{ model: "Web CPU", speed: 0, times: {} }],
        totalmem: () => 0,
        freemem: () => 0,
        networkInterfaces: () => ({}),
        EOL: "\n",
    };

    // ---- events polyfill --------------------------------------------------
    class EventEmitter {
        constructor() { this._l = Object.create(null); }
        on(ev, fn) { (this._l[ev] = this._l[ev] || []).push(fn); return this; }
        once(ev, fn) {
            const w = (...args) => { this.off(ev, w); fn(...args); };
            return this.on(ev, w);
        }
        off(ev, fn) {
            const arr = this._l[ev]; if (!arr) return this;
            this._l[ev] = arr.filter(x => x !== fn); return this;
        }
        removeListener(ev, fn) { return this.off(ev, fn); }
        removeAllListeners(ev) { if (ev) delete this._l[ev]; else this._l = Object.create(null); return this; }
        emit(ev, ...args) {
            const arr = (this._l[ev] || []).slice();
            for (const fn of arr) { try { fn(...args); } catch (e) { console.error(e); } }
            return arr.length > 0;
        }
        addListener(ev, fn) { return this.on(ev, fn); }
        listeners(ev) { return (this._l[ev] || []).slice(); }
        listenerCount(ev) { return (this._l[ev] || []).length; }
    }

    // ---- electron stubs ---------------------------------------------------
    // Static placeholder data for systeminformation calls. The UI renders
    // fully (charts, labels, tables) but numbers are inert / dashes.
    function fakeSystemInformation(prop, args) {
        switch (prop) {
            case "cpu":
                return {
                    manufacturer: "Web", brand: "Browser CPU",
                    cores: 8, physicalCores: 4,
                    speed: 0, speedMin: 0, speedMax: 0,
                    vendor: "", family: "", model: "", stepping: "", revision: "",
                    voltage: "", cache: { l1d: 0, l1i: 0, l2: 0, l3: 0 },
                };
            case "currentLoad":
                return {
                    avgLoad: 0, currentLoad: 0, currentLoadUser: 0,
                    currentLoadSystem: 0, currentLoadNice: 0, currentLoadIdle: 100,
                    currentLoadIrq: 0, rawCurrentLoad: 0,
                    cpus: Array.from({ length: 8 }, () => ({
                        load: 0, loadUser: 0, loadSystem: 0, loadNice: 0, loadIdle: 100, loadIrq: 0,
                    })),
                };
            case "cpuTemperature":
                return { main: 0, cores: [0, 0, 0, 0], max: 0 };
            case "mem":
                return {
                    total: 0, free: 0, used: 0, active: 0, available: 0,
                    buffers: 0, cached: 0, slab: 0, buffcache: 0,
                    swaptotal: 0, swapused: 0, swapfree: 0,
                };
            case "processes":
                return { all: 0, running: 0, blocked: 0, sleeping: 0, unknown: 0, list: [] };
            case "system":
                return { manufacturer: "Web", model: "Browser", version: "", serial: "", uuid: "", sku: "" };
            case "chassis":
                return { manufacturer: "Web", model: "Browser", type: "Other", version: "", serial: "", assetTag: "" };
            case "battery":
                return { hasbattery: false, cycleCount: 0, isCharging: false, voltage: 0, capacityUnit: "", maxCapacity: 0, currentCapacity: 0, percent: 0, timeRemaining: 0, acConnected: true, type: "", model: "", manufacturer: "" };
            case "networkInterfaces":
                return [{ iface: "web0", ifaceName: "web0", default: true, ip4: "0.0.0.0", ip4subnet: "", ip6: "", mac: "00:00:00:00:00:00", internal: false, virtual: false, operstate: "up", type: "wireless", duplex: "", mtu: 1500, speed: 0, dhcp: true, dnsSuffix: "", ieee8021xAuth: "", ieee8021xState: "", carrierChanges: 0 }];
            case "networkStats":
                return [{ iface: "web0", operstate: "up", rx_bytes: 0, rx_dropped: 0, rx_errors: 0, tx_bytes: 0, tx_dropped: 0, tx_errors: 0, rx_sec: 0, tx_sec: 0, ms: Date.now() }];
            case "networkConnections":
                return [];
            case "blockDevices":
                return [];
            case "fsSize":
                return [];
            case "osInfo":
                return { platform: "darwin", distro: "macOS", release: "0", codename: "", kernel: "0", arch: "x64", hostname: "web", logofile: "", serial: "", build: "", servicepack: "", uefi: false };
            case "versions":
                return { kernel: "0", openssl: "", node: "", npm: "", pm2: "" };
            case "time":
                return { current: Date.now(), uptime: 0, timezone: "", timezoneName: "" };
            case "users":
                return [];
            default:
                return {};
        }
    }

    const ipcRenderer = new EventEmitter();
    ipcRenderer.send = function (channel, ...args) {
        // The renderer expects async-reply handshakes on a few channels.
        // We auto-reply so the UI keeps moving without a real backend.
        switch (channel) {
            case "getThemeOverride":
            case "getKbOverride":
                // Reply on next tick with null → use the value from settings.json
                setTimeout(() => ipcRenderer.emit(channel, {}, null), 0);
                break;
            case "systeminformation-call": {
                const [prop, id] = args; // (propName, id, ...rest)
                const reply = fakeSystemInformation(prop, args.slice(2));
                setTimeout(() => ipcRenderer.emit("systeminformation-reply-" + id, {}, reply), 0);
                break;
            }
            default:
                // swallow everything else (logs, resize, etc.)
                break;
        }
    };
    ipcRenderer.sendSync = () => null;
    ipcRenderer.invoke = () => Promise.resolve(null);
    ipcRenderer.postMessage = () => {};

    const ipcMain = new EventEmitter();
    ipcMain.handle = () => {};

    const fakeApp = {
        getPath: (key) => {
            if (key === "userData") return USER_DATA;
            if (key === "home") return "/";
            if (key === "temp") return "/tmp";
            if (key === "documents") return "/";
            return "/";
        },
        getVersion: () => "2.2.8-web",
        getName: () => "eDEX-UI",
        focus: () => {},
        quit: () => {},
        isReady: () => true,
        on: () => {},
    };

    const fakeScreen = {
        getPrimaryDisplay: () => ({
            bounds: { x: 0, y: 0, width: window.innerWidth, height: window.innerHeight },
            workArea: { x: 0, y: 0, width: window.innerWidth, height: window.innerHeight },
            scaleFactor: 1,
        }),
        getAllDisplays: () => [fakeScreen.getPrimaryDisplay()],
    };

    const fakeBrowserWindow = class {
        constructor() {}
        static getFocusedWindow() { return fakeBrowserWindow._w; }
        static getAllWindows() { return [fakeBrowserWindow._w]; }
        on() {} once() {} loadURL() {} show() {} hide() {} close() {} reload() {} focus() {}
        isFocused() { return true; } isVisible() { return true; } isFullScreen() { return false; }
        setFullScreen() {} setBounds() {} getBounds() { return { x: 0, y: 0, width: 0, height: 0 }; }
        webContents = new EventEmitter();
    };
    fakeBrowserWindow._w = new fakeBrowserWindow();

    const fakeProcess = {
        argv: ["web"],
        platform: "darwin",
        env: {},
        cwd: () => "/",
        versions: { electron: "12.0.0", node: "14.0.0", chrome: "89.0.0" },
        getSystemVersion: () => "0",
        nextTick: (fn, ...args) => setTimeout(() => fn(...args), 0),
        on: () => {},
    };

    const electronShim = {
        ipcRenderer,
        ipcMain,
        remote: null, // filled below
        shell: {
            openExternal: (u) => { window.open(u, "_blank"); return Promise.resolve(); },
            openPath: () => Promise.resolve(""),
            showItemInFolder: () => {},
        },
        clipboard: {
            readText: () => {
                try { return window.navigator.clipboard && window.navigator.clipboard.readText ? "" : ""; }
                catch (e) { return ""; }
            },
            writeText: (t) => { try { navigator.clipboard && navigator.clipboard.writeText(t); } catch (e) {} },
        },
        nativeImage: { createFromPath: () => ({}), createEmpty: () => ({}) },
        dialog: { showMessageBox: () => Promise.resolve({ response: 0 }) },
        app: fakeApp,
        BrowserWindow: fakeBrowserWindow,
        screen: fakeScreen,
        process: fakeProcess,
    };

    // Permissive stub: any property/call returns another permissive stub,
    // so chained accesses like `remote.globalShortcut.unregisterAll()` never throw.
    function makePermissiveStub(label) {
        const fn = function () { return makePermissiveStub(label + "()"); };
        return new Proxy(fn, {
            get: (_t, k) => {
                if (k === Symbol.toPrimitive) return () => "";
                if (k === "then" || k === "Symbol(Symbol.toPrimitive)") return undefined;
                return makePermissiveStub(label + "." + String(k));
            },
            apply: () => makePermissiveStub(label + "()"),
            construct: () => ({}),
        });
    }

    const remoteBase = {
        app: fakeApp,
        process: fakeProcess,
        screen: fakeScreen,
        BrowserWindow: fakeBrowserWindow,
        shell: electronShim.shell,
        clipboard: electronShim.clipboard,
        dialog: electronShim.dialog,
        getCurrentWindow: () => fakeBrowserWindow._w,
        getCurrentWebContents: () => fakeBrowserWindow._w.webContents,
        getGlobal: (n) => window[n],
        require: (m) => requireShim(m),
        globalShortcut: {
            register: () => true,
            registerAll: () => {},
            unregister: () => {},
            unregisterAll: () => {},
            isRegistered: () => false,
        },
        Menu: { buildFromTemplate: () => ({ popup: () => {} }), setApplicationMenu: () => {} },
        MenuItem: class { constructor() {} },
        nativeTheme: { shouldUseDarkColors: true, on: () => {} },
        powerMonitor: { on: () => {} },
        net: { request: () => ({ on: () => {}, end: () => {} }) },
    };

    const remoteShim = new Proxy(remoteBase, {
        get: (t, k) => (k in t ? t[k] : makePermissiveStub("remote." + String(k))),
    });
    electronShim.remote = remoteShim;
    electronShim.webFrame = {
        setVisualZoomLevelLimits: () => {},
        setZoomLevel: () => {},
        getZoomLevel: () => 0,
        setZoomFactor: () => {},
        getZoomFactor: () => 1,
    };
    electronShim.contextBridge = { exposeInMainWorld: () => {} };

    // ---- native / backend stubs -------------------------------------------
    const nodePtyStub = {
        spawn: () => {
            const pty = new EventEmitter();
            pty.write = () => {};
            pty.resize = () => {};
            pty.kill = () => {};
            pty.pid = 0;
            return pty;
        },
    };

    const wsStub = { Server: class { constructor() { /* noop */ } on() {} close() {} } };

    const childProcessStub = {
        exec: (_cmd, _opts, cb) => { const c = typeof _opts === "function" ? _opts : cb; c && c(null, "", ""); return new EventEmitter(); },
        execSync: () => "",
        spawn: () => { const p = new EventEmitter(); p.stdout = new EventEmitter(); p.stderr = new EventEmitter(); p.kill = () => {}; return p; },
        spawnSync: () => ({ status: 0, stdout: "", stderr: "" }),
        fork: () => new EventEmitter(),
    };

    // Source parses `new require("https").Agent(...)` weirdly; Agent must be
    // callable both with and without `new`. A plain function works for both.
    function HttpsAgent() { return this instanceof HttpsAgent ? this : {}; }
    HttpsAgent.prototype = {};
    const httpsStub = {
        get: (opts, cb) => {
            const req = new EventEmitter();
            req.end = () => {};
            req.abort = () => {};
            setTimeout(() => req.emit("error", new Error("https disabled in web build")), 0);
            return req;
        },
        Agent: HttpsAgent,
        request: () => httpsStub.get(),
    };

    const httpStub = httpsStub;
    function NetSocket() { return this instanceof NetSocket ? this : {}; }
    NetSocket.prototype = { connect: () => {}, on: () => {}, end: () => {}, destroy: () => {}, write: () => {} };
    const netStub = { Socket: NetSocket };

    const signaleStub = (() => {
        const m = (...args) => console.log(...args);
        m.info = (...args) => console.info(...args);
        m.warn = (...args) => console.warn(...args);
        m.error = (...args) => console.error(...args);
        m.success = (...args) => console.log("✓", ...args);
        m.pending = (...args) => console.log("⋯", ...args);
        m.debug = (...args) => console.debug(...args);
        m.log = m.info;
        m.Signale = class { constructor() { Object.assign(this, m); } };
        return m;
    })();

    const tailStub = { Tail: class { constructor() {} on() {} watch() {} unwatch() {} } };

    function emptyAsync() { return Promise.resolve({}); }

    const systeminformationStub = new Proxy({}, {
        get: () => (..._args) => Promise.resolve({}),
    });

    const geoliteStub = {
        downloadDbs: () => Promise.resolve(),
        open: () => Promise.resolve({ get: () => null }),
    };
    const maxmindStub = { open: () => Promise.resolve({ get: () => null }) };
    const shellEnvStub = () => Promise.resolve(Object.create(null));
    const whichStub = (cmd) => Promise.resolve(cmd);
    whichStub.sync = (cmd) => cmd;
    const usernameStub = () => Promise.resolve("user");
    usernameStub.sync = () => "user";

    // ---- require resolver -------------------------------------------------
    const moduleMap = {
        "path": pathShim,
        "fs": fsShim,
        "os": osShim,
        "events": { EventEmitter },
        "electron": electronShim,
        "@electron/remote": remoteShim,
        "@electron/remote/main": { initialize: () => {}, enable: () => {} },
        "node-pty": nodePtyStub,
        "ws": wsStub,
        "child_process": childProcessStub,
        "https": httpsStub,
        "http": httpStub,
        "net": netStub,
        "signale": signaleStub,
        "tail": tailStub,
        "systeminformation": systeminformationStub,
        "geolite2-redist": geoliteStub,
        "maxmind": maxmindStub,
        "shell-env": shellEnvStub,
        "which": whichStub,
        "username": usernameStub,
        "cluster": { isMaster: true, isWorker: false, fork: () => ({ on: () => {}, send: () => {} }), on: () => {}, setupMaster: () => {} },
        "util": {
            inherits: (ctor, superCtor) => { if (superCtor) Object.setPrototypeOf(ctor.prototype, superCtor.prototype); },
            format: (...a) => a.map(x => typeof x === "string" ? x : JSON.stringify(x)).join(" "),
            promisify: (fn) => (...args) => new Promise((res, rej) => fn(...args, (err, r) => err ? rej(err) : res(r))),
            inspect: (o) => JSON.stringify(o),
            types: { isPromise: (v) => v && typeof v.then === "function" },
            TextDecoder: window.TextDecoder, TextEncoder: window.TextEncoder,
        },
        "font-finder": {
            list: () => Promise.resolve([]),
            listVariants: () => Promise.resolve([]),
        },
        "stream": { Readable: class { on() {} pipe() {} }, Writable: class { on() {} write() {} end() {} } },
        "buffer": { Buffer: window.Buffer },
        "querystring": {
            stringify: (o) => new URLSearchParams(o).toString(),
            parse: (s) => Object.fromEntries(new URLSearchParams(s)),
        },
        "assert": Object.assign(function () {}, { ok: () => {}, strictEqual: () => {}, deepStrictEqual: () => {} }),
        "crypto": {
            randomBytes: (n) => { const a = new Uint8Array(n); (window.crypto || {}).getRandomValues && window.crypto.getRandomValues(a); return a; },
            createHash: () => ({ update() { return this; }, digest() { return ""; } }),
        },
        "url": {
            format: (o) => {
                if (typeof o === "string") return o;
                return (o.protocol || "file:") + "//" + (o.host || "") + (o.pathname || "");
            },
            parse: (s) => { try { return new URL(s); } catch (e) { return { href: s }; } },
            URL,
        },
        "mime-types": {
            lookup: (p) => {
                p = String(p || "").toLowerCase();
                if (p.endsWith(".html")) return "text/html";
                if (p.endsWith(".json")) return "application/json";
                if (p.endsWith(".js")) return "text/javascript";
                if (p.endsWith(".css")) return "text/css";
                if (p.endsWith(".png")) return "image/png";
                if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
                if (p.endsWith(".svg")) return "image/svg+xml";
                if (p.endsWith(".pdf")) return "application/pdf";
                if (p.endsWith(".md") || p.endsWith(".txt")) return "text/plain";
                return false;
            },
            contentType: function (p) { const t = this.lookup(p); return t ? t + "; charset=utf-8" : false; },
            extension: () => false,
            charset: () => "UTF-8",
        },
    };

    // xterm + addons + smoothie + howler are loaded as UMD via <script>; expose through require()
    const umdDeferred = () => {
        // xterm's UMD iterates its exports onto window; reconstruct the module object.
        moduleMap["xterm"] = { Terminal: window.Terminal };
        // Addon UMDs assign the ENTIRE module export object to a single global
        // (e.g. window.FitAddon = { FitAddon: class }). Pass it through as-is.
        moduleMap["xterm-addon-attach"] = window.AttachAddon || {};
        moduleMap["xterm-addon-fit"] = window.FitAddon || {};
        moduleMap["xterm-addon-ligatures"] = window.LigaturesAddon || {};
        moduleMap["xterm-addon-webgl"] = window.WebglAddon || {};
        moduleMap["smoothie"] = { TimeSeries: window.TimeSeries, SmoothieChart: window.SmoothieChart };
        moduleMap["howler"] = { Howl: window.Howl, Howler: window.Howler };
        if (window.__edexBundle) {
            for (const k of Object.keys(window.__edexBundle)) {
                moduleMap[k] = window.__edexBundle[k];
            }
        }
    };

    function resolveRelative(name) {
        // Electron renderer resolves `./...` relative to the HTML file (src/).
        // Mimic that: rewrite `./foo` → `src/foo`.
        if (name.startsWith("./")) return SRC_DIR + "/" + name.slice(2);
        if (name.startsWith("../")) return pathShim.normalize(SRC_DIR + "/" + name);
        return name;
    }

    function requireShim(name) {
        if (typeof name !== "string") return {};

        // JSON files accessed by absolute or relative path
        if (name.endsWith(".json")) {
            const resolved = resolveRelative(name);
            try {
                const txt = fsShim.readFileSync(resolved);
                return JSON.parse(txt);
            } catch (e) {
                console.warn("require() json miss:", name, "->", resolved, e.message);
                return {};
            }
        }

        // Relative JS file inside src/ (e.g. ./classes/..., ./assets/icons/...)
        if (name.startsWith("./") || name.startsWith("../")) {
            if (name.endsWith("file-icons-match.js")) {
                return window.__edexFileIconsMatcher || function () { return null; };
            }
            if (name.endsWith(".js")) {
                console.warn("require() js miss:", name);
                return {};
            }
        }

        if (moduleMap[name]) return moduleMap[name];

        // Unknown: return a permissive stub that logs & tolerates chained calls
        console.warn("require() stub for unknown module:", name);
        const stub = function () { return stub; };
        return new Proxy(stub, {
            get: (_t, k) => (k === "then" ? undefined : stub),
            apply: () => stub,
        });
    }

    // The terminal class opens `ws://127.0.0.1:<port>/` and throws on error.
    // Replace WebSocket with a quiet stub so the error modal never pops up.
    const RealWebSocket = window.WebSocket;
    window.WebSocket = function QuietWebSocket(url, protocols) {
        if (typeof url === "string" && /^wss?:\/\/127\.0\.0\.1:/.test(url)) {
            const s = new EventEmitter();
            s.url = url; s.readyState = 0; s.CONNECTING = 0; s.OPEN = 1; s.CLOSING = 2; s.CLOSED = 3;
            s.protocol = ""; s.bufferedAmount = 0; s.extensions = "";
            s.send = () => {}; s.close = () => { s.readyState = 3; };
            s.addEventListener = (ev, fn) => s.on(ev, fn);
            s.removeEventListener = (ev, fn) => s.off(ev, fn);
            Object.defineProperty(s, "onopen", { set(fn) { this._onopen = fn; } });
            Object.defineProperty(s, "onerror", { set(fn) { this._onerror = fn; } });
            Object.defineProperty(s, "onclose", { set(fn) { this._onclose = fn; } });
            Object.defineProperty(s, "onmessage", { set(fn) { this._onmessage = fn; } });
            return s;
        }
        return new RealWebSocket(url, protocols);
    };
    window.WebSocket.prototype = RealWebSocket.prototype;
    ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach(
        (k, i) => { window.WebSocket[k] = i; }
    );

    window.global = window;
    window.process = fakeProcess;
    window.__dirname = SRC_DIR;
    window.__filename = SRC_DIR + "/_renderer.js";
    window.Buffer = window.Buffer || { from: (x) => x, isBuffer: () => false };
    window.require = requireShim;
    // Each class file ends with `module.exports = {...}`. A shared writable
    // module object keeps those assignments from throwing; the classes are
    // referenced by their global names so the actual exports are discarded.
    // We deliberately do NOT set window.exports — some UMD modules (smoothie)
    // fall through to the global object when `typeof exports === 'undefined'`,
    // which is how they publish TimeSeries / SmoothieChart to window.
    window.module = { exports: {} };
    window.__edexShim = {
        path: pathShim, fs: fsShim, os: osShim, primeCache, primeDir,
        finalizeUMD: umdDeferred,
    };
})();
