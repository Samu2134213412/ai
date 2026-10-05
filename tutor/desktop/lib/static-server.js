/* Lokaler Server (nur 127.0.0.1): liefert die Oberfläche aus und bedient die Browser-Erweiterung
   „Tutor Fokus“ (GET /api/focus, POST /api/focus/start|stop) – dieselbe API wie web.py. */
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".md": "text/markdown; charset=utf-8",
  ".webmanifest": "application/manifest+json", ".png": "image/png", ".json": "application/json" };
const EXT_ORIGIN = /^(chrome|moz|safari-web)-extension:\/\//;

function createStaticServer({ wwwDir, focus, onCommand, port = 8765 }) {
  const root = path.resolve(wwwDir);
  let actualPort = port;

  const json = (res, code, obj, headers = {}) => {
    const body = JSON.stringify(obj);
    res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body),
      "Cache-Control": "no-store", ...headers });
    res.end(body);
  };
  const hostOk = (req) => {                       // Schutz vor DNS-Rebinding
    const h = (req.headers.host || "").toLowerCase();
    return h === `127.0.0.1:${actualPort}` || h === `localhost:${actualPort}`;
  };

  const server = http.createServer((req, res) => {
    if (!hostOk(req)) return json(res, 421, { error: "Falscher Host" });
    const url = new URL(req.url, "http://localhost");
    const origin = req.headers.origin || "";
    const extension = EXT_ORIGIN.test(origin);
    const cors = extension ? { "Access-Control-Allow-Origin": origin, Vary: "Origin" } : {};

    if (req.method === "OPTIONS") {
      res.writeHead(204, extension ? { ...cors, "Access-Control-Allow-Headers": "Content-Type, X-Tutor-Token",
        "Access-Control-Allow-Methods": "GET, POST" } : {});
      return res.end();
    }

    if (url.pathname.startsWith("/api/")) {
      if (url.pathname === "/api/focus" && req.method === "GET") return json(res, 200, focus.info(), cors);
      if (req.method === "POST" && (url.pathname === "/api/focus/start" || url.pathname === "/api/focus/stop")) {
        // Nur Erweiterung oder die App selbst (Origin passt zum Host) – keine fremden Webseiten.
        const same = origin && new URL(origin).host === req.headers.host;
        if (origin && !extension && !same) return json(res, 403, { error: "Falscher Origin" });
        let body = "";
        req.on("data", (c) => { body += c; if (body.length > 4096) req.destroy(); });
        req.on("end", () => {
          let data = {};
          try { data = JSON.parse(body || "{}"); } catch (e) { return json(res, 400, { error: "Ungültiges JSON" }, cors); }
          if (url.pathname.endsWith("/start")) {
            const minutes = parseInt(data.minutes, 10) || 25;
            if (minutes < 1 || minutes > 240) return json(res, 400, { error: "Ungültige Minuten." }, cors);
            focus.start(minutes); onCommand && onCommand({ type: "start", minutes });
          } else { focus.stop(); onCommand && onCommand({ type: "stop" }); }
          json(res, 200, { ok: true, focus: focus.info() }, cors);
        });
        return;
      }
      return json(res, 404, { error: "Unbekannt" });
    }

    if (req.method !== "GET" && req.method !== "HEAD") return json(res, 405, { error: "Nicht erlaubt" });
    let rel;
    try { rel = decodeURIComponent(url.pathname); } catch (e) { return json(res, 400, { error: "Ungültiger Pfad" }); }
    if (rel === "/") rel = "/index.html";
    const file = path.resolve(root, "." + rel);
    if (file !== root && !file.startsWith(root + path.sep)) return json(res, 403, { error: "Verboten" });
    fs.readFile(file, (err, data) => {
      if (err) return json(res, 404, { error: "Nicht gefunden" });
      res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
      res.end(req.method === "HEAD" ? undefined : data);
    });
  });

  return {
    server,
    /* Startet auf dem Wunschport; ist er belegt, auf einem freien. Gibt den Port zurück. */
    listen() {
      return new Promise((resolve, reject) => {
        const tryPort = (p, retry) => {
          server.once("error", (e) => (e.code === "EADDRINUSE" && retry ? tryPort(0, false) : reject(e)));
          server.listen(p, "127.0.0.1", () => { actualPort = server.address().port; resolve(actualPort); });
        };
        tryPort(port, true);
      });
    },
    close: () => new Promise((r) => { server.close(r); server.closeAllConnections(); }),
  };
}
module.exports = { createStaticServer };
