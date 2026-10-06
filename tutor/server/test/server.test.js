const test = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createTutorServer } = require("../server.js");

const WWW = path.join(__dirname, "..", "..", "web");

/* Fake-Ollama: antwortet je Modell, optional langsam (für „besetzt“-Test) */
function fakeOllama() {
  const calls = [], replies = {}; let delay = 0;
  const s = http.createServer((req, res) => {
    let body = ""; req.on("data", (c) => (body += c));
    req.on("end", async () => {
      if (req.url === "/api/tags") { res.setHeader("Content-Type", "application/json"); return res.end(JSON.stringify({ models: ["qwen2.5:32b", "qwen2.5:3b", "qwen2.5vl:7b"].map((m) => ({ model: m })) })); }
      const r = JSON.parse(body); calls.push(r);
      if (!r.stream) { res.setHeader("Content-Type", "application/json"); return res.end(JSON.stringify({ message: { content: "Aufgabe: 3x[?8x] + 7 = 22" }, done: true })); }
      res.setHeader("Content-Type", "application/x-ndjson");
      let text = replies[r.model]; if (Array.isArray(text)) text = text.length > 1 ? text.shift() : text[0];
      for (const w of (text === undefined ? "Was hast du versucht?" : text).split(/(?<= )/)) { if (delay) await new Promise((x) => setTimeout(x, delay)); res.write(JSON.stringify({ message: { content: w }, done: false }) + "\n"); }
      res.end(JSON.stringify({ message: { content: "" }, done: true }) + "\n");
    });
  });
  return new Promise((ok) => s.listen(0, "127.0.0.1", () => ok({ s, calls, replies, setDelay: (d) => (delay = d), url: `http://127.0.0.1:${s.address().port}` })));
}

async function setup(opts = {}) {
  const fo = await fakeOllama();
  const dataDir = opts.dataDir || fs.mkdtempSync(path.join(os.tmpdir(), "tutor-data-"));
  const srv = createTutorServer({ wwwDir: WWW, dataDir, ollama: fo.url, port: 0 });
  const { port } = await srv.start();
  const base = `http://127.0.0.1:${port}`;
  const ownerToken = (await (await fetch(base + "/api/pair", { method: "POST", body: JSON.stringify({ code: srv.createPairing({ forOwner: true }) }) })).json()).token;
  const call = (p, init = {}) => fetch(base + p, { ...init, headers: { "X-Tutor-Token": ownerToken, "Content-Type": "application/json", ...(init.headers || {}) } });
  const post = (p, body, h) => call(p, { method: "POST", body: JSON.stringify(body || {}), headers: h });
  const events = async (r) => (await r.text()).split("\n\n").filter((l) => l.startsWith("data:")).map((l) => JSON.parse(l.slice(5)));
  return { fo, srv, base, ownerToken, call, post, events, dataDir, stop: async () => { await srv.stop(); fo.s.close(); fo.s.closeAllConnections(); } };
}

test("Kopplung: ohne Token gesperrt, Code einmalig, Link setzt Cookie, Header und Bearer gehen", async () => {
  const t = await setup();
  try {
    assert.strictEqual((await fetch(t.base + "/api/state")).status, 401);
    assert.strictEqual((await fetch(t.base + "/")).status, 401);
    assert.strictEqual((await fetch(t.base + "/?pair=FALSCH123")).status, 401);
    const code = t.srv.createPairing({ forOwner: true });
    const link = await fetch(t.base + `/?pair=${code.toLowerCase()}`, { redirect: "manual" });   // Groß/Klein egal
    assert.strictEqual(link.status, 302);
    const cookie = link.headers.get("set-cookie").split(";")[0];
    assert.match(link.headers.get("set-cookie"), /HttpOnly/);
    assert.strictEqual((await fetch(t.base + "/api/state", { headers: { Cookie: cookie } })).status, 200);
    assert.match(await (await fetch(t.base + "/", { headers: { Cookie: cookie } })).text(), /<title>Tutor/);
    assert.strictEqual((await fetch(t.base + `/?pair=${code}`, { redirect: "manual" })).status, 401);   // schon benutzt
    const token = cookie.split("=")[1];
    assert.strictEqual((await fetch(t.base + "/api/state", { headers: { Authorization: "Bearer " + token } })).status, 200);
    assert.strictEqual((await fetch(t.base + "/api/state", { headers: { "X-Tutor-Token": "falsch" } })).status, 401);
    const abgelaufen = t.srv.createPairing({ forOwner: true, ttlMs: -1 });
    assert.strictEqual((await fetch(t.base + `/?pair=${abgelaufen}`)).status, 401);
    // Tokens liegen nur als Hash auf der Platte
    assert.ok(!fs.readFileSync(path.join(t.dataDir, "users.json"), "utf8").includes(t.ownerToken));
  } finally { await t.stop(); }
});

test("Chat: SSE-Stream, Stufen, Aufgeben-Hinweis als JSON, Neu, getrennte Verläufe pro Person", async () => {
  const t = await setup();
  try {
    t.fo.replies["qwen2.5:32b"] = "Was hast du versucht?";
    const evs = await t.events(await t.post("/api/chat", { text: "Wie löse ich 3x+7=22?" }));
    assert.strictEqual(evs.filter((e) => e.t).map((e) => e.t).join("").trim(), "Was hast du versucht?");
    assert.strictEqual(evs.at(-1).done, true); assert.strictEqual(evs.at(-1).route.tier, "main"); assert.strictEqual(evs.at(-1).state.attempts, 1);
    assert.match(t.fo.calls.at(-1).messages[0].content, /Stufe 1/);
    const notice = await (await t.post("/api/giveup")).json();                  // zu früh → Rückfrage als JSON
    assert.match(notice.notice, /Bestätigen/);
    const fresh = await (await t.post("/api/new")).json(); assert.strictEqual(fresh.state.attempts, 0);
    // zweite Person: eigener Verlauf & eigene Aufgaben
    const anna = await (await fetch(t.base + "/api/pair", { method: "POST", body: JSON.stringify({ code: t.srv.createPairing({ name: "Anna" }) }) })).json();
    const A = (p, b) => fetch(t.base + p, { method: "POST", headers: { "X-Tutor-Token": anna.token }, body: JSON.stringify(b || {}) });
    await t.events(await t.post("/api/chat", { text: "Hilf mir bei x=5" })); await t.post("/api/tasks", { title: "Meine Aufgabe" });
    const annaState = await (await fetch(t.base + "/api/state", { headers: { "X-Tutor-Token": anna.token } })).json();
    assert.strictEqual(annaState.attempts, 0);
    assert.deepStrictEqual((await (await fetch(t.base + "/api/planner", { headers: { "X-Tutor-Token": anna.token } })).json()).tasks, []);
    assert.strictEqual((await A("/api/pairing")).status, 403);                    // nur der Besitzer koppelt
    assert.strictEqual((await (await t.call("/api/me")).json()).owner, true);
  } finally { await t.stop(); }
});

test("Modellwahl, Sprach-Wächter und Fehler laufen über den Server", async () => {
  const t = await setup();
  try {
    t.fo.replies["qwen2.5:3b"] = "Moin! Woran arbeitest du?";
    const a = await t.events(await t.post("/api/chat", { text: "moin" }));
    assert.strictEqual(a.at(-1).route.tier, "light");
    t.fo.replies["qwen2.5:32b"] = ["Hi 你好 du", "Hallo! Was möchtest du lernen?"];
    const b = await t.events(await t.post("/api/new", { text: "Hilf mir bei der Aufgabe" }));
    assert.ok(b.some((e) => e.reset)); assert.strictEqual(b.at(-1).done, true);
    // Host ist gesperrt: der Client kann Ollama nicht umbiegen
    const s = await (await t.post("/api/settings", { host: "http://evil.example:11434", model: "qwen2.5:32b" })).json();
    assert.match(s.host, /^http:\/\/127\.0\.0\.1:\d+$/);
    assert.strictEqual((await t.post("/api/model", { name: "gibtsnicht:1b" })).status, 400);
    const empty = await t.events(await t.post("/api/chat", { text: " " }));              // leere Nachricht → Fehler-Ereignis
    assert.match(empty.at(-1).error, /Leere Nachricht/);
  } finally { await t.stop(); }
});

test("Besetzt: zweite Anfrage derselben Person bekommt 409, andere Person nicht", async () => {
  const t = await setup();
  try {
    t.fo.setDelay(60); t.fo.replies["qwen2.5:32b"] = "Das ist eine längere Antwort mit mehreren Wörtern";
    const first = t.post("/api/chat", { text: "Hilf mir bei x=5" });
    await new Promise((r) => setTimeout(r, 80));
    const second = await t.post("/api/chat", { text: "noch eine Frage zu x=6" });
    assert.strictEqual(second.status, 409);
    assert.strictEqual((await t.events(await first)).at(-1).done, true);
  } finally { await t.stop(); }
});

test("Persistenz: Verlauf-unabhängige Daten und Geräte überleben einen Neustart", async () => {
  const t = await setup();
  await t.post("/api/tasks", { title: "Bio lernen", due: "2099-01-02", minutes: 40 });
  await t.post("/api/blocklist", { items: ["foo.com"] });
  const dataDir = t.dataDir, token = t.ownerToken;
  await t.srv.stop(); t.fo.s.close(); t.fo.s.closeAllConnections();
  const t2 = await (async () => { const fo = await fakeOllama(); const srv = createTutorServer({ wwwDir: WWW, dataDir, ollama: fo.url, port: 0 }); const { port } = await srv.start(); return { fo, srv, base: `http://127.0.0.1:${port}` }; })();
  try {
    const planner = await (await fetch(t2.base + "/api/planner", { headers: { "X-Tutor-Token": token } })).json();   // altes Token gilt weiter
    assert.strictEqual(planner.tasks[0].title, "Bio lernen"); assert.deepStrictEqual(planner.blocklist, ["foo.com"]);
    assert.strictEqual(t2.srv.users.list().length, 1);
  } finally { await t2.srv.stop(); t2.fo.s.close(); t2.fo.s.closeAllConnections(); }
});

test("Planer, Kalender, Seiten und Screenshot-Upload (Kurzbefehl)", async () => {
  const t = await setup();
  try {
    const st = await (await t.post("/api/tasks", { title: "Mathe", due: "2099-01-02", minutes: 60 })).json();
    assert.ok(st.plan.blocks.length);
    const ics = await t.call("/api/plan.ics"); assert.match(ics.headers.get("content-type"), /text\/calendar/); assert.match(await ics.text(), /BEGIN:VCALENDAR/);
    const img = Buffer.alloc(300, 1).toString("base64");
    const page = await (await t.post("/api/page", { images: [img] })).json(); assert.strictEqual(page.unsure, 1);
    assert.strictEqual((await (await t.post("/api/tasks/extract", { image: img })).json()).candidates.length, 0);   // Fake liefert keine JSON-Liste
    assert.strictEqual((await (await t.call("/api/shot")).json()).version, 0);
    const up = await t.call("/api/shot", { method: "POST", body: Buffer.alloc(400, 7), headers: { "Content-Type": "image/png" } });
    assert.deepStrictEqual(await up.json(), { ok: true, version: 1 });
    assert.strictEqual((await t.call("/api/shot.img")).headers.get("content-type"), "image/png");
    assert.strictEqual((await t.call("/api/shot", { method: "POST", body: "x", headers: { "Content-Type": "text/html" } })).status, 415);
  } finally { await t.stop(); }
});

test("Erweiterung „Tutor Fokus“: lokal ohne Token nur für Fokus-Routen, fremde Origins nie", async () => {
  const t = await setup();
  try {
    const ext = { Origin: "chrome-extension://abc" };
    const start = await fetch(t.base + "/api/focus/start", { method: "POST", headers: { ...ext, "Content-Type": "application/json" }, body: JSON.stringify({ minutes: 25 }) });
    assert.strictEqual(start.status, 200); assert.strictEqual(start.headers.get("access-control-allow-origin"), "*");
    const f = await (await fetch(t.base + "/api/focus", { headers: ext })).json();
    assert.strictEqual(f.active, true); assert.ok(f.blocklist.includes("youtube.com"));
    assert.strictEqual((await t.call("/api/focus")).status, 200);                      // dieselbe Sitzung (Besitzer)
    assert.strictEqual((await fetch(t.base + "/api/state", { headers: ext })).status, 401);   // sonst kein Zugriff ohne Token
    assert.strictEqual((await fetch(t.base + "/api/focus", { headers: { Origin: "https://evil.example" } })).status, 401);
    assert.strictEqual((await fetch(t.base + "/api/focus")).status, 401);
    assert.strictEqual((await fetch(t.base + "/api/focus", { method: "OPTIONS", headers: ext })).status, 204);
  } finally { await t.stop(); }
});

test("Besitzer koppelt weitere Geräte/Personen per API; WLAN-Zugang lässt sich ein- und ausschalten", async () => {
  const t = await setup();
  try {
    const r = await (await t.post("/api/pairing", { name: "Ben" })).json();
    assert.match(r.code, /^[A-Z2-9]{8}$/); assert.ok(r.urls[0].includes("?pair=" + r.code));
    const dev = await (await fetch(t.base + "/api/pair", { method: "POST", body: JSON.stringify({ code: r.code }) })).json();
    assert.notStrictEqual(dev.id, t.srv.ownerId);
    assert.strictEqual((await fetch(t.base + "/api/pair", { method: "POST", body: JSON.stringify({ code: r.code }) })).status, 401);
    const lan = await t.srv.enableLan(0);
    assert.ok(lan.port > 0); assert.strictEqual(t.srv.lanEnabled, true);
    const viaLan = await fetch(`http://127.0.0.1:${lan.port}/api/state`, { headers: { "X-Tutor-Token": dev.token } });
    assert.strictEqual(viaLan.status, 200);
    await t.srv.disableLan(); assert.strictEqual(t.srv.lanEnabled, false);
    await assert.rejects(fetch(`http://127.0.0.1:${lan.port}/api/state`));
  } finally { await t.stop(); }
});

test("Fremde Ursprünge (iPad-App, Overlay): Vorabfrage erlaubt, Zugriff nur mit Token", async () => {
  const t = await setup();
  try {
    const pre = await fetch(t.base + "/api/chat", { method: "OPTIONS", headers: { Origin: "capacitor://localhost", "Access-Control-Request-Headers": "x-tutor-token,content-type" } });
    assert.strictEqual(pre.status, 204); assert.match(pre.headers.get("access-control-allow-headers"), /X-Tutor-Token/i);
    const ok = await fetch(t.base + "/api/state", { headers: { Origin: "capacitor://localhost", "X-Tutor-Token": t.ownerToken } });
    assert.strictEqual(ok.status, 200); assert.strictEqual(ok.headers.get("access-control-allow-origin"), "*");
    const no = await fetch(t.base + "/api/state", { headers: { Origin: "https://evil.example" } });
    assert.strictEqual(no.status, 401);                                          // ohne Token nichts zu holen
    const stream = await t.post("/api/chat", { text: "Hilf mir bei x=5" }, { Origin: "capacitor://localhost" });
    assert.strictEqual(stream.headers.get("access-control-allow-origin"), "*");  // auch beim Streaming
    await stream.text();
  } finally { await t.stop(); }
});

test("Statische Dateien: kein Ausbruch aus dem Web-Ordner", async () => {
  const t = await setup();
  try {
    for (const p of ["/../server.js", "/%2e%2e/server/server.js", "/..%2fREADME.md"]) {
      const r = await t.call(p); assert.ok([403, 404].includes(r.status), p); assert.doesNotMatch(await r.text(), /createTutorServer/);
    }
    assert.strictEqual((await t.call("/app.js")).status, 200);
    assert.strictEqual((await t.call("/nicht-da.js")).status, 404);
  } finally { await t.stop(); }
});
