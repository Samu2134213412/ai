/* Planer, Fokus-Sitzung, Erinnerungen und Willkommens-Dialog. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const App = window.TutorApp;
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privat */ } },
};
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
const WD = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];

let data = null, focusLeft = 0, wasFocus = false, shieldChecked = false;

/* ---------------- Benachrichtigungen ---------------- */

async function notify(title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") { App.say(title + " " + body, 6000); return; }
  try {
    const reg = navigator.serviceWorker && await navigator.serviceWorker.getRegistration();
    if (reg) return await reg.showNotification(title, { body, icon: "/icon.svg", tag: title });
  } catch { /* weiter mit Fallback */ }
  try { new Notification(title, { body, icon: "/icon.svg" }); } catch { App.say(title, 6000); }
}
async function askNotifications() {
  if (window.TutorNative && TutorNative.hasNotifications) {
    const r = await TutorNative.requestNotifications(); syncNotifState();
    if (r === "granted") TutorNative.onPlannerState(data || (await App.api("/api/planner")));
    return r;
  }
  if (!("Notification" in window)) { App.say("Dieses Gerät/Browser unterstützt keine Benachrichtigungen. Nutze den Kalender-Export."); return "unsupported"; }
  const r = await Notification.requestPermission();
  syncNotifState();
  if (r === "granted") notify("Super! 🔔", "Ich erinnere dich ans Lernen.");
  return r;
}
function syncNotifState() {
  if (window.TutorNative && TutorNative.hasNotifications) {
    TutorNative.notificationsStatus().then((st) => { $("notifState").textContent = { granted: "✅ erlaubt", denied: "⛔ blockiert (iPad-Einstellungen → Tutor)", prompt: "noch nicht erlaubt" }[st] || st; });
    return;
  }
  const st = !("Notification" in window) ? "nicht unterstützt" : { granted: "✅ erlaubt", denied: "⛔ blockiert (in den Systemeinstellungen ändern)", default: "noch nicht erlaubt" }[Notification.permission];
  $("notifState").textContent = st;
}
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

/* ---------------- Daten ---------------- */

async function load() {
  data = await App.api("/api/planner");
  render();
  return data;
}
async function post(path, body) { data = await App.api(path, body || {}); render(); }

const D = window.TutorDesktop;                   // PC-App (Electron)
if (D) D.onFocusCommand(() => load().catch(() => {}));     // Tray/Erweiterung haben den Fokus geändert → neu laden

function render() {
  if (!data) return;
  if (window.TutorNative && TutorNative.isNative) TutorNative.onPlannerState(data);
  // Aufgaben
  const today = new Date().toISOString().slice(0, 10);
  $("taskList").innerHTML = data.tasks.length ? data.tasks.map((t) => `
    <li class="${t.done ? "done" : ""}" data-id="${t.id}">
      <input type="checkbox" ${t.done ? "checked" : ""} aria-label="erledigt">
      <span><span class="t">${esc(t.title)}</span><br><span class="m ${t.due && t.due < today && !t.done ? "late" : ""}">${esc(t.subject || "–")} · ${t.minutes} min${t.due ? " · bis " + t.due.split("-").reverse().slice(0, 2).join(".") : ""}</span></span>
      <span></span><button type="button" class="del" aria-label="löschen">🗑</button></li>`).join("") : '<li><span class="m">Noch keine Aufgaben.</span></li>';
  // Plan
  const days = {};
  data.plan.blocks.forEach((b) => (days[b.date] = days[b.date] || []).push(b));
  $("planView").innerHTML = Object.keys(days).sort().map((d) => {
    const dt = new Date(d + "T12:00");
    return `<div class="day">${WD[dt.getDay()]}, ${dt.getDate()}.${dt.getMonth() + 1}.</div>` +
      days[d].map((b) => `<div class="blk">${b.start} · ${b.minutes} min · ${esc(b.title)}</div>`).join("");
  }).join("") + data.plan.unplaced.map((u) => `<div class="warn">⚠ „${esc(u.title)}“: ${u.missing} min passen ${esc(u.reason)} nicht rein.</div>`).join("") || '<span class="hint">Nichts zu planen.</span>';
  // Einstellungen
  $("remOn").checked = data.reminders.enabled; $("remTime").value = data.reminders.time;
  if (document.activeElement !== $("blocklist")) $("blocklist").value = data.blocklist.join(" ");
  $("extractTasks").disabled = !App.hasPage();
  setFocus(data.focus);
}

/* ---------------- Fokus ---------------- */

function setFocus(f) {
  focusLeft = f.active ? f.remaining : 0;
  const N = window.TutorNative;
  if (wasFocus && !f.active) {
    if (!(N && N.isNative)) notify("Fokus geschafft 🎉", "Zeit für eine kurze Pause.");
    if (N && N.hasShield) N.shield(false);
  }
  if (!wasFocus && f.active && N && N.hasShield) N.shield(true).then((err) => err && App.say("Sperre nicht aktiv: " + err, 6000));
  wasFocus = f.active;
  paintFocus();
}
function paintFocus() {
  const chip = $("focusChip"), on = focusLeft > 0;
  chip.classList.toggle("live", on);
  chip.textContent = on ? `🔒 ${fmt(focusLeft)}` : "🎯 Fokus";
  $("focusState").textContent = on ? `Fokus läuft – noch ${fmt(focusLeft)}.` : "Kein Fokus aktiv. Starte eine Sitzung – Ablenkungen werden von der Browser-Erweiterung geschlossen.";
  const b = $("focusBtns"); b.replaceChildren();
  const mk = (txt, cls, fn) => { const x = document.createElement("button"); x.type = "button"; x.textContent = txt; if (cls) x.className = cls; x.onclick = fn; b.appendChild(x); };
  if (on) mk("Beenden", "", () => post("/api/focus/stop"));
  else [25, 45].forEach((m) => mk(`${m} min starten`, m === 25 ? "go" : "", async () => { await post("/api/focus/start", { minutes: m }); App.say("Fokus! Ich halte dir den Rücken frei. 🛡", 4000); }));
}
$("focusChip").addEventListener("click", async () => {
  if (focusLeft > 0) return openPlanner();
  await post("/api/focus/start", { minutes: 25 });
  App.say("25 Minuten Fokus – los! 🛡", 4000); App.hop();
});
setInterval(() => {
  if (focusLeft <= 0) return;
  focusLeft -= 1;
  if (focusLeft === 0) setFocus({ active: false, remaining: 0 });   // Ende sofort: Sperre lösen, melden
  else paintFocus();
}, 1000);

/* ---------------- Dialog-Verdrahtung ---------------- */

function openPlanner() { syncNotifState(); load().catch((e) => App.addMsg("err", e.message)); $("plannerDlg").showModal(); }
$("plannerBtn").addEventListener("click", openPlanner);
$("plannerClose").addEventListener("click", () => $("plannerDlg").close());

$("taskForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  await post("/api/tasks", { title: $("tTitle").value, subject: $("tSubject").value, due: $("tDue").value, minutes: +$("tMin").value || 30 });
  e.target.reset(); $("tMin").value = 30;
});
$("taskList").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-id]"); if (!li) return;
  if (e.target.classList.contains("del")) post("/api/tasks/delete", { id: li.dataset.id });
});
$("taskList").addEventListener("change", (e) => {
  const li = e.target.closest("li[data-id]");
  if (li && e.target.type === "checkbox") post("/api/tasks/update", { id: li.dataset.id, fields: { done: e.target.checked } });
});
$("saveBlock").addEventListener("click", () => post("/api/blocklist", { items: $("blocklist").value.split(/[\s,]+/).filter(Boolean) }));
const saveRem = () => post("/api/reminders", { enabled: $("remOn").checked, time: $("remTime").value });
$("remOn").addEventListener("change", async () => { await saveRem(); if ($("remOn").checked && Notification.permission === "default") askNotifications(); });
$("remTime").addEventListener("change", saveRem);
$("notifBtn").addEventListener("click", askNotifications);
$("icsLink").addEventListener("click", async (e) => {
  if (!window.TutorBackend && !App.remote.base) return;     // Browser am eigenen Server: normaler Download
  e.preventDefault();
  const ics = window.TutorBackend ? (await App.api("/api/plan.ics")).ics
    : await (await fetch(App.remote.base + "/api/plan.ics", { headers: App.authHeaders() })).text();
  const file = new File([ics], "lernplan.ics", { type: "text/calendar" });
  try { if (navigator.canShare && navigator.canShare({ files: [file] })) return await navigator.share({ files: [file], title: "Lernplan" }); }
  catch (err) { if (err.name === "AbortError") return; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(file); a.download = "lernplan.ics"; a.click();
});

/* ---------------- Einstellungen (App, PC-App und Server-Betrieb) ---------------- */

let settingsReady = false;
function initSettings(st) {
  if (settingsReady) return; settingsReady = true;
  $("settingsBtn").hidden = false;
  const N = window.TutorNative;
  const owner = !!(st && st.owner);
  const nativeState = async () => {
    if (!N || !N.isNative) return;
    $("nativeSettings").hidden = false;
    const s2 = await N.shieldStatus();
    $("sNativeState").textContent = s2 ? `Fokus-Sperre: ${s2.authorized ? "freigegeben" : "nicht freigegeben"}, ${s2.hasSelection ? "Apps gewählt" : "keine Apps gewählt"}` : "Fokus-Sperre auf diesem Gerät nicht verfügbar.";
  };
  $("settingsBtn").addEventListener("click", async () => {
    const c = await App.api("/api/settings");
    $("sHost").value = c.host; $("sHost").readOnly = !!c.locked;           // im Server-Betrieb legt der Server Ollama fest
    $("sModel").value = c.model; $("sLight").value = c.light_model; $("sVision").value = c.vision_model;
    $("sTest").textContent = ""; nativeState();
    $("pairSettings").hidden = !(D || owner);
    if (D) {
      const d = await D.getSettings();
      $("desktopSettings").hidden = false;
      $("dApps").value = d.blockedApps.join("\n"); $("dTray").checked = d.trayOnClose; $("dAuto").checked = d.autostart; $("dOverlay").checked = d.overlay;
      $("dAutoFocus").checked = d.autoFocus; $("dAutoOverlay").checked = d.autoOverlay; $("dWatch").checked = d.watchScreen; $("dWatchMin").value = d.watchMinutes;
    }
    $("settingsDlg").showModal();
  });
  const save = () => App.api("/api/settings", { host: $("sHost").value, model: $("sModel").value, light_model: $("sLight").value, vision_model: $("sVision").value });
  $("sTestBtn").addEventListener("click", async () => {
    $("sTest").textContent = "Teste …";
    try {
      await save();
      const s2 = await App.api("/api/state");
      $("sTest").textContent = s2.problem ? "⚠ " + s2.problem : `✅ verbunden · ${s2.models.length} Modelle`;
      if (!s2.problem) App.applyState(s2, s2.models);
    } catch (e) { $("sTest").textContent = "⚠ " + e.message; }
  });
  // Weiteres Gerät koppeln: QR-Code mit einmaligem Link (PC-App schaltet dafür den WLAN-Zugang ein)
  $("phoneBtn").addEventListener("click", async () => {
    try {
      let r;
      if (D) r = await D.phoneStart();
      else {
        const p = await App.api("/api/pairing", {});
        if (!p.urls.length) throw new Error("Der Server ist nur auf diesem PC erreichbar. Mit --host 0.0.0.0 starten.");
        r = { url: p.urls[0], qr: p.qr, lan: p.lan };
      }
      $("phoneQr").src = r.qr || ""; $("phoneQr").hidden = !r.qr;
      $("phoneUrl").textContent = r.url;
      $("phoneStop").hidden = !D;
      $("phoneDlg").showModal();
    } catch (e) { $("sTest").textContent = "⚠ " + e.message.replace(/^Error invoking remote method '[^']+': (Error: )?/, ""); }
  });
  // iPad-App: mit einem Tutor-Server (z. B. dem PC) verbinden statt direkt mit Ollama zu sprechen
  const connected = !!App.remote.base;
  $("connectSettings").hidden = !(N && N.isNative);
  $("cState").textContent = connected ? `Verbunden mit ${App.remote.base}` : "Nicht verbunden – die App spricht direkt mit Ollama.";
  $("cForm").hidden = connected; $("cDisconnect").hidden = !connected;
  $("cConnect").addEventListener("click", async () => {
    const base = $("cServer").value.trim().replace(/\/$/, "");
    try {
      if (!/^https?:\/\/[^\s/]+(:\d+)?$/.test(base)) throw new Error("Adresse bitte als http://IP:8780 angeben.");
      const r = await fetch(base + "/api/pair", { method: "POST", body: JSON.stringify({ code: $("cCode").value.trim() }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || "Verbindung fehlgeschlagen.");
      localStorage.setItem("tutor.server", base); localStorage.setItem("tutor.token", j.token);
      location.reload();
    } catch (e) { $("cState").textContent = "⚠ " + (e.message === "Failed to fetch" ? "Server nicht erreichbar (selbes WLAN? Adresse/Port richtig?)" : e.message); }
  });
  $("cDisconnect").addEventListener("click", () => { localStorage.removeItem("tutor.server"); localStorage.removeItem("tutor.token"); location.reload(); });
  if (D) $("overlayBtn").addEventListener("click", () => D.overlayToggle());
  $("phoneStop").addEventListener("click", async () => { if (D) await D.phoneStop(); $("phoneDlg").close(); App.say("Handy-Zugang beendet."); });
  $("settingsDlg").addEventListener("close", async () => {
    if (D && !$("desktopSettings").hidden) await D.setSettings({ blockedApps: $("dApps").value.split(/[\n,]+/), trayOnClose: $("dTray").checked, autostart: $("dAuto").checked, overlay: $("dOverlay").checked,
      autoFocus: $("dAutoFocus").checked, autoOverlay: $("dAutoOverlay").checked, watchScreen: $("dWatch").checked, watchMinutes: +$("dWatchMin").value || 3 });
    try { await save(); App.applyState(await App.api("/api/state")); } catch (e) { /* Test zeigt Fehler */ } });
  $("sNotif").addEventListener("click", async () => { await askNotifications(); $("sNativeState").textContent = $("notifState").textContent; });
  $("sShield").addEventListener("click", async () => {
    try { await N.shieldAuthorize(); await N.shieldPick(); } catch (e) { $("sNativeState").textContent = "⚠ " + e.message; }
    nativeState();
  });
}
App.initSettings = initSettings;
if (window.TutorBackend) initSettings({});

$("extractTasks").addEventListener("click", async () => {
  const box = $("candidates"); box.textContent = "Lese …";
  try {
    const { candidates } = await App.api("/api/tasks/extract", { images: App.pageImages() });
    const known = new Set(data.tasks.map((t) => (t.title + "|" + t.due).toLowerCase()));
    const fresh = candidates.filter((c) => !known.has((c.title + "|" + c.due).toLowerCase()));
    if (!fresh.length) { box.textContent = "Keine neuen Aufgaben gefunden."; return; }
    box.replaceChildren(...fresh.map((c) => {
      const d = document.createElement("div"); d.className = "cand";
      const b = document.createElement("button"); b.type = "button"; b.textContent = "＋";
      b.onclick = async () => { await post("/api/tasks", c); d.remove(); };
      d.append(b, document.createTextNode(`${c.title}${c.subject ? " (" + c.subject + ")" : ""}${c.due ? " · bis " + c.due : ""} · ${c.minutes} min`));
      return d;
    }));
  } catch (e) { box.textContent = e.message; }
});

/* ---------------- Erinnerungs-Takt (solange die App offen ist) ---------------- */

const fired = new Set(store.get("fired", []));
function once(key, fn) {
  if (fired.has(key)) return; fired.add(key);
  store.set("fired", [...fired].slice(-200)); fn();
}
async function tick() {
  let d; try { d = await App.api("/api/planner"); } catch { return; }
  data = d; setFocus(d.focus);
  if (!shieldChecked) {                           // App-Start ohne Fokus: übrig gebliebene Sperre aufheben
    shieldChecked = true;
    if (!d.focus.active && window.TutorNative && TutorNative.hasShield) TutorNative.shield(false);
  }
  if (window.TutorNative && TutorNative.isNative) { if (document.getElementById("plannerDlg").open) render(); return; }   // App: native Benachrichtigungen
  const now = new Date(), hm = now.toTimeString().slice(0, 5), day = now.toISOString().slice(0, 10);
  if (d.reminders.enabled && hm >= d.reminders.time && hm < addMin(d.reminders.time, 30)) once(`daily-${day}`, () => notify("Zeit zum Lernen 📚", d.tasks.some((t) => !t.done) ? "Du hast noch offene Aufgaben – kurze Runde?" : "Wie wär’s mit einer Wiederholung?"));
  for (const b of d.plan.blocks) {
    if (b.date !== day) continue;
    const diff = minutes(b.start) - minutes(hm);
    if (diff >= 0 && diff <= 10) once(`blk-${b.task_id}-${b.date}-${b.start}`, () => notify(`Gleich: ${b.title}`, `${b.minutes} min ab ${b.start}.`));
  }
  if (document.getElementById("plannerDlg").open) render();
}
const minutes = (hm) => +hm.slice(0, 2) * 60 + +hm.slice(3, 5);
const addMin = (hm, m) => { const t = Math.min(1439, minutes(hm) + m); return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`; };
setInterval(tick, 10000); setTimeout(tick, 1500);

/* ---------------- Willkommen ---------------- */

$("askNotif").addEventListener("click", async (e) => { const r = await askNotifications(); e.target.textContent = r === "granted" ? "✅" : "…"; });
if (!store.get("welcomed", false)) setTimeout(() => { $("welcome").showModal(); store.set("welcomed", true); }, 900);
})();
