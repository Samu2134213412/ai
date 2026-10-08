/* Klassen-Pool: Jedes Gerät mit Tutor-App und Ollama stellt seine Rechenleistung den anderen im selben Netz zur
   Verfügung und nutzt dafür deren Leistung mit. Es wird kein Modell zerteilt – jede Anfrage läuft komplett auf
   EINEM Gerät (dem freien, das das Modell hat). So bekommen alle eine Antwort, auch wenn ein Gerät allein zu
   schwach oder gerade besetzt ist.

   - Entdeckung: kurzer UDP-Rundruf alle paar Sekunden („ich bin da, das sind meine Modelle“), signiert mit dem
     Klassencode. Wer den Code nicht kennt, wird ignoriert.
   - Arbeiter: nimmt nur /api/tags und /api/chat an, nur von Geräten, die selbst beitragen, nur mit gültiger
     Signatur und aktuellem Zeitstempel, höchstens `maxJobs` Anfragen gleichzeitig.
   - Lokaler Verteiler: spricht wie Ollama (127.0.0.1) – der Tutor-Server bekommt ihn als „Ollama-Adresse“. */
const http = require("node:http");
const crypto = require("node:crypto");
const dgram = require("node:dgram");

const POOL_PORT = 8767;
const PEER_TTL = 20000, SKEW = 5 * 60 * 1000, MAX_BODY = 16 * 1024 * 1024;
const OPTION_KEYS = new Set(["temperature", "num_predict", "num_ctx", "top_p", "top_k", "seed", "repeat_penalty", "stop"]);
const BODY_KEYS = new Set(["model", "messages", "stream", "options", "keep_alive", "format"]);

const hmac = (key, text) => crypto.createHmac("sha256", key).update(text).digest("hex");
const same = (a, b) => { const x = Buffer.from(String(a)), y = Buffer.from(String(b)); return x.length === y.length && crypto.timingSafeEqual(x, y); };
const fullName = (m) => (m.includes(":") ? m : m + ":latest");

function validKey(key) { return typeof key === "string" && key.trim().length >= 8; }

/* Nur erlaubte Felder und Optionen an Ollama weiterreichen. */
function cleanChat(body) {
  const out = {};
  for (const k of Object.keys(body || {})) if (BODY_KEYS.has(k)) out[k] = body[k];
  if (typeof out.model !== "string" || !Array.isArray(out.messages)) throw new Error("Ungültige Anfrage.");
  if (out.options && typeof out.options === "object") {
    out.options = Object.fromEntries(Object.entries(out.options).filter(([k]) => OPTION_KEYS.has(k)));
    if (out.options.num_ctx > 16384) out.options.num_ctx = 16384;
  } else delete out.options;
  if (out.keep_alive !== undefined && typeof out.keep_alive !== "string" && typeof out.keep_alive !== "number") delete out.keep_alive;
  return out;
}

function readBody(req, limit = MAX_BODY) {
  return new Promise((resolve, reject) => {
    const chunks = []; let n = 0;
    req.on("data", (c) => { n += c.length; if (n > limit) { reject(new Error("Zu groß")); req.destroy(); } else chunks.push(c); });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function createPool(opts) {
  const { key, ollama = "http://127.0.0.1:11434", maxJobs = 1, port = POOL_PORT, announceMs = 5000,
    queueMs = 90000, bind = "0.0.0.0", broadcast = "255.255.255.255", udp = true, clock = Date.now, fetchImpl = fetch, onChange } = opts;
  if (!validKey(key)) throw new Error("Klassencode zu kurz (mindestens 8 Zeichen).");
  const id = opts.id || crypto.randomBytes(6).toString("hex");
  const jobsMax = Math.max(1, Math.min(4, parseInt(maxJobs, 10) || 1));
  const peers = new Map();                       // id -> { id, host, port, models, active, max, seen }
  const stats = { served: 0, used: 0 };
  let active = 0, localModels = [], localAt = 0, workerServer = null, proxyServer = null, sock = null, timer = null, workerPort = 0;
  const base = ollama.replace(/\/$/, "");

  const sig = (parts) => hmac(key, parts.join("|"));
  const signHeaders = (path) => { const ts = String(clock()); return { "X-Pool-Id": id, "X-Pool-Ts": ts, "X-Pool-Sig": sig([id, ts, path]) }; };

  async function refreshLocal(force) {
    if (!force && clock() - localAt < 8000) return localModels;
    try {
      const r = await fetchImpl(base + "/api/tags");
      const d = await r.json();
      localModels = (d.models || []).map((m) => m.model || m.name).filter(Boolean);
    } catch (e) { localModels = []; }
    localAt = clock();
    return localModels;
  }
  const contributing = () => localModels.length > 0;
  const live = () => [...peers.values()].filter((p) => clock() - p.seen < PEER_TTL);
  const changed = () => {
    if (onChange) onChange(info());
    if (sock) announce().catch(() => {});            // freie Plätze sofort melden, damit Wartende nicht bis zum nächsten Takt hängen
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ---------- Rundruf ---------- */

  function announcement() {
    const ts = String(clock());
    return Buffer.from(JSON.stringify({ v: 1, id, port: workerPort, ts, models: localModels, active, max: jobsMax,
      sig: sig([id, workerPort, ts, localModels.join(",")]) }));
  }
  function hear(msg, host) {
    let m; try { m = JSON.parse(msg.toString("utf8")); } catch (e) { return false; }
    if (!m || m.v !== 1 || typeof m.id !== "string" || m.id === id || !Number.isInteger(m.port) || !Array.isArray(m.models)) return false;
    if (Math.abs(clock() - Number(m.ts)) > SKEW) return false;
    if (!same(m.sig, sig([m.id, m.port, m.ts, m.models.join(",")]))) return false;
    const known = peers.has(m.id);
    peers.set(m.id, { id: m.id, host, port: m.port, models: m.models.map(String).slice(0, 64), active: Number(m.active) || 0,
      max: Math.max(1, Number(m.max) || 1), seen: clock() });
    if (!known) changed();
    return true;
  }
  async function announce() {
    await refreshLocal();
    if (!contributing() || !sock) return;
    sock.send(announcement(), port, broadcast, () => { /* Netz weg: nächster Takt */ });
  }

  /* ---------- Arbeiter (nimmt Anfragen anderer Geräte an) ---------- */

  function authorize(req, path) {
    const pid = req.headers["x-pool-id"], ts = req.headers["x-pool-ts"], s = req.headers["x-pool-sig"];
    if (!pid || !ts || !s || Math.abs(clock() - Number(ts)) > 60000) return false;
    if (!same(s, sig([pid, ts, path]))) return false;
    const p = peers.get(pid);                                   // nur Geräte, die selbst beitragen
    return !!p && clock() - p.seen < PEER_TTL;
  }
  const send = (res, code, obj) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };

  async function workerHandle(req, res) {
    const path = (req.url || "").split("?")[0];
    if (!["/pool/tags", "/pool/chat"].includes(path) || !authorize(req, path)) return send(res, 403, { error: "Kein Zugriff" });
    if (path === "/pool/tags") return send(res, 200, { models: (await refreshLocal()).map((m) => ({ model: m })) });
    if (active >= jobsMax) return send(res, 429, { error: "Besetzt" });
    let body;
    try { body = cleanChat(JSON.parse(await readBody(req))); } catch (e) { return send(res, 400, { error: e.message }); }
    if (!(await refreshLocal()).map(fullName).includes(fullName(body.model))) return send(res, 404, { error: "Modell nicht installiert" });
    active++; stats.served++; changed();
    const ctl = new AbortController();
    res.on("close", () => ctl.abort());
    try {
      const r = await fetchImpl(base + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal });
      res.writeHead(r.status, { "Content-Type": r.headers.get("content-type") || "application/x-ndjson" });
      if (r.body) for await (const chunk of r.body) res.write(chunk);
      res.end();
    } catch (e) { if (!res.headersSent) send(res, 502, { error: "Ollama nicht erreichbar" }); else res.end(); }
    finally { active--; changed(); }
  }

  /* ---------- Auswahl des Geräts ---------- */

  function candidates(model) {
    const want = fullName(model), list = [];
    if (localModels.map(fullName).includes(want) && active < jobsMax) list.push({ self: true, load: active / jobsMax, id });
    for (const p of live()) if (p.models.map(fullName).includes(want) && p.active < p.max) list.push({ self: false, load: p.active / p.max, peer: p, id: p.id });
    return list.sort((a, b) => a.load - b.load || (b.self ? 1 : 0) - (a.self ? 1 : 0) || (a.id < b.id ? -1 : 1));
  }
  const allModels = () => [...new Set([...localModels, ...live().flatMap((p) => p.models)].map(fullName))];

  /* ---------- Lokaler Verteiler (Ollama-Schnittstelle) ---------- */

  async function proxyHandle(req, res) {
    const path = (req.url || "").split("?")[0];
    await refreshLocal();
    if (req.method === "GET" && path === "/api/tags") return send(res, 200, { models: allModels().map((m) => ({ name: m, model: m })) });
    if (req.method !== "POST" || path !== "/api/chat") return send(res, 404, { error: "Nicht unterstützt" });
    let body;
    try { body = cleanChat(JSON.parse(await readBody(req))); } catch (e) { return send(res, 400, { error: e.message }); }
    const ctl = new AbortController();
    res.on("close", () => ctl.abort());
    let order = candidates(body.model);
    const until = clock() + queueMs;                            // Warteschlange: nacheinander, sobald ein Gerät frei ist
    while (!order.length && allModels().includes(fullName(body.model)) && clock() < until && !ctl.signal.aborted) { await sleep(200); order = candidates(body.model); }
    if (ctl.signal.aborted) return res.end();
    if (!order.length) {
      const exists = allModels().includes(fullName(body.model));
      return send(res, exists ? 503 : 404, { error: exists ? "Alle Geräte im Pool sind lange besetzt – bitte gleich nochmal versuchen." : `model '${body.model}' not found` });
    }
    for (const c of order) {
      try {
        let r;
        if (c.self) { active++; changed(); r = await fetchImpl(base + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal }); }
        else { c.peer.active++; r = await fetchImpl(`http://${c.peer.host}:${c.peer.port}/pool/chat`, { method: "POST", signal: ctl.signal,
          headers: { "Content-Type": "application/json", ...signHeaders("/pool/chat") }, body: JSON.stringify(body) }); }
        try {
          if (!c.self && (r.status === 429 || r.status === 403 || r.status >= 500)) { c.peer.active = c.peer.max; continue; }   // nächster Kandidat
          if (!c.self) stats.used++;
          res.writeHead(r.status, { "Content-Type": r.headers.get("content-type") || "application/x-ndjson" });
          if (r.body) for await (const chunk of r.body) res.write(chunk);
          return res.end();
        } finally { if (c.self) { active--; changed(); } else c.peer.active = Math.max(0, c.peer.active - 1); }
      } catch (e) {
        if (ctl.signal.aborted) return res.end();
        if (!c.self) peers.delete(c.peer.id);                   // nicht erreichbar → raus, nächster Kandidat
        if (res.headersSent) return res.end();
      }
    }
    if (!res.headersSent) send(res, 503, { error: "Kein Gerät im Pool hat geantwortet." });
  }

  const guard = (fn) => (req, res) => fn(req, res).catch(() => { if (!res.headersSent) send(res, 500, { error: "Fehler" }); else res.end(); });
  const listen = (server, p, h) => new Promise((ok, fail) => { server.once("error", fail); server.listen(p, h, () => ok(server.address().port)); });

  function info() {
    return { id, running: !!workerServer, contributing: contributing(), active, max: jobsMax, served: stats.served, used: stats.used,
      localModels: [...localModels], peers: live().map((p) => ({ id: p.id, host: p.host, models: p.models, active: p.active, max: p.max })) };
  }

  return {
    id, info, hear, announcement, candidates,
    get proxyUrl() { return proxyServer ? `http://127.0.0.1:${proxyServer.address().port}` : null; },
    get workerPort() { return workerPort; },
    async start() {
      await refreshLocal(true);
      workerServer = http.createServer(guard(workerHandle));
      workerPort = await listen(workerServer, opts.workerPort === undefined ? 0 : opts.workerPort, bind);
      proxyServer = http.createServer(guard(proxyHandle));
      await listen(proxyServer, opts.proxyPort || 0, "127.0.0.1");
      if (udp) {
        sock = dgram.createSocket({ type: "udp4", reuseAddr: true });
        sock.on("message", (msg, rinfo) => hear(msg, rinfo.address));
        sock.on("error", () => { /* kein Netz */ });
        await new Promise((ok, fail) => { sock.once("error", fail); sock.bind(port, bind, () => { try { sock.setBroadcast(true); } catch (e) { /* ignorieren */ } ok(); }); });
      }
      await announce();
      timer = setInterval(() => { announce().catch(() => {}); }, announceMs); timer.unref();
      return { proxyUrl: this.proxyUrl, workerPort };
    },
    async stop() {
      clearInterval(timer);
      if (sock) { try { sock.close(); } catch (e) { /* schon zu */ } sock = null; }
      for (const s of [workerServer, proxyServer]) if (s) await new Promise((r) => { s.close(r); s.closeAllConnections(); });
      workerServer = proxyServer = null; peers.clear();
    },
    announce,
    refresh: () => refreshLocal(true),
  };
}
module.exports = { createPool, cleanChat, validKey, POOL_PORT };
