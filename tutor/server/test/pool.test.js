const test = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const { createPool, cleanChat } = require("../pool.js");

const KEY = "klasse-7b-geheim";
function fakeOllama(models, { delay = 0, tag = "A" } = {}) {
  const calls = [];
  const s = http.createServer((req, res) => {
    let b = ""; req.on("data", (c) => (b += c));
    req.on("end", async () => {
      if (req.url === "/api/tags") return res.end(JSON.stringify({ models: models.map((m) => ({ model: m })) }));
      const r = JSON.parse(b); calls.push(r);
      res.setHeader("Content-Type", "application/x-ndjson");
      if (delay) await new Promise((x) => setTimeout(x, delay));
      res.write(JSON.stringify({ message: { content: `von ${tag} ` }, done: false }) + "\n");
      res.end(JSON.stringify({ message: { content: "" }, done: true }) + "\n");
    });
  });
  return new Promise((ok) => s.listen(0, "127.0.0.1", () => ok({ s, calls, url: `http://127.0.0.1:${s.address().port}` })));
}
async function node(models, o = {}) {
  const fo = await fakeOllama(models, o);
  const pool = createPool({ key: o.key || KEY, ollama: fo.url, udp: false, maxJobs: o.maxJobs || 1 });
  await pool.start();
  return { fo, pool, stop: async () => { await pool.stop(); fo.s.close(); fo.s.closeAllConnections(); } };
}
const link = (a, b) => { a.pool.hear(b.pool.announcement(), "127.0.0.1"); b.pool.hear(a.pool.announcement(), "127.0.0.1"); };
const ask = async (n, model, body = {}) => {
  const r = await fetch(n.pool.proxyUrl + "/api/chat", { method: "POST", body: JSON.stringify({ model, messages: [{ role: "user", content: "hi" }], stream: true, ...body }) });
  return { status: r.status, text: await r.text() };
};

test("zu kurzer Klassencode wird abgelehnt", () => {
  assert.throws(() => createPool({ key: "abc", udp: false }), /zu kurz/);
});

test("Anfrage geht an das Gerät, das das Modell hat", async () => {
  const weak = await node(["qwen2.5:3b"], { tag: "schwach" }), strong = await node(["qwen2.5:3b", "qwen2.5:32b"], { tag: "stark" });
  link(weak, strong);
  const r = await ask(weak, "qwen2.5:32b");
  assert.match(r.text, /von stark/);
  assert.equal(strong.fo.calls.length, 1);
  assert.equal(weak.fo.calls.length, 0);
  assert.equal(weak.pool.info().used, 1);
  assert.equal(strong.pool.info().served, 1);
  const tags = await (await fetch(weak.pool.proxyUrl + "/api/tags")).json();
  assert.ok(tags.models.some((m) => m.model === "qwen2.5:32b:latest" || m.model.startsWith("qwen2.5:32b")));
  await weak.stop(); await strong.stop();
});

test("besetztes Gerät wird umgangen, sonst gleichmäßig verteilt", async () => {
  const a = await node(["m:1"], { delay: 150, tag: "a" }), b = await node(["m:1"], { delay: 150, tag: "b" });
  link(a, b);
  const [r1, r2] = await Promise.all([ask(a, "m:1"), ask(a, "m:1")]);
  assert.deepEqual([r1.text.includes("von a"), r2.text.includes("von b")].sort(), [true, true].sort());
  assert.notEqual(r1.text.match(/von \w/)[0], r2.text.match(/von \w/)[0]);
  const r3 = await Promise.all([ask(a, "m:1"), ask(a, "m:1"), ask(a, "m:1")]);   // dritte wartet, bis ein Gerät frei ist
  assert.deepEqual(r3.map((r) => r.status), [200, 200, 200]);
  assert.equal(a.fo.calls.length + b.fo.calls.length, 5);
  await a.stop(); await b.stop();
});

test("falscher Klassencode, fehlende Signatur und Nicht-Beitragende werden abgewiesen", async () => {
  const a = await node(["m:1"]), other = await node(["m:1"], { key: "ganz-andere-klasse" });
  assert.equal(a.pool.hear(other.pool.announcement(), "127.0.0.1"), false);
  const url = `http://127.0.0.1:${a.pool.workerPort}/pool/chat`;
  const body = JSON.stringify({ model: "m:1", messages: [] });
  assert.equal((await fetch(url, { method: "POST", body })).status, 403);
  // gültig signiert, aber Absender hat nie beigetragen (kein Rundruf gehört)
  const stranger = createPool({ key: KEY, ollama: a.fo.url, udp: false, id: "fremd" });
  const crypto = require("node:crypto"), ts = String(Date.now());
  const sig = crypto.createHmac("sha256", KEY).update(["fremd", ts, "/pool/chat"].join("|")).digest("hex");
  assert.equal((await fetch(url, { method: "POST", body, headers: { "X-Pool-Id": "fremd", "X-Pool-Ts": ts, "X-Pool-Sig": sig } })).status, 403);
  assert.equal((await fetch(`http://127.0.0.1:${a.pool.workerPort}/pool/anything`)).status, 403);
  await a.stop(); await other.stop();
});

test("nur erlaubte Felder werden an Ollama weitergegeben", () => {
  const c = cleanChat({ model: "m", messages: [], stream: true, system: "x", options: { temperature: 0.6, num_ctx: 999999, evil: 1 }, keep_alive: { a: 1 } });
  assert.deepEqual(Object.keys(c).sort(), ["messages", "model", "options", "stream"]);
  assert.deepEqual(c.options, { temperature: 0.6, num_ctx: 16384 });
  assert.throws(() => cleanChat({ model: 5 }));
});

test("ausgefallenes Gerät: nächster Kandidat übernimmt", async () => {
  const a = await node(["m:1"], { tag: "a" }), b = await node(["m:1"], { tag: "b" });
  link(a, b);
  await b.stop();
  const r = await ask(a, "m:1");
  assert.match(r.text, /von a/);
  await a.stop();
});

test("unbekanntes Modell: 404 wie bei Ollama", async () => {
  const a = await node(["m:1"]);
  const r = await ask(a, "gibtsnicht:1b");
  assert.equal(r.status, 404);
  await a.stop();
});

test("Wartezeit zu lang: freundliche 503 statt Hängen", async () => {
  const fo = await fakeOllama(["m:1"], { delay: 400 });
  const pool = createPool({ key: KEY, ollama: fo.url, udp: false, queueMs: 100 });
  await pool.start();
  const n = { pool };
  const [a, b] = await Promise.all([ask(n, "m:1"), new Promise((r) => setTimeout(r, 50)).then(() => ask(n, "m:1"))]);
  assert.deepEqual([a.status, b.status], [200, 503]);
  await pool.stop(); fo.s.close(); fo.s.closeAllConnections();
});

/* ---------- Tablets rechnen mit (Abholer) ---------- */
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { createTutorServer } = require("../server.js");

async function tabletSetup() {
  const fo = await fakeOllama([]);                                  // PC ohne eigenes Modell – nur das Tablet rechnet
  const pool = createPool({ key: KEY, ollama: fo.url, udp: false });
  await pool.start();
  const models = fs.mkdtempSync(path.join(os.tmpdir(), "ollama-models-"));
  const digest = "a".repeat(64);
  fs.mkdirSync(path.join(models, "manifests", "registry.ollama.ai", "library", "qwen2.5"), { recursive: true });
  fs.writeFileSync(path.join(models, "manifests", "registry.ollama.ai", "library", "qwen2.5", "1.5b"),
    JSON.stringify({ layers: [{ mediaType: "application/vnd.ollama.image.model", digest: "sha256:" + digest }] }));
  fs.mkdirSync(path.join(models, "blobs"));
  fs.writeFileSync(path.join(models, "blobs", "sha256-" + digest), Buffer.from("GGUF0123456789"));
  const srv = createTutorServer({ wwwDir: path.join(__dirname, "..", "..", "web"), dataDir: fs.mkdtempSync(path.join(os.tmpdir(), "td-")),
    ollama: pool.proxyUrl, port: 0, pool, modelsDir: models });
  const { port } = await srv.start();
  const base = `http://127.0.0.1:${port}`;
  const token = (await (await fetch(base + "/api/pair", { method: "POST", body: JSON.stringify({ code: srv.createPairing({ forOwner: true }) }) })).json()).token;
  const H = { "X-Tutor-Token": token, "Content-Type": "application/json" };
  return { fo, pool, srv, base, H, stop: async () => { await srv.stop(); await pool.stop(); fo.s.close(); fo.s.closeAllConnections(); } };
}

test("Tablet holt Anfrage ab, rechnet und streamt zurück – für den Pool wie ein Ollama", async () => {
  const t = await tabletSetup();
  const st = await (await fetch(t.base + "/api/pool/status", { headers: t.H })).json();
  assert.deepEqual(st, { enabled: true, models: ["qwen2.5:1.5b"], tablets: 0 });
  // Tablet wartet auf Arbeit
  const pulling = fetch(t.base + "/api/pool/pull?dev=ipad1&name=iPad&models=qwen2.5:1.5b,qwen2.5:32b", { headers: t.H }).then((r) => r.json());
  await new Promise((r) => setTimeout(r, 50));
  assert.ok((await (await fetch(t.pool.proxyUrl + "/api/tags")).json()).models.some((m) => m.model === "qwen2.5:1.5b"));
  assert.ok(!(await (await fetch(t.pool.proxyUrl + "/api/tags")).json()).models.some((m) => m.model.startsWith("qwen2.5:32b")), "große Modelle darf ein Tablet nicht anbieten");
  const answer = ask({ pool: t.pool }, "qwen2.5:1.5b", { options: { temperature: 0.2 } });
  const { job } = await pulling;
  assert.equal(job.model, "qwen2.5:1.5b");
  assert.equal(job.messages[0].content, "hi");
  assert.equal(job.temperature, 0.2);
  const push = (b) => fetch(t.base + "/api/pool/push?dev=ipad1", { method: "POST", headers: t.H, body: JSON.stringify({ job: job.job, ...b }) }).then((r) => r.json());
  assert.deepEqual(await push({ content: "Was " }), { ok: true, cancel: false });
  await push({ content: "meinst du?" });
  await push({ done: true });
  const r = await answer;
  assert.equal(r.status, 200);
  const lines = r.text.trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(lines.map((l) => l.message.content).join(""), "Was meinst du?");
  assert.equal(lines.at(-1).done, true);
  assert.equal(t.pool.info().tablets[0].done, 1);
  // ein anderes Gerät kann die Aufgabe nicht beantworten
  assert.deepEqual(await (await fetch(t.base + "/api/pool/push?dev=fremd", { method: "POST", headers: t.H, body: JSON.stringify({ job: job.job, content: "x" }) })).json(), { ok: false, cancel: true });
  await t.stop();
});

test("Tablet: Abbruch beim Fragenden meldet cancel, Modell-Download mit Range, Pfad-Tricks abgewiesen", async () => {
  const t = await tabletSetup();
  const pulling = fetch(t.base + "/api/pool/pull?dev=ipad2&models=qwen2.5:1.5b", { headers: t.H }).then((r) => r.json());
  await new Promise((r) => setTimeout(r, 50));
  const ctl = new AbortController();
  const req = fetch(t.pool.proxyUrl + "/api/chat", { method: "POST", signal: ctl.signal, body: JSON.stringify({ model: "qwen2.5:1.5b", messages: [{ role: "user", content: "x" }] }) }).catch(() => null);
  const { job } = await pulling;
  ctl.abort(); await req; await new Promise((r) => setTimeout(r, 50));
  const res = await (await fetch(t.base + "/api/pool/push?dev=ipad2", { method: "POST", headers: t.H, body: JSON.stringify({ job: job.job, content: "zu spät" }) })).json();
  assert.equal(res.cancel, true);
  const full = await fetch(t.base + "/api/pool/model.gguf?name=qwen2.5:1.5b", { headers: t.H });
  assert.equal(await full.text(), "GGUF0123456789");
  const head = await fetch(t.base + "/api/pool/model.gguf?name=qwen2.5:1.5b", { method: "HEAD", headers: t.H });
  assert.equal(head.headers.get("content-length"), "14"); assert.equal(head.headers.get("accept-ranges"), "bytes");
  const part = await fetch(t.base + "/api/pool/model.gguf?name=qwen2.5:1.5b", { headers: { ...t.H, Range: "bytes=4-7" } });
  assert.equal(part.status, 206); assert.equal(await part.text(), "0123");
  for (const n of ["../../etc/passwd", "qwen2.5:32b", "qwen2.5:3b"]) assert.equal((await fetch(t.base + "/api/pool/model.gguf?name=" + encodeURIComponent(n), { headers: t.H })).status, 404, n);
  assert.equal((await fetch(t.base + "/api/pool/pull?models=qwen2.5:1.5b")).status, 401, "ohne Kopplung kein Zugriff");
  await t.stop();
});

test("Pool aus: Tablet-Routen sagen das klar", async () => {
  const fo = await fakeOllama(["m:1"]);
  const srv = createTutorServer({ wwwDir: path.join(__dirname, "..", "..", "web"), dataDir: fs.mkdtempSync(path.join(os.tmpdir(), "td-")), ollama: fo.url, port: 0 });
  const { port } = await srv.start(); const base = `http://127.0.0.1:${port}`;
  const token = (await (await fetch(base + "/api/pair", { method: "POST", body: JSON.stringify({ code: srv.createPairing({ forOwner: true }) }) })).json()).token;
  assert.deepEqual(await (await fetch(base + "/api/pool/status", { headers: { "X-Tutor-Token": token } })).json(), { enabled: false, models: [], tablets: 0 });
  assert.equal((await fetch(base + "/api/pool/pull", { headers: { "X-Tutor-Token": token } })).status, 404);
  await srv.stop(); fo.s.close(); fo.s.closeAllConnections();
});
