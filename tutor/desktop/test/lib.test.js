const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { FocusState } = require("../lib/focus-state.js");
const { createStaticServer } = require("../lib/static-server.js");
const { createGuard, sanitizeNames, parseProcessList } = require("../lib/guard.js");
const { createConfig } = require("../lib/config.js");

/* ---------- FocusState ---------- */
test("FocusState: Start/Stop/Ablauf und validiertes Update", () => {
  let t = 1000; const f = new FocusState(() => t);
  assert.strictEqual(f.info().active, false);
  f.start(25); assert.strictEqual(f.info().remaining, 1500);
  t += 1600; assert.strictEqual(f.info().active, false);
  f.start(9999); assert.strictEqual(f.minutes, 240);
  f.stop(); assert.strictEqual(f.info().active, false);
  f.update({ ends_at: 5000, minutes: 10, blocklist: ["a.com", "böse; rm", "../x", 5] });
  assert.deepStrictEqual(f.blocklist, ["a.com"]); assert.strictEqual(f.endsAt, 5000);
  f.update(null); f.update({ ends_at: "x" });
  assert.strictEqual(f.endsAt, 5000);
});

/* ---------- Server ---------- */
const open = [];
test.after(async () => { for (const s of open) await s.close().catch(() => {}); });

async function startServer() {
  const www = fs.mkdtempSync(path.join(os.tmpdir(), "www-"));
  fs.writeFileSync(path.join(www, "index.html"), "<title>x</title>");
  fs.mkdirSync(path.join(www, "prompts")); fs.writeFileSync(path.join(www, "prompts", "tutor.md"), "# Prompt");
  fs.writeFileSync(path.join(path.dirname(www), "geheim.txt"), "nicht ausliefern");
  const focus = new FocusState(), cmds = [];
  const s = createStaticServer({ wwwDir: www, focus, onCommand: (c) => cmds.push(c), port: 0 });
  const port = await s.listen(); open.push(s);
  const call = (p, init = {}) => fetch(`http://127.0.0.1:${port}${p}`, init);
  return { s, port, call, focus, cmds, www };
}

test("Server: liefert Dateien, blockt Pfad-Tricks und falschen Host", async () => {
  const { s, port, call } = await startServer();
  const r = await call("/"); assert.strictEqual(r.status, 200); assert.match(await r.text(), /<title>x/);
  assert.strictEqual((await call("/prompts/tutor.md")).headers.get("content-type").startsWith("text/markdown"), true);
  assert.strictEqual((await call("/nix")).status, 404);
  for (const p of ["/../geheim.txt", "/%2e%2e/geheim.txt", "/..%2fgeheim.txt"]) {
    const got = await call(p); assert.ok([403, 404].includes(got.status), p); assert.doesNotMatch(await got.text(), /nicht ausliefern/);
  }
  const status = await new Promise((ok, fail) => {       // fetch darf „Host“ nicht setzen → rohes http
    require("node:http").get({ host: "127.0.0.1", port, path: "/", headers: { Host: "evil.example" } }, (r) => { r.resume(); ok(r.statusCode); }).on("error", fail);
  });
  assert.strictEqual(status, 421);
});

test("Server: Fokus-API für die Erweiterung (CORS, Origin-Schutz, Grenzen)", async () => {
  const { s, call, focus, cmds } = await startServer();
  const ext = { Origin: "chrome-extension://abc", "Content-Type": "application/json" };
  const start = await call("/api/focus/start", { method: "POST", headers: ext, body: JSON.stringify({ minutes: 25 }) });
  assert.strictEqual(start.status, 200);
  assert.strictEqual(start.headers.get("access-control-allow-origin"), "chrome-extension://abc");
  assert.deepStrictEqual(cmds, [{ type: "start", minutes: 25 }]);
  const info = await (await call("/api/focus", { headers: ext })).json();
  assert.strictEqual(info.active, true); assert.ok(info.blocklist.includes("youtube.com"));
  const evil = await call("/api/focus/stop", { method: "POST", headers: { Origin: "https://evil.example" }, body: "{}" });
  assert.strictEqual(evil.status, 403); assert.strictEqual(focus.info().active, true);
  assert.strictEqual((await call("/api/focus/start", { method: "POST", headers: ext, body: JSON.stringify({ minutes: 9999 }) })).status, 400);
  assert.strictEqual((await call("/api/focus/start", { method: "POST", headers: ext, body: "{kaputt" })).status, 400);
  const pre = await call("/api/focus/start", { method: "OPTIONS", headers: ext }); assert.strictEqual(pre.status, 204);
  assert.strictEqual((await call("/api/focus/stop", { method: "POST", headers: ext, body: "{}" })).status, 200);
  assert.strictEqual(focus.info().active, false); assert.deepStrictEqual(cmds.at(-1), { type: "stop" });
  assert.strictEqual((await call("/api/andere")).status, 404);
});

test("Server: belegter Port → weicht auf freien aus", async () => {
  const a = await startServer();
  const s2 = createStaticServer({ wwwDir: a.www, focus: new FocusState(), port: a.port });
  const p2 = await s2.listen(); assert.notStrictEqual(p2, a.port);
  open.push(s2);
});

/* ---------- Wächter ---------- */
test("Wächter: säubert Namen und verbietet System-/Eigenprozesse", () => {
  assert.deepStrictEqual(sanitizeNames("Discord.exe, steam\nexplorer.exe, ../evil, Tutor, discord"), ["discord", "steam"]);
  assert.deepStrictEqual(sanitizeNames(["x y", "a;b", 5]), ["x y"]);
});

test("Wächter: parst Windows- und Unix-Prozesslisten", () => {
  assert.deepStrictEqual(parseProcessList("win32", '"Discord.exe","123","Console","1","10 K"\r\n"chrome.exe","9","Console","1","1 K"\r\n'), ["Discord.exe", "chrome.exe"]);
  assert.deepStrictEqual(parseProcessList("darwin", "/Applications/Steam.app/Contents/MacOS/steam_osx\n/usr/sbin/cfprefsd\n"), ["steam_osx", "cfprefsd"]);
});

test("Wächter: beendet nur gelistete Programme (Windows)", async () => {
  const calls = [];
  const exec = async (cmd, args) => {
    calls.push([cmd, ...args]);
    return cmd === "tasklist" ? '"Discord.exe","1"\r\n"explorer.exe","2"\r\n"chrome.exe","3"\r\n' : "";
  };
  const g = createGuard({ exec, platform: "win32" });
  assert.deepStrictEqual(await g.tick(["discord", "explorer", "tutor"]), ["discord"]);
  assert.deepStrictEqual(calls.filter((c) => c[0] === "taskkill"), [["taskkill", "/IM", "Discord.exe", "/F"]]);
  assert.deepStrictEqual(await g.tick([]), []);
});

test("Wächter: Unix nutzt pkill -x mit exaktem Namen; Fehler beim Beenden bricht nicht ab", async () => {
  const calls = [];
  const exec = async (cmd, args) => {
    calls.push([cmd, ...args]);
    if (cmd === "ps") return "/usr/bin/steam\n/opt/Discord/Discord\n";
    if (args[1] === "steam") throw new Error("kein Recht");
    return "";
  };
  const g = createGuard({ exec, platform: "linux", selfNames: ["Discord"] });
  assert.deepStrictEqual(await g.tick(["steam", "discord"]), []);       // steam scheitert, discord ist „selbst“
  assert.ok(calls.some((c) => c.join(" ") === "pkill -x steam"));
});

/* ---------- Einstellungen ---------- */
test("Config: speichert validiert und lädt wieder", () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "cfg-")), "s", "settings.json");
  const c = createConfig(file);
  assert.deepStrictEqual(c.get(), { blockedApps: [], autostart: false, trayOnClose: true });
  c.set({ blockedApps: "Discord.exe, explorer, ../x", autostart: 1, trayOnClose: false, evil: "ignoriert" });
  const again = createConfig(file).get();
  assert.deepStrictEqual(again, { blockedApps: ["discord"], autostart: true, trayOnClose: false });
  assert.strictEqual(c.set(null).autostart, true);
});

/* ---------- Handy-Server ---------- */
const http = require("node:http");
const { createPhoneServer, lanAddresses } = require("../lib/phone-server.js");

function fakeOllama() {
  const seen = [];
  const s = http.createServer((req, res) => {
    let body = ""; req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push({ method: req.method, url: req.url, body });
      if (req.url === "/api/tags") { res.setHeader("Content-Type", "application/json"); return res.end('{"models":[{"model":"qwen2.5:3b"}]}'); }
      res.setHeader("Content-Type", "application/x-ndjson");
      res.write('{"message":{"content":"Hallo "}}\n');
      setTimeout(() => res.end('{"message":{"content":"Welt"},"done":true}\n'), 50);
    });
  });
  return new Promise((ok) => s.listen(0, "127.0.0.1", () => ok({ s, seen, port: s.address().port })));
}

test("Handy-Server: Token/QR, Cookie, Oberfläche und nur zwei Ollama-Wege", async () => {
  const www = fs.mkdtempSync(path.join(os.tmpdir(), "www-"));
  fs.writeFileSync(path.join(www, "index.html"), "<title>handy</title>");
  const fo = await fakeOllama();
  const phone = createPhoneServer({ wwwDir: www, ollamaTarget: `http://127.0.0.1:${fo.port}`, port: 0, addresses: () => ["127.0.0.1"] });
  const info = await phone.start();
  try {
    assert.strictEqual(phone.running, true); assert.strictEqual((await phone.start()).token, info.token);
    const base = `http://127.0.0.1:${info.port}`;
    assert.strictEqual((await fetch(base + "/")).status, 401);
    assert.strictEqual((await fetch(base + "/?t=falsch")).status, 401);
    assert.strictEqual((await fetch(base + "/ollama/api/tags")).status, 401);
    // QR geöffnet: Cookie + Weiterleitung ohne Token, mit Handy-Flags
    const open = await fetch(info.url, { redirect: "manual" });
    assert.strictEqual(open.status, 302);
    assert.match(open.headers.get("location"), /^\/index\.html\?(local=1&phone=1|phone=1&local=1)$/);
    const cookie = open.headers.get("set-cookie").split(";")[0];
    assert.doesNotMatch(open.headers.get("location"), /t=/);
    const H = { headers: { Cookie: cookie } };
    assert.match(await (await fetch(base + "/index.html", H)).text(), /handy/);
    assert.strictEqual((await fetch(base + "/../x", H)).status, 404);
    // Weiterleitung an Ollama
    const tags = await (await fetch(base + "/ollama/api/tags", H)).json();
    assert.strictEqual(tags.models[0].model, "qwen2.5:3b");
    const chunks = [];
    const r = await fetch(base + "/ollama/api/chat", { method: "POST", ...H, headers: { ...H.headers, "Content-Type": "application/json" }, body: '{"model":"x","stream":true}' });
    for await (const c of r.body) chunks.push(Buffer.from(c).toString());
    assert.match(chunks.join(""), /Hallo[\s\S]*Welt/);
    assert.ok(chunks.length >= 2, "wird gestreamt, nicht gesammelt");
    assert.deepStrictEqual(fo.seen.map((x) => x.url), ["/api/tags", "/api/chat"]);
    assert.strictEqual(fo.seen[1].body, '{"model":"x","stream":true}');
    // alles andere bei Ollama ist tabu
    for (const [m, p] of [["POST", "/ollama/api/delete"], ["GET", "/ollama/api/chat"], ["POST", "/ollama/api/pull"], ["GET", "/ollama/"]]) {
      assert.strictEqual((await fetch(base + p, { method: m, ...H, ...(m === "POST" ? { body: "{}" } : {}) })).status, 403, m + p);
    }
    assert.strictEqual((await fetch(base + "/api/focus", H)).status, 404);
    assert.strictEqual((await fetch(base + "/index.html", { method: "POST", ...H })).status, 405);
  } finally { await phone.stop(); fo.s.close(); fo.s.closeAllConnections(); }
  assert.strictEqual(phone.running, false);
  await assert.rejects(fetch(`http://127.0.0.1:${info.port}/`));
});

test("Handy-Server: Ollama aus → 502; kein Netz → verständlicher Fehler; Adressen sortiert", async () => {
  const www = fs.mkdtempSync(path.join(os.tmpdir(), "www-"));
  const phone = createPhoneServer({ wwwDir: www, ollamaTarget: "http://127.0.0.1:1", port: 0, addresses: () => ["127.0.0.1"] });
  const info = await phone.start();
  try {
    const cookie = (await fetch(info.url, { redirect: "manual" })).headers.get("set-cookie").split(";")[0];
    const r = await fetch(`http://127.0.0.1:${info.port}/ollama/api/tags`, { headers: { Cookie: cookie } });
    assert.strictEqual(r.status, 502); assert.match((await r.json()).error, /Ollama/);
  } finally { await phone.stop(); }
  await assert.rejects(createPhoneServer({ wwwDir: www, addresses: () => [] }).start(), /Kein WLAN/);
  const ifs = { lo: [{ family: "IPv4", address: "127.0.0.1", internal: true }],
    a: [{ family: "IPv4", address: "100.64.1.2", internal: false }, { family: "IPv6", address: "fe80::1", internal: false }],
    b: [{ family: "IPv4", address: "192.168.1.20", internal: false }], c: [{ family: "IPv4", address: "10.0.0.5", internal: false }] };
  assert.deepStrictEqual(lanAddresses(ifs), ["192.168.1.20", "10.0.0.5", "100.64.1.2"]);
});
