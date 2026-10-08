const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createGuard, sanitizeNames, parseProcessList } = require("../lib/guard.js");
const { createConfig } = require("../lib/config.js");

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
  assert.deepStrictEqual(c.get(), { blockedApps: [], autostart: false, trayOnClose: true, overlay: false, autoFocus: false, autoOverlay: false, autoMinutes: 120, watchScreen: false, watchMinutes: 3, pool: false, poolKey: "", poolJobs: 1 });
  c.set({ blockedApps: "Discord.exe, explorer, ../x", autostart: 1, trayOnClose: false, overlay: 1, evil: "ignoriert" });
  const again = createConfig(file).get();
  assert.deepStrictEqual(again, { blockedApps: ["discord"], autostart: true, trayOnClose: false, overlay: true, autoFocus: false, autoOverlay: false, autoMinutes: 120, watchScreen: false, watchMinutes: 3, pool: false, poolKey: "", poolJobs: 1 });
  assert.strictEqual(c.set(null).autostart, true);
});


/* ---------- GoodNotes-Wächter und Automatik ---------- */
const { createWatcher, createAuto } = require("../lib/watch.js");

test("Wächter: offen sofort, geschlossen erst nach zwei Fehlsichtungen; Ausfall der Quelle ändert nichts", async () => {
  let names = [], fail = false; const events = [];
  const w = createWatcher({ getNames: async () => { if (fail) throw new Error("x"); return names; }, onOpen: async () => events.push("open"), onClose: async () => events.push("close") });
  assert.strictEqual(await w.tick(), false);
  names = ["Chrome", "GoodNotes – Mathe"]; assert.strictEqual(await w.tick(), true);
  assert.strictEqual(await w.tick(), true); assert.deepStrictEqual(events, ["open"]);          // nicht doppelt
  names = ["Chrome"]; assert.strictEqual(await w.tick(), true);                                  // 1. Fehlsichtung: noch offen
  names = ["goodnotes.exe"]; assert.strictEqual(await w.tick(), true);                           // wieder da → Zähler zurück
  names = []; await w.tick(); fail = true; assert.strictEqual(await w.tick(), true);             // Quelle fällt aus → bleibt offen
  fail = false; await w.tick(); assert.strictEqual(await w.tick(), false);
  assert.deepStrictEqual(events, ["open", "close"]);
});

function autoFixture(cfg = {}) {
  let t = 1000, f = { active: false }; const calls = [], notes = [];
  const config = { autoFocus: true, autoOverlay: true, autoMinutes: 60, ...cfg };
  const focus = { info: async () => ({ ...f, remaining: 1 }), start: async (m) => { calls.push(["start", m]); f = { active: true }; }, stop: async () => { calls.push(["stop"]); f = { active: false }; } };
  const overlay = { show: () => { calls.push(["show"]); return true; }, hide: () => calls.push(["hide"]) };
  const auto = createAuto({ getConfig: () => config, focus, overlay, notify: (a, b) => notes.push(a), now: () => t });
  return { auto, calls, notes, setActive: (v) => (f = { active: v }), advance: (s) => (t += s), config };
}

test("Automatik: GoodNotes auf → Leiste + Fokus; zu → beides wieder aus", async () => {
  const x = autoFixture();
  await x.auto.onOpen();
  assert.deepStrictEqual(x.calls, [["show"], ["start", 60]]); assert.match(x.notes[0], /Fokus läuft/);
  await x.auto.onClose();
  assert.deepStrictEqual(x.calls.slice(2), [["stop"], ["hide"]]); assert.strictEqual(x.auto.focusOn, false);
});

test("Automatik: greift nicht in selbst gestartete Sitzungen ein und tut nichts, wenn abgeschaltet", async () => {
  const mine = autoFixture(); mine.setActive(true);
  await mine.auto.onOpen(); await mine.auto.onClose();
  assert.ok(!mine.calls.some((c) => c[0] === "start" || c[0] === "stop"));                       // eigene Sitzung bleibt
  const off = autoFixture({ autoFocus: false, autoOverlay: false });
  await off.auto.onOpen(); await off.auto.onClose();
  assert.deepStrictEqual(off.calls, []);
});

test("Automatik: Verlängern vor Ablauf; manuelles Beenden wird respektiert", async () => {
  const x = autoFixture(); await x.auto.onOpen(); x.calls.length = 0;
  x.advance(20); await x.auto.keepAlive(); assert.deepStrictEqual(x.calls, []);                  // noch Zeit
  x.advance(60 * 60); await x.auto.keepAlive(); assert.deepStrictEqual(x.calls, [["start", 60]]);  // kurz vor Ende → verlängert
  const y = autoFixture(); await y.auto.onOpen(); y.calls.length = 0;
  y.advance(30); y.setActive(false); await y.auto.keepAlive();                                   // Lernender beendet den Fokus
  assert.strictEqual(y.auto.focusOn, false); y.advance(3600); await y.auto.keepAlive();
  assert.deepStrictEqual(y.calls, []);                                                           // und nichts startet ihn wieder
});

test("Pool-Einstellungen: ohne gültigen Klassencode bleibt der Pool aus", () => {
  const f = require("node:path").join(require("node:os").tmpdir(), "pool-cfg-" + Date.now() + ".json");
  const { createConfig } = require("../lib/config.js");
  const c = createConfig(f);
  assert.equal(c.get().pool, false);
  assert.equal(c.set({ pool: true, poolKey: "kurz" }).pool, false);
  const on = c.set({ pool: true, poolKey: "klasse-7b-geheim", poolJobs: 9 });
  assert.equal(on.pool, true);
  assert.equal(on.poolJobs, 4);
  assert.equal(on.autostart, true);          // rechnet auch ungenutzt im Hintergrund mit
  assert.equal(on.trayOnClose, true);
});
