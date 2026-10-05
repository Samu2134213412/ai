/* Wächter für Ablenkungs-Programme: beendet während einer Fokus-Sitzung Prozesse, die der
   Lernende selbst in den Einstellungen eingetragen hat (z. B. Discord, Steam).
   Bewusst vorsichtig: nur exakte Programmnamen, nie System- oder eigene Prozesse. */
const path = require("node:path");

const DENY = new Set(["system", "idle", "registry", "smss", "csrss", "wininit", "winlogon", "services", "lsass",
  "svchost", "explorer", "dwm", "fontdrvhost", "taskmgr", "cmd", "powershell", "pwsh", "conhost", "init",
  "systemd", "launchd", "kernel_task", "windowserver", "loginwindow", "finder", "dock", "systemuiserver",
  "xorg", "xwayland", "gnome-shell", "plasmashell", "kwin_x11", "kwin_wayland", "sshd", "bash", "zsh", "sh",
  "electron", "tutor", "node", "ollama", "ollama app"]);

const norm = (n) => String(n).trim().toLowerCase().replace(/\.exe$/, "");

/* Namen aus den Einstellungen säubern: nur schlichte Programmnamen, ohne Verbotenes. */
function sanitizeNames(list) {
  const items = Array.isArray(list) ? list : String(list).split(/[\n,]+/);
  const out = [];
  for (const raw of items) {
    if (typeof raw !== "string") continue;
    const name = norm(raw);
    if (/^[a-z0-9][a-z0-9 ._+-]{0,58}$/.test(name) && !DENY.has(name) && !out.includes(name)) out.push(name);
  }
  return out;
}

/* Prozessliste → Namen (Originalschreibweise, ohne Pfad). */
function parseProcessList(platform, stdout) {
  const names = new Set();
  for (const line of String(stdout).split(/\r?\n/)) {
    if (!line.trim()) continue;
    if (platform === "win32") {
      const m = /^"([^"]+)"/.exec(line);                 // tasklist /FO CSV /NH
      if (m) names.add(m[1]);
    } else {
      names.add(path.basename(line.trim()));             // ps -A -o comm=
    }
  }
  return [...names];
}

function createGuard({ exec, platform = process.platform, selfNames = [] }) {
  const self = new Set(selfNames.map(norm));
  return {
    /* Beendet alle laufenden Prozesse, deren Name in `blocked` steht. Gibt die beendeten Namen zurück. */
    async tick(blocked) {
      const wanted = sanitizeNames(blocked).filter((n) => !self.has(n));
      if (!wanted.length) return [];
      const out = platform === "win32" ? await exec("tasklist", ["/FO", "CSV", "/NH"]) : await exec("ps", ["-A", "-o", "comm="]);
      const running = parseProcessList(platform, out);
      const killed = [];
      for (const proc of running) {
        const n = norm(proc);
        if (!wanted.includes(n) || DENY.has(n) || self.has(n)) continue;
        try {
          if (platform === "win32") await exec("taskkill", ["/IM", proc, "/F"]);
          else await exec("pkill", ["-x", proc]);
          killed.push(n);
        } catch (e) { /* schon beendet oder keine Berechtigung */ }
      }
      return [...new Set(killed)];
    },
  };
}
module.exports = { createGuard, sanitizeNames, parseProcessList, DENY };
