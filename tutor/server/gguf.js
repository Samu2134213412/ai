/* Modell-Datei (GGUF) eines in Ollama installierten Modells finden – damit Tablets im Pool das kleine Modell
   direkt vom PC laden können (kein Internet nötig). Ollama legt Modelle als Manifest + Blobs ab. */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function modelsDir(env = process.env) { return env.OLLAMA_MODELS || path.join(os.homedir(), ".ollama", "models"); }

function ggufPath(name, dir = modelsDir()) {
  const m = /^([a-z0-9][a-z0-9._-]{0,63})(?::([a-z0-9][a-z0-9._-]{0,63}))?$/i.exec(String(name || ""));
  if (!m) return null;                                           // kein Pfad-Trick möglich: nur einfache Namen
  const manifest = path.join(dir, "manifests", "registry.ollama.ai", "library", m[1], m[2] || "latest");
  let man; try { man = JSON.parse(fs.readFileSync(manifest, "utf8")); } catch (e) { return null; }
  const layer = (man.layers || []).find((l) => l.mediaType === "application/vnd.ollama.image.model");
  if (!layer || !/^sha256:[a-f0-9]{64}$/.test(layer.digest)) return null;
  const file = path.join(dir, "blobs", layer.digest.replace(":", "-"));
  try { return fs.statSync(file).isFile() ? file : null; } catch (e) { return null; }
}

/* Datei mit HEAD- und Range-Unterstützung ausliefern (wllama lädt in Stücken). */
function sendFile(req, res, file, type = "application/octet-stream") {
  const size = fs.statSync(file).size;
  const head = { "Content-Type": type, "Accept-Ranges": "bytes", "Cache-Control": "no-store" };
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
  if (range && (range[1] || range[2])) {
    let start = range[1] ? Number(range[1]) : size - Number(range[2]), end = range[1] && range[2] ? Number(range[2]) : size - 1;
    if (start < 0) start = 0; if (end >= size) end = size - 1;
    if (start > end) { res.writeHead(416, { "Content-Range": `bytes */${size}` }); return res.end(); }
    res.writeHead(206, { ...head, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
    if (req.method === "HEAD") return res.end();
    return fs.createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(200, { ...head, "Content-Length": size });
  if (req.method === "HEAD") return res.end();
  fs.createReadStream(file).pipe(res);
}
module.exports = { ggufPath, sendFile, modelsDir };
