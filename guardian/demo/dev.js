#!/usr/bin/env node
// Dependency-free static file server with live reload for the Guardian
// demo. Deliberately uses only Node's built-in modules (http/fs/path/net)
// instead of a third-party dev-server package: this is a security project,
// and a static single-file demo doesn't warrant pulling in an unmaintained
// package with a large, partly-deprecated dependency tree just to serve it.
//
// Picks the first free port from 3000 upward instead of failing when 3000
// is already taken, and never auto-opens a browser tab/window, per the
// project's "no uncontrolled new windows" preview requirement.

const http = require("http");
const fs = require("fs");
const path = require("path");
const net = require("net");

const ROOT = __dirname;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

// Injected only into HTML responses: opens a Server-Sent-Events connection
// and reloads the page whenever the server notices a file change.
const RELOAD_SCRIPT = `
<script>
  (() => {
    try {
      const es = new EventSource("/__livereload");
      es.onmessage = () => location.reload();
    } catch (_) { /* live reload is a convenience, not required */ }
  })();
</script>`;

function isPortFree(port) {
  return new Promise((resolve) => {
    const tester = net
      .createServer()
      .once("error", () => resolve(false))
      .once("listening", () => tester.once("close", () => resolve(true)).close())
      .listen(port, "127.0.0.1");
  });
}

async function findFreePort(start, tries = 20) {
  for (let port = start; port < start + tries; port++) {
    if (await isPortFree(port)) return port;
  }
  throw new Error(`Kein freier Port im Bereich ${start}-${start + tries - 1} gefunden.`);
}

const reloadClients = new Set();

function notifyReload() {
  for (const res of reloadClients) res.write("data: reload\n\n");
}

let watchTimer = null;
try {
  fs.watch(ROOT, (_event, filename) => {
    if (!filename) return;
    // Debounce: editors/save actions often fire several events per save.
    clearTimeout(watchTimer);
    watchTimer = setTimeout(notifyReload, 100);
  });
} catch (err) {
  console.warn(`Live-Reload nicht verfügbar (fs.watch fehlgeschlagen): ${err.message}`);
}

function serveFile(res, filePath) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }
    const ext = path.extname(filePath);
    const contentType = MIME[ext] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": contentType });
    res.end(ext === ".html" ? data.toString("utf-8") + RELOAD_SCRIPT : data);
  });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");

  if (url.pathname === "/__livereload") {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.write("\n");
    reloadClients.add(res);
    req.on("close", () => reloadClients.delete(res));
    return;
  }

  let reqPath = decodeURIComponent(url.pathname);
  if (reqPath === "/") reqPath = "/index.html";
  const resolved = path.normalize(path.join(ROOT, reqPath));
  if (!resolved.startsWith(ROOT)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }
  serveFile(res, resolved);
});

async function main() {
  const port = await findFreePort(3000);
  server.listen(port, "127.0.0.1", () => {
    console.log(`Guardian Demo läuft: http://localhost:${port}`);
    console.log("Änderungen an index.html werden automatisch im Browser nachgeladen.");
  });
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
