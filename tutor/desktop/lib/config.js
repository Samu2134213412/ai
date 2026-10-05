/* Einstellungen der Desktop-App (settings.json im Benutzerordner). */
const fs = require("node:fs");
const path = require("node:path");
const { sanitizeNames } = require("./guard.js");

const DEFAULTS = { blockedApps: [], autostart: false, trayOnClose: true };

function createConfig(file) {
  let data = { ...DEFAULTS };
  try { data = { ...DEFAULTS, ...JSON.parse(fs.readFileSync(file, "utf8")) }; } catch (e) { /* neu */ }
  data.blockedApps = sanitizeNames(data.blockedApps);
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
      save();
      return this.get();
    },
  };
}
module.exports = { createConfig, DEFAULTS };
