/* Reine Logik der Erweiterung (ohne chrome.*-APIs, damit mit Node testbar). */
(function (root) {
  "use strict";

  function hostOf(url) {
    try {
      const u = new URL(url);
      return /^https?:$/.test(u.protocol) ? u.hostname.toLowerCase().replace(/^www\./, "") : "";
    } catch (e) { return ""; }
  }

  /* Host oder Subdomain eines Blocklist-Eintrags (m.youtube.com → youtube.com). */
  function isBlocked(url, blocklist) {
    const host = hostOf(url);
    if (!host) return false;
    return (blocklist || []).some((d) => host === d || host.endsWith("." + d));
  }

  /* Verbleibende Sekunden seit dem letzten Abruf (lokal weitergezählt). */
  function remaining(state, nowMs) {
    if (!state || !state.active) return 0;
    return Math.max(0, Math.round(state.remaining - (nowMs - state.fetchedAt) / 1000));
  }

  function fmt(sec) {
    const m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  const api = { hostOf, isBlocked, remaining, fmt };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.TutorFocus = api;
})(typeof self !== "undefined" ? self : globalThis);
