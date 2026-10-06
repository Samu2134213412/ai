/* Handy-Zugang: ein zweiter Server im WLAN, den man per QR-Code öffnet.
   - liefert dieselbe Oberfläche aus (läuft dann im Handy-Browser mit eigenem lokalen Backend),
   - leitet NUR /ollama/api/tags und /ollama/api/chat an das Ollama dieses PCs weiter, damit Ollama
     selbst nicht im Netz freigegeben werden muss,
   - ist durch ein zufälliges Token (Cookie) geschützt und nur an, solange man es einschaltet. */
const http = require("node:http");
const os = require("node:os");
const crypto = require("node:crypto");
const { serveFile } = require("./static-server.js");

const MAX_BODY = 40 * 1024 * 1024;          // Seitenbilder
const PROXY = { "GET /ollama/api/tags": "/api/tags", "POST /ollama/api/chat": "/api/chat" };

/* IPv4-Adressen des PCs im lokalen Netz, private Bereiche zuerst. */
function lanAddresses(interfaces = os.networkInterfaces()) {
  const rank = (ip) => (ip.startsWith("192.168.") ? 0 : ip.startsWith("10.") ? 1 : /^172\.(1[6-9]|2\d|3[01])\./.test(ip) ? 2 : 3);
  return Object.values(interfaces).flat().filter((i) => i && i.family === "IPv4" && !i.internal)
    .map((i) => i.address).sort((a, b) => rank(a) - rank(b));
}

function cookieToken(req) {
  const m = /(?:^|;\s*)tutor_token=([\w-]+)/.exec(req.headers.cookie || "");
  return m ? m[1] : "";
}
const safeEqual = (a, b) => a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));

function createPhoneServer({ wwwDir, ollamaTarget = "http://127.0.0.1:11434", port = 8766, addresses = lanAddresses }) {
  const root = require("node:path").resolve(wwwDir);
  let server = null, token = "", info = null;
  const target = new URL(ollamaTarget);

  const text = (res, code, body, headers = {}) => {
    res.writeHead(code, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", ...headers });
    res.end(body);
  };
  const json = (res, code, obj) => text(res, code, JSON.stringify(obj), { "Content-Type": "application/json; charset=utf-8" });

  function proxy(req, res, upstreamPath) {
    let size = 0;
    const up = http.request({ hostname: target.hostname, port: target.port || 80, path: upstreamPath, method: req.method,
      headers: { "Content-Type": req.headers["content-type"] || "application/json", ...(req.headers["content-length"] ? { "Content-Length": req.headers["content-length"] } : {}) } }, (r) => {
      res.writeHead(r.statusCode, { "Content-Type": r.headers["content-type"] || "application/json", "Cache-Control": "no-store" });
      r.pipe(res);                                    // Streaming bleibt erhalten
    });
    up.on("error", () => { if (!res.headersSent) json(res, 502, { error: "Ollama ist auf dem PC nicht erreichbar." }); else res.end(); });
    res.on("close", () => up.destroy());              // Handy weg → Anfrage an Ollama abbrechen
    req.on("data", (c) => { size += c.length; if (size > MAX_BODY) { req.destroy(); up.destroy(); } });
    req.pipe(up);
  }

  function handle(req, res) {
    const url = new URL(req.url, "http://x");
    const given = url.searchParams.get("t") || "";
    if (given && safeEqual(given, token)) {           // QR-Code geöffnet → Cookie setzen, Token aus der URL entfernen
      url.searchParams.delete("t");
      const back = url.pathname === "/" ? "/index.html" : url.pathname;
      const qs = new URLSearchParams(url.searchParams); qs.set("local", "1"); qs.set("phone", "1");
      res.writeHead(302, { Location: `${back}?${qs}`, "Set-Cookie": `tutor_token=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400`, "Cache-Control": "no-store" });
      return res.end();
    }
    const c = cookieToken(req);
    if (!c || !safeEqual(c, token)) return text(res, 401, "Zugriff nur über den QR-Code des Tutors (am PC: Einstellungen → Handy verbinden).");
    const key = `${req.method} ${url.pathname}`;
    if (url.pathname.startsWith("/ollama/")) {
      return PROXY[key] ? proxy(req, res, PROXY[key]) : json(res, 403, { error: "Nicht erlaubt" });
    }
    if (req.method !== "GET" && req.method !== "HEAD") return json(res, 405, { error: "Nicht erlaubt" });
    if (url.pathname.startsWith("/api/")) return json(res, 404, { error: "Unbekannt" });
    serveFile(root, url.pathname, req, res);
  }

  return {
    get running() { return !!server; },
    get info() { return info; },
    /* Startet den Server und liefert { url, ip, port, token }. Läuft er schon, kommen dieselben Daten zurück. */
    async start() {
      if (server) return info;
      const ips = addresses();
      if (!ips.length) throw new Error("Kein WLAN/LAN gefunden. Der PC muss im selben Netz wie das Handy sein.");
      token = crypto.randomBytes(12).toString("base64url");
      const s = http.createServer(handle);
      await new Promise((resolve, reject) => {
        const tryPort = (p, retry) => {
          s.once("error", (e) => (e.code === "EADDRINUSE" && retry ? tryPort(0, false) : reject(e)));
          s.listen(p, "0.0.0.0", resolve);
        };
        tryPort(port, true);
      });
      server = s;
      const actual = s.address().port;
      info = { ip: ips[0], port: actual, token, url: `http://${ips[0]}:${actual}/?t=${token}`, all: ips };
      return info;
    },
    async stop() {
      const s = server; server = null; info = null; token = "";
      if (s) await new Promise((r) => { s.close(r); s.closeAllConnections(); });
    },
  };
}
module.exports = { createPhoneServer, lanAddresses };
