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
  const r3 = await Promise.all([ask(a, "m:1"), ask(a, "m:1"), ask(a, "m:1")]);
  assert.ok(r3.some((r) => r.status === 503), "dritte gleichzeitige Anfrage: alle besetzt");
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
