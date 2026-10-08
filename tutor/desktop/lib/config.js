/* Einstellungen der Desktop-App (settings.json im Benutzerordner). */
const fs = require("node:fs");
const path = require("node:path");
const { sanitizeNames } = require("./guard.js");

const DEFAULTS = { blockedApps: [], autostart: false, trayOnClose: true, overlay: false,
  autoFocus: false, autoOverlay: false, autoMinutes: 120, watchScreen: false, watchMinutes: 3,
  pool: false, poolKey: "", poolJobs: 1 };

function createConfig(file) {
  let data = { ...DEFAULTS };
  try { data = { ...DEFAULTS, ...JSON.parse(fs.readFileSync(file, "utf8")) }; } catch (e) { /* neu */ }
  data.blockedApps = sanitizeNames(data.blockedApps);
  data.autoMinutes = Math.max(20, Math.min(240, parseInt(data.autoMinutes, 10) || 120));
  data.watchMinutes = Math.max(1, Math.min(30, parseInt(data.watchMinutes, 10) || 3));
  data.poolJobs = Math.max(1, Math.min(4, parseInt(data.poolJobs, 10) || 1));
  data.poolKey = String(data.poolKey || "").trim().slice(0, 64);
  const save = () => {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file + ".tmp", JSON.stringify(data, null, 2));
    fs.renameSync(file + ".tmp", file);
  };
  return {
    get: () => ({ ...data, blockedApps: [...data.blockedApps] }),
    set(partial) {
      if (!partial || typeof partial !== "object") return this.get();
      if ("blockedApps" in partial) data.blockedApps = sanitizeNames(partial.blockedApps);
      if ("autostart" in partial) data.autostart = !!partial.autostart;
      if ("trayOnClose" in partial) data.trayOnClose = !!partial.trayOnClose;
      if ("overlay" in partial) data.overlay = !!partial.overlay;
      for (const k of ["autoFocus", "autoOverlay", "watchScreen"]) if (k in partial) data[k] = !!partial[k];
      if ("autoMinutes" in partial) data.autoMinutes = Math.max(20, Math.min(240, parseInt(partial.autoMinutes, 10) || 120));
      if ("watchMinutes" in partial) data.watchMinutes = Math.max(1, Math.min(30, parseInt(partial.watchMinutes, 10) || 3));
      if ("pool" in partial) data.pool = !!partial.pool;
      if ("poolKey" in partial) data.poolKey = String(partial.poolKey || "").trim().slice(0, 64);
      if ("poolJobs" in partial) data.poolJobs = Math.max(1, Math.min(4, parseInt(partial.poolJobs, 10) || 1));
      if (data.pool && data.poolKey.length < 8) data.pool = false;        // ohne gültigen Klassencode kein Pool
      save();
      return this.get();
    },
  };
}
module.exports = { createConfig, DEFAULTS };
