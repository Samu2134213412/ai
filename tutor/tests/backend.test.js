const test = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const { createBackend } = require("../web/backend-local.js");

/* Fake-Ollama */
function fakeOllama() {
  const calls = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      if (req.url === "/api/tags") {
        res.setHeader("Content-Type", "application/json");
        return res.end(JSON.stringify({ models: [{ model: "qwen2.5:32b" }, { name: "qwen2.5vl:7b" }, { model: "x:1b" }] }));
      }
      const r = JSON.parse(body); calls.push(r);
      if (!["qwen2.5:32b", "qwen2.5vl:7b", "x:1b"].includes(r.model)) {
        res.statusCode = 404; return res.end(JSON.stringify({ error: `model '${r.model}' not found` }));
      }
      if (!r.stream) {
        const p = r.messages[0].content;
        const txt = p.includes("JSON-Array") ? '[{"title":"Mathe S. 12","due":"2099-03-04","minutes":20}]' : "Aufgabe: 3x[?8x] + 7 = 22";
        return res.end(JSON.stringify({ message: { content: txt }, done: true }));
      }
      res.setHeader("Content-Type", "application/x-ndjson");
      for (const w of ["Was ", "hast ", "du ", "versucht?"]) res.write(JSON.stringify({ message: { content: w }, done: false }) + "\n");
      res.end(JSON.stringify({ message: { content: "" }, done: true }) + "\n");
    });
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok({ server, calls, url: `http://127.0.0.1:${server.address().port}` })));
}

function memStorage() {
  const m = new Map();
  return { get: async (k) => m.get(k) || null, set: async (k, v) => { m.set(k, JSON.parse(JSON.stringify(v))); }, m };
}
const TEMPLATE = "SYSTEM{{fach}} {{sprache}}";
let T = 1_800_000_000_000;                       // deterministische Uhr
const clock = () => ({ iso: "2026-10-05T15:00:00", ms: T });

async function setup(opts = {}) {
  const fo = await fakeOllama();
  const storage = opts.storage || memStorage();
  const b = createBackend({ storage, template: TEMPLATE, clock });
  await b.api("/api/settings", { host: opts.host || fo.url });
  return { b, fo, storage, done: () => fo.server.close() };
}
const IMG = Buffer.alloc(300, 1).toString("base64");

test("Chat streamt und hebt die Stufe an; Stufentext steht im System-Prompt", async () => {
  const { b, fo, done } = await setup();
  let last;
  for (let i = 0; i < 5; i++) {
    const got = []; last = await b.stream("/api/chat", { text: "frage " + i }, (p) => got.push(p));
    assert.strictEqual(got.join(""), "Was hast du versucht?");
  }
  assert.strictEqual(last.state.stage, 3);
  const chats = fo.calls.filter((c) => c.stream);
  assert.match(chats[0].messages[0].content, /Stufe 1 – Leitfrage/);
  assert.match(chats[2].messages[0].content, /Stufe 2 – Denkanstoß/);
  assert.match(chats[4].messages[0].content, /Stufe 3 – Teilschritt/);
  assert.ok(chats.every((c) => c.messages[0].content.startsWith("SYSTEM Deutsch")));
  done();
});

test("Aufgeben: Rückfrage, dann Lösung freigegeben; /new setzt zurück", async () => {
  const { b, fo, done } = await setup();
  assert.match((await b.stream("/api/giveup", {}, () => {})).notice, /keine Aufgabe/);
  await b.stream("/api/chat", { text: "aufgabe" }, () => {});
  assert.match((await b.stream("/api/giveup", {}, () => {})).notice, /Bestätigen/);
  const r = await b.stream("/api/giveup", {}, () => {});
  assert.strictEqual(r.state.stage, 4);
  assert.match(fo.calls.at(-1).messages[0].content, /AUFGEGEBEN/);
  const n = await b.stream("/api/new", {}, () => {});
  assert.strictEqual(n.state.stage, 1); assert.strictEqual(n.state.attempts, 0);
  done();
});

test("Fehler: Modell fehlt / Ollama nicht erreichbar → Runde wird zurückgenommen", async () => {
  const { b, done } = await setup();
  await assert.rejects(b.api("/api/model", { name: "nope:1b" }), /ollama pull nope:1b/);
  await b.api("/api/model", { name: "x:1b" });
  done();
  const dead = await setup({ host: "http://127.0.0.1:1" });
  await assert.rejects(dead.b.stream("/api/chat", { text: "hi" }, () => {}), (e) => /nicht erreichbar/.test(e.message) && e.state.attempts === 0);
  const st = await dead.b.api("/api/state"); assert.match(st.problem, /nicht erreichbar/);
  dead.done();
  const none = createBackend({ storage: memStorage(), template: TEMPLATE, clock });
  await assert.rejects(none.stream("/api/chat", { text: "hi" }, () => {}), /Ollama-Adresse/);
});

test("Seite lesen: [?]-Zählung, Kontext im Prompt, korrigierte Abschrift ersetzt", async () => {
  const { b, fo, done } = await setup();
  const r = await b.api("/api/page", { images: [IMG, "data:image/png;base64," + IMG] });
  assert.strictEqual(r.unsure, 2);
  assert.ok(fo.calls[0].messages[0].images[0] === IMG);
  await b.api("/api/page_text", { text: "3x + 7 = 22" });
  await b.stream("/api/chat", { text: "hilf" }, () => {});
  const sys = fo.calls.at(-1).messages[0].content;
  assert.match(sys, /- 3x \+ 7 = 22/); assert.doesNotMatch(sys, /3x\[\?8x\]/);
  await assert.rejects(b.api("/api/page", { images: [""] }), /Kein Bild/);
  done();
});

test("Planer: Aufgaben, Plan, Tutor-Kontext, Fokus, Blockliste, Kalender", async () => {
  const { b, fo, storage, done } = await setup();
  let s = await b.api("/api/tasks", { title: "Bio lernen", subject: "Bio", due: "2099-01-02", minutes: 60 });
  assert.strictEqual(s.tasks.length, 1); assert.ok(s.plan.blocks.length);
  await assert.rejects(b.api("/api/tasks", { title: " " }), /Titel/);
  await b.stream("/api/chat", { text: "hi" }, () => {});
  assert.match(fo.calls.at(-1).messages[0].content, /Bio lernen \(Bio\), fällig 2099-01-02/);
  s = await b.api("/api/tasks/update", { id: s.tasks[0].id, fields: { done: true } });
  assert.deepStrictEqual(s.plan.blocks, []);
  s = await b.api("/api/focus/start", { minutes: 25 });
  assert.ok(s.focus.active); assert.strictEqual(s.focus.remaining, 1500);
  T += 1600 * 1000; assert.strictEqual((await b.api("/api/focus")).active, false); T -= 1600 * 1000;
  s = await b.api("/api/blocklist", { items: ["https://www.Foo.com/x", "kaputt"] });
  assert.deepStrictEqual(s.blocklist, ["foo.com"]);
  await b.api("/api/reminders", { enabled: true, time: "17:30" });
  assert.match((await b.api("/api/plan.ics")).ics, /RRULE:FREQ=DAILY/);
  // Persistenz: neues Backend mit demselben Speicher sieht alles wieder
  const b2 = createBackend({ storage, template: TEMPLATE, clock });
  const again = await b2.api("/api/planner");
  assert.strictEqual(again.tasks[0].title, "Bio lernen"); assert.deepStrictEqual(again.blocklist, ["foo.com"]);
  assert.strictEqual((await b2.api("/api/settings")).host, fo.url);
  done();
});

test("Aufgaben aus Seite lesen: Duplikate aus überlappenden Bändern entfallen", async () => {
  const { b, done } = await setup();
  const r = await b.api("/api/tasks/extract", { images: [IMG, IMG] });
  assert.deepStrictEqual(r.candidates.map((c) => c.title), ["Mathe S. 12"]);
  done();
});

test("Einstellungen validieren die Adresse; Speichern legt Sitzung ab", async () => {
  const { b, done } = await setup();
  await assert.rejects(b.api("/api/settings", { host: "ftp://x" }), /Adresse/);
  assert.deepStrictEqual(await b.api("/api/save", {}), { saved: null });
  await b.stream("/api/chat", { text: "hi" }, () => {});
  assert.strictEqual((await b.api("/api/save", {})).saved, "in der App");
  done();
});
