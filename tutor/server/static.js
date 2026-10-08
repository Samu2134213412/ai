/* Statische Auslieferung der Oberfläche (Pfad-Tricks werden abgewiesen). */
const fs = require("node:fs");
const path = require("node:path");

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".md": "text/markdown; charset=utf-8",
  ".webmanifest": "application/manifest+json", ".png": "image/png", ".json": "application/json", ".wasm": "application/wasm" };

function serveFile(root, pathname, req, res) {
  const fail = (code, error) => {
    const body = JSON.stringify({ error });
    res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body) });
    res.end(body);
  };
  let rel;
  try { rel = decodeURIComponent(pathname); } catch (e) { return fail(400, "Ungültiger Pfad"); }
  if (rel === "/") rel = "/index.html";
  const file = path.resolve(root, "." + rel);
  if (file !== root && !file.startsWith(root + path.sep)) return fail(403, "Verboten");
  fs.readFile(file, (err, data) => {
    if (err) return fail(404, "Nicht gefunden");
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream",
      "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
    res.end(req.method === "HEAD" ? undefined : data);
  });
}
module.exports = { serveFile };
