/* GoodNotes-Leiste (PC/Mac): schlanke Leiste oben, der Blob fliegt nach unten, liest den Bildschirm
   und schreibt Randnotizen darüber. Läuft als durchsichtiges Fenster der PC-App und spricht mit dem Tutor-Server. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const D = window.TutorDesktop;
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* privat */ } },
};
const NOTE_FONT = '"Bradley Hand","Noteworthy","Marker Felt","Segoe Print","Comic Sans MS",cursive';
const NOTE_COLOR = "#e8590c";
const BLOB = 84, TIP = { x: 0.35, y: 0.94 };

let perm = store.get("operm", false), busy = false, pointer = null, pickMode = false, lastShot = null;
const blob = $("blob"), notes = $("notes"), nctx = notes.getContext("2d");

/* ---------------- Server ---------------- */

async function api(path, body) {
  const r = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Fehler ${r.status}`);
  return j;
}
async function stream(path, body, onPiece) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!(r.headers.get("content-type") || "").includes("event-stream")) {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `Fehler ${r.status}`);
    return j;
  }
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "", result = {};
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2);
      if (!line.startsWith("data:")) continue;
      const ev = JSON.parse(line.slice(5));
      if (ev.error) throw new Error(ev.error);
      if (ev.reset) onPiece(null);
      if (ev.t !== undefined) onPiece(ev.t);
      if (ev.done) result = ev;
    }
  }
  return result;
}

/* ---------------- Mausklicks: nur Leiste/Panel fangen sie, der Rest geht an GoodNotes ---------------- */

let interactive = false;
function setInteractive(on) {
  if (on === interactive) return;
  interactive = on;
  if (D) D.overlayInteractive(on);
}
document.addEventListener("mousemove", (e) => {
  setInteractive(pickMode || document.activeElement === $("oinput") || !!e.target.closest("[data-hit]"));
  const r = blob.getBoundingClientRect();                         // Augen folgen der Maus
  const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2), dist = Math.hypot(dx, dy) || 1, k = Math.min(1, dist / 150);
  blob.style.setProperty("--px", (dx / dist) * 3 * k + "px"); blob.style.setProperty("--py", (dy / dist) * 3 * k + "px");
}, { passive: true });
$("oinput").addEventListener("blur", () => setTimeout(() => { if (!document.querySelector("[data-hit]:hover")) setInteractive(pickMode); }, 150));

/* ---------------- Blob ---------------- */

let sayTimer = 0, at = "home";
const setMood = (m) => { blob.dataset.mood = m; };
function say(text, ms = 3500) {
  clearTimeout(sayTimer);
  $("say").textContent = text || ""; $("say").classList.toggle("show", !!text);
  blob.classList.toggle("flip", blob.getBoundingClientRect().left > innerWidth * 0.6);
  if (text && ms) sayTimer = setTimeout(() => $("say").classList.remove("show"), ms);
}
function place(x, y, away) { blob.classList.toggle("away", !!away); blob.style.transform = `translate(${Math.round(x)}px,${Math.round(y)}px)`; }
function goHome(snap) {
  at = "home"; blob.classList.remove("writing", "mirror");
  if (snap) blob.classList.add("snap");
  const r = $("ohome").getBoundingClientRect(); place(r.left, r.top, false);
  if (snap) requestAnimationFrame(() => requestAnimationFrame(() => blob.classList.remove("snap")));
}
const hop = () => { blob.classList.remove("hop"); void blob.offsetWidth; blob.classList.add("hop"); };
function tipTo(x, y) {                                            // Stiftspitze auf Bildschirmpunkt (CSS-Pixel)
  at = "away"; blob.classList.add("mirror");
  place(x - TIP.x * BLOB, y - TIP.y * BLOB, true);
}

/* ---------------- Verlauf ---------------- */

const panel = $("opanel");
function openPanel(open) { panel.hidden = !open; if (open) panel.scrollTop = panel.scrollHeight; }
function addMsg(kind, text) {
  const el = document.createElement("div"); el.className = "msg " + kind; el.textContent = text;
  $("olist").appendChild(el); panel.scrollTop = panel.scrollHeight; return el;
}
function showRoute(el, route) {
  if (!route || !route.model) return;
  const tag = document.createElement("small"); tag.className = "route";
  tag.textContent = (route.tier === "light" ? "⚡ " : "🧠 ") + route.model; el.appendChild(tag);
}
function pickNote(reply) {
  const clean = reply.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
  const sentences = clean.match(/[^.!?]+[.!?]+/g) || [clean];
  const q = sentences.filter((s) => s.trim().endsWith("?"));
  let note = (q.length ? q[q.length - 1] : sentences[0]).trim();
  if (note.length > 130) note = note.slice(0, 130).replace(/\s+\S*$/, "") + " …";
  return note;
}

/* ---------------- Bildschirm lesen & zeigen ---------------- */

async function grabScreen() {
  if (!D) throw new Error("Bildschirm lesen geht nur in der PC-App.");
  const r = await D.overlayCapture();
  if (!r || !r.image) throw new Error("Bildschirmaufnahme nicht möglich (macOS: Systemeinstellungen → Datenschutz → Bildschirmaufnahme erlauben).");
  const img = new Image(); img.src = r.image; await img.decode();
  const cv = document.createElement("canvas"); cv.width = img.naturalWidth; cv.height = img.naturalHeight;
  cv.getContext("2d").drawImage(img, 0, 0);
  return (lastShot = cv);
}
const needPerm = () => { if (perm) return false; say("Schalte 👀 ein, dann darf ich auf den Bildschirm schauen.", 5000); hop(); return true; };

async function lookAtScreen() {
  if (busy || needPerm()) return;
  busy = true;
  try {
    setMood("think"); say("Ich schau mal …", 0);
    tipTo(innerWidth * 0.5, 150); await sleep(500);
    const cv = await grabScreen();
    const res = await api("/api/page", { images: TutorVision.tiles([cv], cv.width, cv.height) });
    openPanel(true);
    addMsg("sys", "👀 Gelesen: " + res.summary.replace(/\s+/g, " ").slice(0, 200) + (res.summary.length > 200 ? " …" : ""));
    setMood(res.unsure ? "think" : "happy");
    say(res.unsure ? `Bei ${res.unsure} Stellen bin ich unsicher – zeig sie mir mit 📍.` : "Hab gelesen! Frag mich oder zeig mir mit 📍 eine Stelle.", 6000); hop();
    await sleep(1200);
  } catch (e) { openPanel(true); addMsg("err", e.message); say("Das hat nicht geklappt."); }
  finally { busy = false; setMood("idle"); goHome(); }
}

function startPick() {
  if (busy || needPerm()) return;
  pickMode = true; $("pick").hidden = false; setInteractive(true); if (D) D.overlayFocus();
  say("Klick auf die Stelle …", 0); setMood("think");
}
function endPick() { pickMode = false; $("pick").hidden = true; setInteractive(false); }
$("pick").addEventListener("click", async (e) => {
  if (e.target.closest(".hintbar")) return;
  const x = e.clientX, y = e.clientY;
  endPick(); busy = true; pointer = { x, y };
  try {
    ring(x, y); tipTo(x, y); hop(); say("Hier?", 0);
    const cv = await grabScreen(), s = cv.width / innerWidth;
    const w = cv.width * 0.4, h = cv.height * 0.3;
    const rect = { x: Math.max(0, Math.min(cv.width - w, x * s - w / 2)), y: Math.max(0, Math.min(cv.height - h, y * s - h / 2)), w, h };
    const res = await api("/api/page", { image: TutorVision.snapshot([cv], rect), focus: "stelle" });
    openPanel(true); addMsg("sys", "📍 Stelle gelesen: " + res.summary.replace(/\s+/g, " ").slice(0, 160));
    setMood("idle"); say("Was ist hier unklar? Frag mich!", 5000); $("oinput").focus(); setInteractive(true);
  } catch (err) { openPanel(true); addMsg("err", err.message); say("Das konnte ich nicht lesen."); }
  finally { busy = false; setMood("idle"); }
});

/* ---------------- Notizen über den Bildschirm schreiben ---------------- */

function sizeNotes() {
  const dpr = window.devicePixelRatio || 1;
  const keep = notes.width ? nctx.getImageData(0, 0, notes.width, notes.height) : null;
  notes.width = Math.round(innerWidth * dpr); notes.height = Math.round(innerHeight * dpr);
  nctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (keep) nctx.putImageData(keep, 0, 0);
}
function ring(x, y) {
  nctx.save(); nctx.strokeStyle = NOTE_COLOR; nctx.lineWidth = 3; nctx.lineCap = "round";
  nctx.beginPath(); nctx.ellipse(x, y, 30, 22, -0.2, 0.3, Math.PI * 2 + 0.1); nctx.stroke(); nctx.restore();
}
function wrapText(ctx, text, maxW) {
  const lines = []; let cur = "";
  for (const word of text.split(" ")) {
    const t = cur ? cur + " " + word : word;
    if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = word; } else cur = t;
  }
  if (cur) lines.push(cur);
  return lines;
}
async function annotate(reply) {
  const fs = 24, lh = fs * 1.25, maxW = 340;
  nctx.font = `${fs}px ${NOTE_FONT}`;
  const lines = wrapText(nctx, pickNote(reply), maxW);
  let x = pointer.x + 44, y = pointer.y - 10;
  if (x + maxW > innerWidth - 12) x = Math.max(12, pointer.x - maxW - 30);
  y = Math.max(fs + 90, Math.min(innerHeight - lines.length * lh - 12, y));
  setMood("idle"); say("");
  tipTo(x, y + fs * 0.9); hop(); await sleep(800);
  blob.classList.add("writing");
  nctx.save(); nctx.font = `${fs}px ${NOTE_FONT}`; nctx.lineJoin = "round"; nctx.lineWidth = fs * 0.2;
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li], by = y + fs * 0.9 + li * lh;
    for (let ci = 0; ci < line.length; ci++) {
      const cx = x + nctx.measureText(line.slice(0, ci)).width, ch = line[ci];
      nctx.strokeStyle = "rgba(255,255,255,.9)"; nctx.strokeText(ch, cx, by);
      nctx.fillStyle = NOTE_COLOR; nctx.fillText(ch, cx, by);
      if (ch !== " ") { tipTo(cx + nctx.measureText(ch).width, by); blob.style.transitionDuration = ".11s"; blob.style.transitionTimingFunction = "linear"; await sleep(26); }
    }
  }
  nctx.restore();
  blob.style.transitionDuration = ""; blob.style.transitionTimingFunction = "";
  blob.classList.remove("writing"); setMood("happy"); say("Probier’s mal selbst! ✏️", 3000); hop();
  await sleep(1500);
}
const clearNotes = () => { nctx.clearRect(0, 0, innerWidth, innerHeight); pointer = null; };

/* ---------------- Fragen ---------------- */

async function ask(text) {
  if (busy || !text.trim()) return;
  busy = true; addMsg("me", text); openPanel(true);
  const el = addMsg("tutor", "…");
  setMood("think"); say("Hmm …", 0);
  let full = "";
  try {
    const res = await stream("/api/chat", { text }, (piece) => {
      if (piece === null) { full = ""; el.textContent = "…"; setMood("think"); return; }
      if (!full) { setMood("talk"); say(""); }
      full += piece; el.textContent = full; panel.scrollTop = panel.scrollHeight;
    });
    if (res.notice) { el.remove(); addMsg("sys", res.notice); setMood("idle"); return; }
    showRoute(el, res.route); setMood("happy");
    if (perm && pointer && full) await annotate(full); else await sleep(900);
  } catch (e) { if (!full) el.remove(); addMsg("err", e.message); say("Oje, da ist was schiefgegangen."); }
  finally { busy = false; setMood("idle"); if (at !== "home") goHome(); }
}

/* ---------------- Verdrahtung ---------------- */

$("oform").addEventListener("submit", (e) => { e.preventDefault(); const v = $("oinput").value; $("oinput").value = ""; ask(v); });
$("operm").addEventListener("click", () => {
  perm = !perm; store.set("operm", perm); $("operm").setAttribute("aria-pressed", String(perm));
  say(perm ? "Danke! Ich schau nur, wenn du’s willst. 👀" : "Okay, ich schaue nicht mehr auf den Bildschirm."); if (perm) hop();
});
$("olook").addEventListener("click", lookAtScreen);
$("opoint").addEventListener("click", startPick);
$("onew").addEventListener("click", async () => { if (busy) return; try { await api("/api/new", {}); $("olist").replaceChildren(); clearNotes(); say("Neue Aufgabe! Worum geht’s?"); } catch (e) { addMsg("err", e.message); } });
$("olog").addEventListener("click", () => openPanel(panel.hidden));
$("oclear").addEventListener("click", () => { clearNotes(); say("Notizen weg. 🧹"); });
$("ohide").addEventListener("click", () => { if (D) D.overlayHide(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (pickMode) { endPick(); say(""); setMood("idle"); } else clearNotes(); } });
addEventListener("resize", () => { sizeNotes(); if (at === "home") goHome(true); });

sizeNotes();
$("operm").setAttribute("aria-pressed", String(perm));
goHome(true);
setMood("happy"); setTimeout(() => setMood("idle"), 1500);
api("/api/state").then(() => say("Ich bin da! 👋", 3000)).catch((e) => { openPanel(true); addMsg("err", e.message); });
})();
