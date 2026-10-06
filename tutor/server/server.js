/* Tutor-Server: die KI-Logik (Hinweisstufen, Modellwahl, Planer, Seiten lesen) als HTTP-API.
   Clients – Browser am Handy/iPad, PC-App, GoodNotes-Leiste – schicken Fragen hin und bekommen
   die Antwort zurück. Läuft auf dem eigenen PC und später unverändert auf einem echten Server.

   Eigene Daten je Person (Verlauf, Aufgaben, Einstellungen) in dataDir/users/<id>.json.
   Anmeldung ohne Passwort: ein einmaliger Kopplungs-Code wird per Link/QR auf dem Gerät eingelöst
   und gegen ein langes Geräte-Token getauscht (Cookie oder Header X-Tutor-Token). */
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { serveFile } = require("./static.js");
const { fileStorage, usersDb } = require("./store.js");

const MAX_BODY = 40 * 1024 * 1024;               // Seitenbilder
const STREAM_ROUTES = new Set(["/api/chat", "/api/giveup", "/api/new"]);
const EXT_ORIGIN = /^(chrome|moz|safari-web)-extension:\/\//;
const CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";   // ohne verwechselbare Zeichen

function lanAddresses(interfaces = os.networkInterfaces()) {
  const rank = (ip) => (ip.startsWith("192.168.") ? 0 : ip.startsWith("10.") ? 1 : /^172\.(1[6-9]|2\d|3[01])\./.test(ip) ? 2 : 3);
  return Object.values(interfaces).flat().filter((i) => i && i.family === "IPv4" && !i.internal)
    .map((i) => i.address).sort((a, b) => rank(a) - rank(b));
}

function createTutorServer(opts) {
  const { wwwDir, dataDir, ollama = "http://127.0.0.1:11434", host = "127.0.0.1", port = 8780,
    clock, fetchImpl, template, addresses = lanAddresses } = opts;
  const root = path.resolve(wwwDir);
  const promptText = template || [path.join(root, "prompts", "tutor.md"), path.join(root, "..", "prompts", "tutor.md")]
    .map((f) => { try { return require("node:fs").readFileSync(f, "utf8"); } catch (e) { return null; } }).find(Boolean);
  if (!promptText) throw new Error("prompts/tutor.md nicht gefunden");
  const { createBackend, TutorError } = require(path.join(root, "backend-local.js"));
  const users = usersDb(path.join(dataDir, "users.json"));
  const live = new Map();                        // id -> { backend, busy, shot }
  const pairings = new Map();                    // code -> { id, name, owner, expires }
  const listeners = [];                          // [{ server, host, port }]

  function userState(id) {
    if (!live.has(id)) {
      const backend = createBackend({ storage: fileStorage(path.join(dataDir, "users", id + ".json")), defaultHost: ollama,
        lockHost: true, clock, fetch: fetchImpl, template: promptText });
      live.set(id, { backend, busy: false, shot: { version: 0, data: null, type: "image/png" } });
    }
    return live.get(id);
  }

  let ownerId = users.owner();
  if (!ownerId) ownerId = users.add("Ich", { owner: true }).id;

  /* ---------- Kopplung ---------- */

  function createPairing({ name = "Lernende:r", forOwner = false, id = null, ttlMs = 10 * 60 * 1000 } = {}) {
    const code = Array.from(crypto.randomBytes(8), (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join("");
    pairings.set(code, { id: forOwner ? ownerId : id, name, expires: Date.now() + ttlMs });
    return code;
  }
  function redeem(code) {
    const p = pairings.get(String(code || "").toUpperCase().replace(/[^A-Z0-9]/g, ""));
    for (const [c, v] of pairings) if (v.expires < Date.now()) pairings.delete(c);
    if (!p || p.expires < Date.now()) return null;
    pairings.delete(String(code).toUpperCase().replace(/[^A-Z0-9]/g, ""));          // einmalig
    return users.add(p.name, { id: p.id || undefined });
  }

  /* ---------- Hilfen ---------- */

  const json = (res, code, obj, extra = {}) => {
    const body = JSON.stringify(obj);
    res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body),
      "Cache-Control": "no-store", ...extra });
    res.end(body);
  };
  const text = (res, code, body, extra = {}) => { res.writeHead(code, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", ...extra }); res.end(body); };
  const readBody = (req) => new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on("data", (c) => { size += c.length; if (size > MAX_BODY) { reject(new Error("Anfrage zu groß")); req.destroy(); } else chunks.push(c); });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
  const tokenOf = (req) => {
    const h = req.headers;
    const bearer = /^Bearer\s+(\S+)/i.exec(h.authorization || "");
    const cookie = /(?:^|;\s*)tutor_token=([\w-]+)/.exec(h.cookie || "");
    return h["x-tutor-token"] || (bearer && bearer[1]) || (cookie && cookie[1]) || "";
  };
  const cookieHeader = (token) => `tutor_token=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000`;
  const isLoopback = (req) => ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(req.socket.remoteAddress);

  /* Antwort streamen. Der SSE-Kopf geht erst beim ersten Stück raus, damit „Hinweise“ (z. B. Aufgeben mit
     Rückfrage) als normales JSON ankommen – wie beim Python-Server. */
  async function streamRoute(res, st, route, body) {
    if (st.busy) return json(res, 409, { error: "Der Tutor antwortet noch – kurz warten." });
    st.busy = true;
    let started = false, closed = false;
    res.on("close", () => { closed = true; });
    const send = (obj) => {
      if (closed) return;
      if (!started) { started = true; res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-store", "X-Accel-Buffering": "no" }); }
      res.write("data: " + JSON.stringify(obj) + "\n\n");
    };
    try {
      const result = await st.backend.stream(route, body, (piece) => send(piece === null ? { reset: true } : { t: piece }));
      if (started) send(result.done ? { done: true, state: result.state, route: result.route } : result);
      else if (!closed) json(res, 200, result);
    } catch (e) {
      send({ error: e.message, state: e.state });
    } finally {
      st.busy = false;
      if (started && !closed) res.end();
      else if (!started && !res.writableEnded && !closed) json(res, 500, { error: "Keine Antwort." });
    }
  }

  async function handle(req, res) {
    const url = new URL(req.url, "http://x");
    const p = url.pathname;
    const origin = req.headers.origin || "";
    const ext = EXT_ORIGIN.test(origin);

    // Clients mit Token im Header (iPad-App, Overlay, Add-ons) dürfen von anderen Ursprüngen aus zugreifen.
    // Cookies werden dabei nicht mitgeschickt (kein „credentials“) – ohne Token gibt es nichts zu lesen.
    if (req.method === "OPTIONS") {
      res.writeHead(204, { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type, X-Tutor-Token, Authorization",
        "Access-Control-Allow-Methods": "GET, POST", "Access-Control-Max-Age": "600" });
      return res.end();
    }
    if (origin) { const orig = res.writeHead.bind(res); res.writeHead = (code, headers) => orig(code, { "Access-Control-Allow-Origin": "*", ...(headers || {}) }); }

    // Kopplung per Link (?pair=CODE) oder per API (POST /api/pair {code})
    if (url.searchParams.has("pair")) {
      const dev = redeem(url.searchParams.get("pair"));
      if (!dev) return text(res, 401, "Dieser Kopplungs-Link ist abgelaufen oder schon benutzt. Am PC einen neuen QR-Code erzeugen.");
      return (res.writeHead(302, { Location: "/", "Set-Cookie": cookieHeader(dev.token), "Cache-Control": "no-store" }), res.end());
    }
    if (p === "/api/pair" && req.method === "POST") {
      let b = {}; try { b = JSON.parse((await readBody(req)).toString() || "{}"); } catch (e) { return json(res, 400, { error: "Ungültiges JSON" }); }
      const dev = redeem(b.code);
      if (!dev) return json(res, 401, { error: "Code ungültig oder abgelaufen." });
      return json(res, 200, { token: dev.token, id: dev.id });
    }

    // Anmeldung: Geräte-Token. Ausnahme: die lokale Erweiterung „Tutor Fokus“ darf auf demselben Rechner die Fokus-Routen nutzen.
    let id = users.find(tokenOf(req));
    const focusRoute = p === "/api/focus" || p === "/api/focus/start" || p === "/api/focus/stop";
    if (!id && ext && isLoopback(req) && focusRoute) id = ownerId;
    if (!id) return text(res, 401, "Nicht gekoppelt. Am PC den QR-Code / Kopplungs-Link öffnen (Tutor → Handy verbinden).");
    const cors = {};
    const st = userState(id);

    if (!p.startsWith("/api/")) {
      if (req.method !== "GET" && req.method !== "HEAD") return json(res, 405, { error: "Nicht erlaubt" });
      return serveFile(root, p, req, res);
    }

    // --- GET ---
    if (req.method === "GET") {
      if (p === "/api/plan.ics") {
        const { ics } = await st.backend.api("/api/plan.ics");
        return text(res, 200, ics, { "Content-Type": "text/calendar; charset=utf-8", "Content-Disposition": 'attachment; filename="lernplan.ics"' });
      }
      if (p === "/api/shot") return json(res, 200, { version: st.shot.version });
      if (p === "/api/shot.img") {
        if (!st.shot.data) return json(res, 404, { error: "Noch kein Screenshot." });
        res.writeHead(200, { "Content-Type": st.shot.type, "Cache-Control": "no-store" });
        return res.end(st.shot.data);
      }
      if (p === "/api/me") return json(res, 200, { id, owner: id === ownerId, name: (users.list().find((u) => u.id === id) || {}).name });
      try {
        const out = await st.backend.api(p);
        if (p === "/api/state") Object.assign(out, { server: true, owner: id === ownerId });    // Oberfläche weiß: Server-Betrieb
        if (p === "/api/settings") out.locked = true;                                           // Ollama-Adresse bestimmt der Server
        return json(res, 200, out, cors);
      } catch (e) { return json(res, e instanceof TutorError ? 400 : 500, { error: e.message }, cors); }
    }
    if (req.method !== "POST") return json(res, 405, { error: "Nicht erlaubt" });

    // --- POST ---
    if (p === "/api/shot") {                       // roher Bild-Upload, z. B. aus einem iPad-Kurzbefehl
      const type = (req.headers["content-type"] || "").split(";")[0].trim().toLowerCase();
      if (!type.startsWith("image/") || type === "image/svg+xml") return json(res, 415, { error: "Bild (PNG/JPEG) als Anfrage-Inhalt senden." });
      let data; try { data = await readBody(req); } catch (e) { return json(res, 413, { error: e.message }); }
      if (data.length < 100) return json(res, 400, { error: "Bild fehlt oder ist zu klein." });
      Object.assign(st.shot, { data, type, version: st.shot.version + 1 });
      return json(res, 200, { ok: true, version: st.shot.version });
    }
    if (p === "/api/pairing") {                    // neue Kopplung erzeugen (Besitzer, Handy/Kollegen verbinden)
      if (id !== ownerId) return json(res, 403, { error: "Nur der Besitzer darf Geräte koppeln." });
      let b = {}; try { b = JSON.parse((await readBody(req)).toString() || "{}"); } catch (e) { return json(res, 400, { error: "Ungültiges JSON" }); }
      const own = b.person === "owner" || !b.name;                         // weiteres Gerät des Besitzers oder neue Person
      const code = createPairing({ name: b.name || "Ich", forOwner: own });
      const urls = pairingUrls(code);
      let qr = null;
      try { qr = urls[0] ? await require("qrcode").toDataURL(urls[0], { margin: 1, width: 320, errorCorrectionLevel: "M" }) : null; } catch (e) { /* qrcode optional */ }
      return json(res, 200, { code, urls, qr, lan: listeners.some((l) => l.host === "0.0.0.0") });
    }

    let body = {};
    try { const raw = await readBody(req); body = raw.length ? JSON.parse(raw.toString()) : {}; }
    catch (e) { return json(res, 400, { error: "Ungültige Anfrage: " + e.message }); }
    if (STREAM_ROUTES.has(p)) return streamRoute(res, st, p, body);
    try { return json(res, 200, await st.backend.api(p, body), cors); }
    catch (e) { return json(res, e instanceof TutorError ? 400 : 500, { error: e.message }, cors); }
  }

  /* ---------- Listener ---------- */

  const listen = (h, pt) => new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => handle(req, res).catch((e) => { if (!res.headersSent) json(res, 500, { error: e.message }); else res.end(); }));
    server.once("error", reject);
    server.listen(pt, h, () => resolve({ server, host: h, port: server.address().port }));
  });
  function pairingUrls(code) {
    return listeners.flatMap((l) => (l.host === "0.0.0.0" ? addresses() : [l.host]).map((ip) => `http://${ip}:${l.port}/?pair=${code}`));
  }

  return {
    wwwDir: root,
    ownerId,
    backendFor: (id) => userState(id).backend,
    users,
    createPairing, pairingUrls, redeem,
    get ports() { return listeners.map((l) => ({ host: l.host, port: l.port })); },
    async start(o = {}) {
      const l = await listen(host, o.port === undefined ? port : o.port);
      listeners.push(l);
      return { host, port: l.port };
    },
    /* Zusätzlich im WLAN erreichbar machen (für Handy/iPad). Liefert die Adressen. */
    async enableLan(lanPort = 0) {
      if (!addresses().length) throw new Error("Kein WLAN/LAN gefunden. Der PC muss im selben Netz wie das Handy sein.");
      let l = listeners.find((x) => x.host === "0.0.0.0");
      if (!l) { l = await listen("0.0.0.0", lanPort); listeners.push(l); }
      return { port: l.port, ips: addresses() };
    },
    async disableLan() {
      const i = listeners.findIndex((x) => x.host === "0.0.0.0");
      if (i < 0) return;
      const [l] = listeners.splice(i, 1);
      await new Promise((r) => { l.server.close(r); l.server.closeAllConnections(); });
    },
    get lanEnabled() { return listeners.some((x) => x.host === "0.0.0.0"); },
    async stop() {
      for (const l of listeners.splice(0)) await new Promise((r) => { l.server.close(r); l.server.closeAllConnections(); });
    },
  };
}
module.exports = { createTutorServer, lanAddresses };
