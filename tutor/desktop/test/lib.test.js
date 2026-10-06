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
  assert.deepStrictEqual(c.get(), { blockedApps: [], autostart: false, trayOnClose: true });
  c.set({ blockedApps: "Discord.exe, explorer, ../x", autostart: 1, trayOnClose: false, evil: "ignoriert" });
  const again = createConfig(file).get();
  assert.deepStrictEqual(again, { blockedApps: ["discord"], autostart: true, trayOnClose: false });
  assert.strictEqual(c.set(null).autostart, true);
});

