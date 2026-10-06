const test = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const { createBackend } = require("../web/backend-local.js");

/* Fake-Ollama */
function fakeOllama() {
  const calls = [], replies = {};            // replies: Modell -> Text oder Liste (je Aufruf der nächste)
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      if (req.url === "/api/tags") {
        res.setHeader("Content-Type", "application/json");
        return res.end(JSON.stringify({ models: [{ model: "qwen2.5:32b" }, { name: "qwen2.5vl:7b" }, { model: "x:1b" }, ...(fakeOllama.withLight ? [{ model: "qwen2.5:3b" }] : [])] }));
      }
      const r = JSON.parse(body); calls.push(r);
      if (!["qwen2.5:32b", "qwen2.5vl:7b", "x:1b", ...(fakeOllama.withLight ? ["qwen2.5:3b"] : [])].includes(r.model)) {
        res.statusCode = 404; return res.end(JSON.stringify({ error: `model '${r.model}' not found` }));
      }
      if (!r.stream && r.messages[0].content.includes("# AUFRÄUMEN")) {
        let t = replies.tidy; if (Array.isArray(t)) t = t.length > 1 ? t.shift() : t[0];
        res.setHeader("Content-Type", "application/json");
        return res.end(JSON.stringify({ message: { content: t === undefined ? "# Mathe\n\n$ 3x + 7 = 22\n$ 3x = 15 [?]\n- 7 abziehen\n[ ] Übung 4" : t }, done: true }));
      }
      if (!r.stream && r.messages[0].content.includes("vom Lernen ablenkt")) {
        let t = replies.distraction; if (Array.isArray(t)) t = t.length > 1 ? t.shift() : t[0];
        res.setHeader("Content-Type", "application/json");
        return res.end(JSON.stringify({ message: { content: t === undefined ? '[{"what":"Tic-Tac-Toe auf der Seite","kind":"Spiel"},{"what":"tic-tac-toe auf der seite"},{"what":"Video im Fenster","kind":"komisch"}]' : t }, done: true }));
      }
      if (!r.stream && replies.vision) {
        res.setHeader("Content-Type", "application/json");
        return res.end(JSON.stringify({ message: { content: replies.vision }, done: true }));
      }
      if (!r.stream) {
        const p = r.messages[0].content;
        const txt = p.includes("JSON-Array") ? '[{"title":"Mathe S. 12","due":"2099-03-04","minutes":20}]' : "Aufgabe: 3x[?8x] + 7 = 22";
        return res.end(JSON.stringify({ message: { content: txt }, done: true }));
      }
      res.setHeader("Content-Type", "application/x-ndjson");
      let text = replies[r.model];
      if (Array.isArray(text)) text = text.length > 1 ? text.shift() : text[0];
      for (const w of (text === undefined ? "Was hast du versucht?" : text).split(/(?<= )/)) res.write(JSON.stringify({ message: { content: w }, done: false }) + "\n");
      res.end(JSON.stringify({ message: { content: "" }, done: true }) + "\n");
    });
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok({ server, calls, replies, url: `http://127.0.0.1:${server.address().port}` })));
}

function memStorage() {
  const m = new Map();
  return { get: async (k) => m.get(k) || null, set: async (k, v) => { m.set(k, JSON.parse(JSON.stringify(v))); }, m };
}
const TEMPLATE = "SYSTEM{{fach}} {{sprache}}";
let T = 1_800_000_000_000;                       // deterministische Uhr
const clock = () => ({ iso: "2026-10-05T15:00:00", ms: T });

async function setup(opts = {}) {
  fakeOllama.withLight = !!opts.lightInstalled;
  const fo = await fakeOllama();
  const storage = opts.storage || memStorage();
  const b = createBackend({ storage, template: TEMPLATE, clock });
  await b.api("/api/settings", { host: opts.host || fo.url, light_model: opts.light || "" });   // Router nur wenn gewünscht
  return { b, fo, storage, done: () => { fo.server.close(); fo.server.closeAllConnections(); } };
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

test("Standard-Adresse (Desktop) gilt, bis der Nutzer sie ändert", async () => {
  const storage = memStorage();
  const b = createBackend({ storage, template: TEMPLATE, clock, defaultHost: "http://localhost:11434" });
  assert.strictEqual((await b.api("/api/settings")).host, "http://localhost:11434");
  await b.api("/api/settings", { host: "http://192.168.0.5:11434" });
  const b2 = createBackend({ storage, template: TEMPLATE, clock, defaultHost: "http://localhost:11434" });
  assert.strictEqual((await b2.api("/api/settings")).host, "http://192.168.0.5:11434");
});

/* ---------- Automatische Modellwahl ---------- */
const LIGHT = "qwen2.5:3b", MAIN = "qwen2.5:32b";
const chatModels = (fo) => fo.calls.filter((c) => c.stream).map((c) => c.model);

test("Router: Smalltalk → schnelles Modell, Aufgabe → großes; keep_alive wird gesetzt", async () => {
  const { b, fo, done } = await setup({ light: LIGHT, lightInstalled: true });
  fo.replies[LIGHT] = "Moin! Woran arbeitest du?";
  const got = []; let r = await b.stream("/api/chat", { text: "moin" }, (p) => got.push(p));
  assert.strictEqual(got.join("").trim(), "Moin! Woran arbeitest du?");
  assert.strictEqual(r.route.tier, "light");
  assert.match(fo.calls[0].messages[0].content, /Schnell-Modus/);
  assert.strictEqual(fo.calls[0].keep_alive, "30m");
  r = await b.stream("/api/chat", { text: "Wie löse ich 3x+7=22?" }, () => {});
  assert.strictEqual(r.route.tier, "main");
  await b.stream("/api/chat", { text: "ok" }, () => {});             // mitten in der Aufgabe → groß
  assert.deepStrictEqual(chatModels(fo), [LIGHT, MAIN, MAIN]);
  assert.doesNotMatch(fo.calls[1].messages[0].content, /Schnell-Modus/);
  done();
});

test("Router: das schnelle Modell übergibt selbst; Escape-Wort erscheint nie in der Anzeige", async () => {
  const { b, fo, done } = await setup({ light: LIGHT, lightInstalled: true });
  fo.replies[LIGHT] = "[[WEITER]]"; fo.replies[MAIN] = "Was hast du versucht?";
  const got = []; const r = await b.stream("/api/chat", { text: "Was ist mit Brüchen" }, (p) => got.push(p));
  assert.strictEqual(got.join("").trim(), "Was hast du versucht?");
  assert.deepStrictEqual(chatModels(fo), [LIGHT, MAIN]);
  assert.match(r.route.reason, /übergeben/);
  done();
});

test("Router: chinesische Zeichen → Anzeige zurücksetzen und streng neu versuchen", async () => {
  const { b, fo, done } = await setup({});
  fo.replies[MAIN] = ["Moin! Was bist 卡特尔语言模型", "Moin! Was möchtest du lernen?"];
  const seen = []; await b.stream("/api/chat", { text: "Hilf mir bei der Aufgabe" }, (p) => seen.push(p));
  assert.ok(seen.includes(null));
  assert.strictEqual(seen.slice(seen.lastIndexOf(null) + 1).join("").trim(), "Moin! Was möchtest du lernen?");
  const calls = fo.calls.filter((c) => c.stream);
  assert.doesNotMatch(calls[0].messages[0].content, /Sprache \(wichtig\)/);
  assert.match(calls[1].messages[0].content, /Sprache \(wichtig\)/);
  assert.ok(calls[1].options.temperature <= 0.3);
  const stored = (await b.api("/api/state")).attempts; assert.strictEqual(stored, 1);
  done();
});

test("Router: alles abgerutscht → höfliche deutsche Antwort statt Kauderwelsch", async () => {
  const { b, fo, done } = await setup({});
  fo.replies[MAIN] = "Was 卡特尔 ist";
  const seen = []; await b.stream("/api/chat", { text: "Hilf mir bei Mathe" }, (p) => seen.push(p));
  const text = seen.slice(seen.lastIndexOf(null) + 1).join("");
  assert.match(text, /Entschuldige/); assert.ok(!require("../web/core.js").hasCjk(text));
  done();
});

test("Router: fehlendes schnelles Modell → still das große, Hinweis einmalig, nicht erneut versucht", async () => {
  const { b, fo, done } = await setup({ light: LIGHT, lightInstalled: false });
  fo.replies[MAIN] = "Moin!";
  const r = await b.stream("/api/chat", { text: "moin" }, () => {});
  assert.match(r.route.notice, /ollama pull qwen2\.5:3b/);
  assert.deepStrictEqual(chatModels(fo), [LIGHT, MAIN]);
  await b.stream("/api/chat", { text: "danke" }, () => {});
  assert.deepStrictEqual(chatModels(fo), [LIGHT, MAIN, MAIN]);
  done();
});

test("Router: gleiches Modell oder leer → kein Routing; Einstellung speichert light_model", async () => {
  const { b, fo, done } = await setup({ light: MAIN, lightInstalled: true });
  await b.stream("/api/chat", { text: "moin" }, () => {});
  assert.deepStrictEqual(chatModels(fo), [MAIN]);
  await b.api("/api/settings", { light_model: "x:1b" });
  assert.strictEqual((await b.api("/api/settings")).light_model, "x:1b");
  assert.strictEqual((await b.api("/api/state")).light_model, "x:1b");
  done();
});

test("Bild-Aufteilung (vision.js): Hochformat in Bänder, sehr Breites in Spalten, sonst ein Stück", () => {
  const V = require("../web/vision.js");
  assert.strictEqual(V.bands(900, 1200).length, 2);
  assert.strictEqual(V.bands(900, 2400).length, 3);
  assert.strictEqual(V.bands(1920, 1080).length, 2);
  assert.strictEqual(V.bands(1000, 1000).length, 1);
  for (const [w, h] of [[900, 1200], [900, 2400], [1920, 1080], [1000, 1000]]) {
    const bs = V.bands(w, h);
    assert.ok(bs.every((b) => b.x >= 0 && b.y >= 0 && b.x + b.w <= w && b.y + b.h <= h), "innerhalb des Bildes");
    assert.strictEqual(Math.min(...bs.map((b) => b.y)), 0); assert.strictEqual(Math.max(...bs.map((b) => b.y + b.h)), h);   // alles abgedeckt
  }
});

test("Aufräumen: Abschrift → geordnetes Notiz-Format; Regeln im Prompt; Zuruf-Änderung; Sprach-Wächter", async () => {
  const { b, fo, done } = await setup({});
  await assert.rejects(b.api("/api/tidy", {}), /noch keine Seite gelesen/);
  await b.api("/api/page", { images: [IMG] });                                  // Abschrift liegt jetzt im Kontext
  const r = await b.api("/api/tidy", {});
  assert.match(r.markup, /^# Mathe/); assert.match(r.markup, /\$ 3x = 15 \[\?\]/);
  const call = fo.calls.at(-1);
  assert.match(call.messages[0].content, /nichts lösen/); assert.match(call.messages[0].content, /\[\?\]/);
  assert.match(call.messages[1].content, /Abschrift der Seite:\n.*3x\[\?8x\]/s);
  assert.strictEqual(call.options.temperature, 0.2);
  // Änderungswunsch: aktuelle Seite + Wunsch + Original-Abschrift gehen mit
  fo.replies.tidy = "# Mathe\n- als Liste";
  const r2 = await b.api("/api/tidy", { markup: r.markup, instruction: "mach das als Liste" });
  assert.match(r2.markup, /als Liste/);
  const c2 = fo.calls.at(-1).messages[1].content;
  assert.match(c2, /Änderungswunsch: mach das als Liste/); assert.match(c2, /Original-Abschrift/); assert.ok(c2.includes(r.markup));
  // Chinesisch → streng neu; Code-Zaun wird entfernt
  fo.replies.tidy = ["# Titel 卡特尔", "```markdown\n# Titel\n- Punkt\n```"];
  const r3 = await b.api("/api/tidy", { text: "irgendwas" });
  assert.strictEqual(r3.markup, "# Titel\n- Punkt");
  assert.match(fo.calls.at(-1).messages[0].content, /Sprache \(wichtig\)/);
  fo.replies.tidy = "   ";
  await assert.rejects(b.api("/api/tidy", { text: "x" }), /nichts geliefert/);
  done();
});

test("Notiz-Format und PDF-Bau (notes.js)", () => {
  const N = require("../web/notes.js");
  const blocks = N.parse("# Titel\n\n## Teil\nText\n$ 3x = 15 [?]\n- a\n1. b\n[ ] c\n[x] d\n> e\n```\n# Zaun\n```");
  assert.deepStrictEqual(blocks.map((x) => x.t), ["h1", "gap", "h2", "p", "formula", "li", "ol", "todo", "todo", "note", "h1"]);
  assert.strictEqual(blocks[4].text, "3x = 15 [?]"); assert.strictEqual(blocks[8].done, true);
  assert.deepStrictEqual(N.parse(""), []);
  // PDF: Struktur, Offsets und Seitenzahl stimmen
  const jpeg = (n) => Uint8Array.from({ length: n }, (_, i) => (i * 7) % 256);
  const pdf = N.buildPdf([{ jpeg: jpeg(300), width: 1240, height: 1754 }, { jpeg: jpeg(50), width: 1240, height: 1754 }]);
  const text = Buffer.from(pdf).toString("latin1");
  assert.ok(text.startsWith("%PDF-1.4")); assert.ok(text.trimEnd().endsWith("%%EOF"));
  assert.match(text, /\/Count 2/);
  const start = +/startxref\n(\d+)/.exec(text)[1];
  assert.ok(text.slice(start).startsWith("xref"));
  const xref = text.slice(start).split("\n"); const total = +xref[1].split(" ")[1];
  for (let n = 1; n < total; n++) { const off = +xref[2 + n].slice(0, 10); assert.ok(text.slice(off).startsWith(`${n} 0 obj`), `Objekt ${n}`); }
});

test("Ablenkungs-Blick: Spiele, Videos, Kritzeleien finden; Antwort robust lesen", async () => {
  const C = require("../web/core.js");
  assert.deepStrictEqual(C.parseDistractions('Hier: [{"what":" Spiel ","kind":"SPIEL"},{"nix":1},{"what":"","kind":"video"}] fertig'), [{ what: "Spiel", kind: "spiel" }]);
  assert.deepStrictEqual(C.parseDistractions("kein json"), []);
  assert.deepStrictEqual(C.parseDistractions("[kaputt"), []);
  assert.strictEqual(C.parseDistractions(JSON.stringify(Array.from({ length: 9 }, (_, i) => ({ what: "x" + i })))).length, 6);
  const { b, fo, done } = await setup({});
  const r = await b.api("/api/distraction", { images: [IMG, IMG] });          // Duplikate aus mehreren Bildern entfallen
  assert.deepStrictEqual(r.distractions, [{ what: "Tic-Tac-Toe auf der Seite", kind: "spiel" }, { what: "Video im Fenster", kind: "sonstiges" }]);
  assert.match(fo.calls[0].messages[0].content, /Lernmaterial, Notizen, Aufgaben, Lernvideos/);     // Lernen zählt nicht als Ablenkung
  fo.replies.distraction = "[]";
  assert.deepStrictEqual((await b.api("/api/distraction", { image: IMG })).distractions, []);
  await assert.rejects(b.api("/api/distraction", {}), /Kein Bild/);
  done();
});

test("Aufräumen lässt Spiele/Kritzeleien weg und meldet sie", async () => {
  const { b, fo, done } = await setup({});
  fo.replies.vision = "Aufgabe 3: 3x + 7 = 22\n3x = 15\nAblenkung: Tic-Tac-Toe am Rand\nAblenkung: Tic-Tac-Toe am Rand\nAblenkung: Kritzelei unten";
  await b.api("/api/page", { images: [IMG] });
  const r = await b.api("/api/tidy", {});
  assert.deepStrictEqual(r.dropped, ["Tic-Tac-Toe am Rand", "Kritzelei unten"]);
  const user = fo.calls.at(-1).messages[1].content;
  assert.doesNotMatch(user, /Tic-Tac-Toe|Kritzelei/); assert.match(user, /3x = 15/);               // gar nicht erst an das Modell geschickt
  assert.match(fo.calls.at(-1).messages[0].content, /„Ablenkung:“ beginnen/);
  fo.replies.vision = "Ablenkung: Tic-Tac-Toe";
  await b.api("/api/page", { images: [IMG] });
  await b.api("/api/page_text", { text: "Ablenkung: Tic-Tac-Toe\nAblenkung: Galgenmännchen" });
  await assert.rejects(b.api("/api/tidy", {}), /nur Ablenkung/);
  done();
});
