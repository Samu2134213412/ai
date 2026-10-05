/* Brücke zur iPad-App (Capacitor): wählt das Backend, speichert Daten, plant
   Benachrichtigungen, steuert Fokus-Sperre und Bildschirm-Freigabe.
   Im normalen Browser (Python-Server) bleibt alles inaktiv. */
(function (root) {
"use strict";
const Cap = root.Capacitor;
const desktop = !!root.TutorDesktop;           // Electron-App (PC)
const isNative = !!(Cap && Cap.isNativePlatform && Cap.isNativePlatform());
const q = new URLSearchParams(root.location ? root.location.search : "");
let forced = false;
try { forced = q.get("local") === "1" || root.localStorage.getItem("tutor.local") === "1"; } catch (e) { /* privat */ }

const plugin = (name) => {
  try { return isNative ? (Cap.Plugins && Cap.Plugins[name]) || Cap.registerPlugin(name) : null; } catch (e) { return null; }
};
const Prefs = plugin("Preferences"), Notif = plugin("LocalNotifications"),
      Shield = plugin("FocusShield"), Share = plugin("ScreenShare");

const storage = {
  async get(k) {
    try {
      const raw = Prefs ? (await Prefs.get({ key: k })).value : root.localStorage.getItem(k);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  },
  async set(k, v) {
    try { const s = JSON.stringify(v); if (Prefs) await Prefs.set({ key: k, value: s }); else root.localStorage.setItem(k, s); }
    catch (e) { /* voll/privat */ }
  },
};

const Local = root.TutorBackendLocal;
root.TutorBackend = (isNative || forced || desktop) && Local
  ? Local.createBackend({ storage, defaultHost: desktop ? "http://localhost:11434" : "" }) : null;

const N = {
  isNative, isDesktop: desktop,
  hasNotifications: !!Notif, hasShield: !!Shield, hasScreenShare: !!Share,

  async notificationsStatus() {
    if (!Notif) return "unsupported";
    try { return (await Notif.checkPermissions()).display; } catch (e) { return "unsupported"; }
  },
  async requestNotifications() {
    if (!Notif) return "unsupported";
    try { return (await Notif.requestPermissions()).display; } catch (e) { return "denied"; }
  },

  /* Erinnerungen, Einheiten und Fokus-Ende als echte lokale Benachrichtigungen:
     sie feuern auch bei geschlossener App. Wird bei jeder Planer-Änderung neu gesetzt. */
  async reschedule(data) {
    if (!Notif || (await N.notificationsStatus()) !== "granted") return;
    try {
      const pending = (await Notif.getPending()).notifications;
      if (pending.length) await Notif.cancel({ notifications: pending.map((p) => ({ id: p.id })) });
      const now = new Date(), pad = (n) => String(n).padStart(2, "0");
      const iso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
      const list = root.TutorCore.buildNotifications(data, iso).map((n) => ({
        id: n.id, title: n.title, body: n.body,
        schedule: n.on.year ? { at: new Date(n.on.year, n.on.month - 1, n.on.day, n.on.hour, n.on.minute) }
                            : { on: n.on, repeats: true, allowWhileIdle: true },
      }));
      if (data.focus && data.focus.active) list.push({ id: 2, title: "Fokus geschafft 🎉", body: "Zeit für eine kurze Pause.",
        schedule: { at: new Date(Date.now() + data.focus.remaining * 1000) } });
      if (list.length) await Notif.schedule({ notifications: list });
    } catch (e) { /* Planung ist best effort */ }
  },
  onPlannerState(data) { N.reschedule(data); },

  /* Fokus-Sperre (Screen Time): ausgewählte Apps/Webseiten abschirmen. */
  async shieldStatus() { try { return Shield ? await Shield.status() : null; } catch (e) { return null; } },
  async shieldAuthorize() { return Shield ? Shield.requestAuthorization() : null; },
  async shieldPick() { return Shield ? Shield.pickApps() : null; },
  async shield(on) { try { if (Shield) await (on ? Shield.start() : Shield.stop()); } catch (e) { return e.message; } return null; },

  /* Bildschirm-Freigabe (ReplayKit): GoodNotes im Split View live mitlesen. */
  async startBroadcast() { return Share ? Share.startBroadcast() : null; },
  _since: 0,
  async latestFrame() {
    try {
      if (!Share) return null;
      const f = await Share.latestFrame({ since: N._since });
      if (f && f.data) N._since = f.version;       // Daten kommen nur bei neuer Version
      return f;
    } catch (e) { return null; }
  },
};
root.TutorNative = N;
})(typeof self !== "undefined" ? self : globalThis);
