/* Tutor-Oberfläche: Leiste + Blob, Chat, Seiten-Ansicht mit Notiz-Ebene. */
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* privat */ } },
};

const NOTE_FONT = '"Bradley Hand","Noteworthy","Marker Felt","Segoe Print","Comic Sans MS",cursive';
const NOTE_COLOR = "#e8590c";
const PEN_COLOR = "#1864ab";
const BLOB_AWAY = 84;
const TIP = { x: 0.35, y: 0.94 };           // Stiftspitze im gespiegelten Blob (Anteil der Größe)

let state = null;
let busy = false;
let perm = store.get("perm", false);
let page = null;                              // { read: bool, pdf?, pdfNo? }
let pointer = null;                           // letzte angetippte Stelle (0–1)
let noteY = 0;                                // nächste freie Zeile für Randnotizen (Canvas-px)
let chatOpen = false;

const blob = $("blob"), homeEl = $("home"), say$ = $("say");
const pageCv = $("page"), ink = $("ink"), wrap = $("pageWrap"), area = $("area");
const pctx = pageCv.getContext("2d"), ictx = ink.getContext("2d");

/* ---------------- API ---------------- */

/* Verbindung zu einem Tutor-Server auf einem anderen Gerät (iPad-App → PC): Adresse + Geräte-Token. */
const REMOTE = (() => { try { return { base: (localStorage.getItem("tutor.server") || "").replace(/\/$/, ""), token: localStorage.getItem("tutor.token") || "" }; } catch (e) { return { base: "", token: "" }; } })();
const authHeaders = () => (REMOTE.token ? { "X-Tutor-Token": REMOTE.token } : {});

async function api(path, body) {
  const B = window.TutorBackend;
  if (B) {                                       // iPad-App ohne Server: Logik läuft lokal
    try { return await B.api(path, body); } catch (e) { throw e; }
  }
  const r = await fetch(REMOTE.base + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Fehler ${r.status}`);
  return j;
}

async function stream(path, body, onPiece) {
  if (window.TutorBackend) return window.TutorBackend.stream(path, body, onPiece);
  const r = await fetch(REMOTE.base + path, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body),
  });
  if (!(r.headers.get("content-type") || "").includes("event-stream")) {
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `Fehler ${r.status}`);
    return j;                                 // z. B. { notice }
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
      if (ev.error) { const e = new Error(ev.error); e.state = ev.state; throw e; }
      if (ev.reset) onPiece(null);
      if (ev.t !== undefined) onPiece(ev.t);
      if (ev.done) result = ev;
    }
  }
  return result;
}

/* ---------------- Blob ---------------- */

let sayTimer = 0, at = "home";
function setMood(m) { blob.dataset.mood = m; }
function say(text, ms = 3500) {
  clearTimeout(sayTimer);
  say$.textContent = text || "";
  say$.classList.toggle("show", !!text);
  const r = blob.getBoundingClientRect();
  blob.classList.toggle("flip", r.left + r.width / 2 > innerWidth * 0.6);
  if (text && ms) sayTimer = setTimeout(() => say$.classList.remove("show"), ms);
}
function place(x, y, away) {
  blob.classList.toggle("away", !!away);
  blob.style.transform = `translate(${Math.round(x)}px,${Math.round(y)}px)`;
}
function goHome(snap = false) {
  at = "home";
  blob.classList.remove("writing", "mirror");
  if (snap) blob.classList.add("snap");
  const r = homeEl.getBoundingClientRect();
  place(r.left, r.top, false);
  if (snap) requestAnimationFrame(() => requestAnimationFrame(() => blob.classList.remove("snap")));
}
function hop() { blob.classList.remove("hop"); void blob.offsetWidth; blob.classList.add("hop"); }
function canvasToClient(x, y) {
  const r = ink.getBoundingClientRect();
  return { x: r.left + (x / ink.width) * r.width, y: r.top + (y / ink.height) * r.height };
}
/* Blob so platzieren, dass die Stiftspitze auf dem Canvas-Punkt (x, y) liegt. */
function tipTo(x, y) {
  const p = canvasToClient(x, y);
  at = "away";
  blob.classList.add("mirror");
  place(p.x - TIP.x * BLOB_AWAY, p.y - TIP.y * BLOB_AWAY, true);
}
document.addEventListener("pointermove", (e) => {
  const r = blob.getBoundingClientRect();
  const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
  const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 150);
  blob.style.setProperty("--px", (dx / d) * 3 * k + "px");
  blob.style.setProperty("--py", (dy / d) * 3 * k + "px");
}, { passive: true });

/* ---------------- Chat ---------------- */

function setChat(open) {
  chatOpen = open;
  $("chat").hidden = !open;
  if (open) $("chat").scrollTop = $("chat").scrollHeight;
  fitPage();
  if (at === "home") goHome(true);
}
function addMsg(kind, text) {
  const el = document.createElement("div");
  el.className = "msg " + kind; el.textContent = text;
  $("log").appendChild(el);
  $("chat").scrollTop = $("chat").scrollHeight;
  return el;
}
homeEl.addEventListener("click", () => setChat(!chatOpen));
area.addEventListener("pointerdown", () => { if (chatOpen && !busy) setChat(false); });

/* ---------------- Zustand → UI ---------------- */

function applyState(s, models) {
  if (!s) return;
  state = s;
  document.querySelectorAll("#stage i").forEach((el, i) => el.classList.toggle("on", s.stage > i));
  $("stageLabel").textContent = s.attempts === 0 ? "–" : s.stage > 3 ? "Lösung" : `Hinweis ${s.stage}/3`;
  const sub = $("subject");
  if (![...sub.options].some((o) => o.value === s.subject)) sub.add(new Option(s.subject, s.subject), 1);
  sub.value = s.subject;
  if (models) {
    const m = $("model"), set = new Set([...models, s.model]);
    m.replaceChildren(...[...set].map((n) => new Option(n, n)));
  }
  $("model").value = s.model;
}

/* ---------------- Unterhaltung ---------------- */

function pickNote(reply) {
  const clean = reply.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
  const sentences = clean.match(/[^.!?]+[.!?]+/g) || [clean];
  const q = sentences.filter((s) => s.trim().endsWith("?"));
  let note = (q.length ? q[q.length - 1] : sentences[0]).trim();
  if (note.length > 130) note = note.slice(0, 130).replace(/\s+\S*$/, "") + " …";
  return note;
}

/* Kleines Etikett unter der Antwort: welches Modell hat geantwortet (und warum). */
let noticeShown = false;
function showRoute(el, route) {
  if (!route || !route.model) return;
  const tag = document.createElement("small");
  tag.className = "route";
  tag.textContent = (route.tier === "light" ? "⚡ " : "🧠 ") + route.model;
  tag.title = route.reason || "";
  el.appendChild(tag);
  if (route.notice && !noticeShown) { noticeShown = true; addMsg("sys", route.notice); }
}

async function run(path, payload, userText) {
  if (busy) return;
  busy = true;
  const me = userText ? addMsg("me", userText) : null;
  setChat(true);
  const el = addMsg("tutor", "…");
  setMood("think"); say("Hmm …", 0);
  let full = "";
  try {
    const res = await stream(path, payload, (piece) => {
      if (piece === null) {                       // Modell ist abgerutscht → Anzeige verwerfen, neuer Versuch
        full = ""; el.textContent = "…"; setMood("think"); return;
      }
      if (!full) { setMood("talk"); say(""); }
      full += piece; el.textContent = full;
      $("chat").scrollTop = $("chat").scrollHeight;
    });
    if (res.notice) { el.remove(); me && me.remove(); addMsg("sys", res.notice); applyState(res.state); setMood("idle"); say(""); return; }
    applyState(res.state);
    showRoute(el, res.route);
    setMood("happy");
    if (perm && page && full) await annotate(full);
    else await sleep(900);
  } catch (e) {
    if (!full) el.remove();
    addMsg("err", e.message); applyState(e.state);
    say("Oje, da ist was schiefgegangen.");
  } finally {
    busy = false; setMood("idle");
    if (at !== "home") goHome();
  }
}

async function handleInput(raw) {
  const text = raw.trim();
  if (!text) return;
  if (text.startsWith("/")) {
    const [cmd, ...rest] = text.split(/\s+/), arg = rest.join(" ");
    if (cmd === "/neu") return newTask(arg);
    if (cmd === "/aufgeben") return giveUp();
    if (cmd === "/modell" && arg) return switchModel(arg);
    if (cmd === "/hilfe") { setChat(true); return addMsg("sys", "Befehle: /neu [Aufgabe] · /aufgeben · /modell <name> – oder nutze die Chips unter der Leiste."); }
  }
  return run("/api/chat", { text }, text);
}

async function newTask(text = "") {
  if (busy) return;
  try {
    clearPage();
    $("log").replaceChildren();
    if (text) return await run("/api/new", { text }, text);
    applyState((await api("/api/new", {})).state);
    addMsg("sys", "Neue Aufgabe – Hinweisstufe zurückgesetzt. Beschreibe sie und was du schon versucht hast.");
    setChat(true); say("Los geht’s!");
  } catch (e) { addMsg("err", e.message); setChat(true); }
}
const giveUp = () => run("/api/giveup", {}, "🏳 Ich gebe auf – bitte zeig mir die Lösung.");

async function switchModel(name) {
  try { applyState((await api("/api/model", { name })).state); say("Modell: " + name); }
  catch (e) { setChat(true); addMsg("err", e.message); $("model").value = state.model; }
}

/* ---------------- Seite laden ---------------- */

const MAX_EDGE = 2200;
function setPage(source, w, h) {
  const s = Math.min(1, MAX_EDGE / Math.max(w, h));
  const W = Math.round(w * s), H = Math.round(h * s);
  pageCv.width = ink.width = W; pageCv.height = ink.height = H;
  pctx.fillStyle = "#fff"; pctx.fillRect(0, 0, W, H);
  pctx.drawImage(source, 0, 0, W, H);
  ictx.clearRect(0, 0, W, H);
  noteY = H * 0.05; pointer = null;
  page = { read: false, pdf: page && page.pdf, pdfNo: page && page.pdfNo };
  $("empty").hidden = true; wrap.hidden = false;
  $("reread").hidden = $("export").hidden = false;
  fitPage();
}
function clearPage() {
  page = null; pointer = null; wrap.hidden = true; $("fixText").hidden = true; $("empty").hidden = false; $("pager").hidden = true;
  $("reread").hidden = $("export").hidden = true;
  if (at !== "home") goHome();
}
function fitPage() {
  if (!page) return;
  const cs = getComputedStyle(area);
  const aw = area.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const ah = area.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  const k = Math.min(aw / pageCv.width, ah / pageCv.height);
  wrap.style.width = Math.floor(pageCv.width * k) + "px";
  wrap.style.height = Math.floor(pageCv.height * k) + "px";
}

function loadImage(file) {
  return new Promise((res, rej) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => { res(img); URL.revokeObjectURL(url); };
    img.onerror = () => rej(new Error("Bild konnte nicht gelesen werden."));
    img.src = url;
  });
}
async function ensurePdfLib() {
  if (window.pdfjsLib) return;
  const base = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  await new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = base + "pdf.min.js"; s.onload = res;
    s.onerror = () => rej(new Error("PDF-Bibliothek nicht ladbar (Internet nötig). Exportiere die Seite in GoodNotes als PNG."));
    document.head.appendChild(s);
  });
  window.pdfjsLib.GlobalWorkerOptions.workerSrc = base + "pdf.worker.min.js";
}
async function showPdfPage(n) {
  const p = await page.pdf.getPage(n), vp = p.getViewport({ scale: 2 });
  const cv = document.createElement("canvas"); cv.width = vp.width; cv.height = vp.height;
  await p.render({ canvasContext: cv.getContext("2d"), viewport: vp }).promise;
  page.pdfNo = n;
  setPage(cv, cv.width, cv.height);
  $("pgNo").textContent = `${n} / ${page.pdf.numPages}`;
  $("pager").hidden = page.pdf.numPages < 2;
}
async function openFile(file) {
  if (!file) return;
  try {
    if (file.type === "application/pdf") {
      await ensurePdfLib();
      const pdf = await window.pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
      page = { pdf, pdfNo: 1, read: false };
      await showPdfPage(1);
    } else {
      const img = await loadImage(file);
      page = null; $("pager").hidden = true;
      setPage(img, img.naturalWidth, img.naturalHeight);
    }
  } catch (e) { setChat(true); return addMsg("err", e.message); }
  if (perm) await readPage(); else say("Schalte „Darf zuschauen“ ein, dann lese ich die Seite.", 5000);
}

/* ---------------- Seite lesen (Vision) ---------------- */

/* Vorverarbeitung für schlechte Handschrift: Graustufen, automatischer Kontrast
   (2–98 %-Perzentil), dunkle Seiten invertieren, kleine Bilder hochskalieren. */
function enhance(cv) {
  const c = cv.getContext("2d"), img = c.getImageData(0, 0, cv.width, cv.height), d = img.data;
  const hist = new Uint32Array(256);
  for (let i = 0; i < d.length; i += 4) {
    const y = (d[i] * 0.299 + d[i + 1] * 0.587 + d[i + 2] * 0.114) | 0;
    d[i] = y; hist[y]++;
  }
  const n = d.length / 4;
  let acc = 0, lo = 0, hi = 255, mean = 0;
  for (let v = 0; v < 256; v++) mean += v * hist[v];
  mean /= n;
  for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc >= n * 0.02) { lo = v; break; } }
  acc = 0;
  for (let v = 255; v >= 0; v--) { acc += hist[v]; if (acc >= n * 0.02) { hi = v; break; } }
  const span = Math.max(40, hi - lo), invert = mean < 110;
  for (let i = 0; i < d.length; i += 4) {
    let y = Math.max(0, Math.min(255, ((d[i] - lo) / span) * 255));
    if (invert) y = 255 - y;
    d[i] = d[i + 1] = d[i + 2] = y; d[i + 3] = 255;
  }
  c.putImageData(img, 0, 0);
  return cv;
}

function cropCanvas(x, y, w, h, minEdge, maxEdge) {
  const k = Math.min(maxEdge / Math.max(w, h), Math.max(1, minEdge / Math.max(w, h)));
  const cv = document.createElement("canvas");
  cv.width = Math.round(w * k); cv.height = Math.round(h * k);
  const c = cv.getContext("2d");
  c.fillStyle = "#fff"; c.fillRect(0, 0, cv.width, cv.height);
  c.imageSmoothingQuality = "high";
  c.drawImage(pageCv, x, y, w, h, 0, 0, cv.width, cv.height);
  c.drawImage(ink, x, y, w, h, 0, 0, cv.width, cv.height);
  return enhance(cv);
}

/* Hohe Seiten in 2–3 überlappende Bänder teilen: größere Schrift = bessere Lesung. */
function pageTiles() {
  const W = pageCv.width, H = pageCv.height, r = H / W;
  const n = r > 2 ? 3 : r > 1.25 ? 2 : 1;
  const th = n === 1 ? H : Math.round(H / n * 1.18);
  return Array.from({ length: n }, (_, i) => {
    const y = n === 1 ? 0 : Math.min(H - th, Math.round((H - th) * i / (n - 1)));
    return cropCanvas(0, y, W, th, 1400, 1800).toDataURL("image/jpeg", 0.9);
  });
}
function snapshot(rect, maxEdge = 900) {
  return cropCanvas(rect.x, rect.y, rect.w, rect.h, 700, maxEdge).toDataURL("image/jpeg", 0.9);
}

/* ---------------- Live-Zugriff: Fenster teilen & Kurzbefehl-Screenshots ---------------- */

let cap = null;                               // { stream, video } bei laufender Freigabe
async function pickWindow() {
  say("Suche Fenster …", 0);
  const list = await TutorDesktop.listWindows();
  say("");
  if (!list.length) throw new Error("Keine Fenster gefunden.");
  list.sort((a, b) => (/goodnotes/i.test(b.name) ? 1 : 0) - (/goodnotes/i.test(a.name) ? 1 : 0) || a.screen - b.screen);
  const box = $("winList"), dlg = $("winDlg");
  return new Promise((resolve) => {
    let picked = null;
    box.replaceChildren(...list.map((w) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "winCard" + (/goodnotes/i.test(w.name) ? " pick" : "");
      const img = document.createElement("img"); img.alt = ""; if (w.thumb) img.src = w.thumb;
      const t = document.createElement("span"); t.textContent = (w.screen ? "🖥 " : "") + w.name;
      b.append(img, t);
      b.onclick = () => { picked = w.id; dlg.close(); };
      return b;
    }));
    dlg.addEventListener("close", () => resolve(picked), { once: true });
    dlg.showModal();
  });
}
async function grabFrame() {
  const v = cap.video;
  if (!v.videoWidth) await new Promise((r) => v.addEventListener("loadeddata", r, { once: true }));
  const cv = document.createElement("canvas");
  cv.width = v.videoWidth; cv.height = v.videoHeight;
  cv.getContext("2d").drawImage(v, 0, 0);
  page = null; $("pager").hidden = true;
  setPage(cv, cv.width, cv.height);
}
function stopCapture() {
  if (!cap) return;
  cap.stream.getTracks().forEach((t) => t.stop());
  cap = null; $("capture").textContent = "🖥 Fenster teilen";
  say("Freigabe beendet.");
}
async function toggleCapture() {
  if (window.TutorNative && TutorNative.hasScreenShare) {      // iPad: ReplayKit-Freigabe
    try { await TutorNative.startBroadcast(); say("Wähle „Tutor“ und starte die Übertragung.", 6000); }
    catch (e) { setChat(true); addMsg("err", "Freigabe nicht möglich: " + e.message); }
    return;
  }
  if (cap) return stopCapture();
  try {
    if (window.TutorDesktop) {                                  // PC-App: Fenster in der App wählen
      const id = await pickWindow();
      if (!id) return;
      if (!(await TutorDesktop.chooseWindow(id))) throw new Error("Fenster nicht mehr verfügbar.");
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false });
    const video = document.createElement("video");
    video.srcObject = stream; video.muted = true; await video.play();
    cap = { stream, video };
    stream.getVideoTracks()[0].addEventListener("ended", stopCapture);
    $("capture").textContent = "⏹ Freigabe beenden";
    await grabFrame();
    if (perm) await readPage(); else say("Schalte „Darf zuschauen“ ein, dann lese ich mit.", 5000);
  } catch (e) {
    if (e.name !== "NotAllowedError") { setChat(true); addMsg("err", "Freigabe nicht möglich: " + e.message); }
  }
}
if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) $("capture").hidden = false;
if (window.TutorNative && TutorNative.hasScreenShare) { $("capture").hidden = false; $("capture").textContent = "📱 Bildschirm teilen"; }
$("capture").addEventListener("click", toggleCapture);

/* Neuer Screenshot: vom Server (Kurzbefehl) oder, in der App, von der ReplayKit-Freigabe. */
let shotVersion = null;
const b64Blob = (b64, type) => { const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new Blob([u], { type }); };
async function pollShot() {
  try {
    let version, getBlob;
    if (window.TutorNative && TutorNative.hasScreenShare) {
      const f = await TutorNative.latestFrame();
      if (!f) return;
      version = f.version; getBlob = async () => b64Blob(f.data, "image/jpeg");
    } else if (window.TutorBackend) return;
    else { version = (await api("/api/shot")).version; getBlob = async () => (await fetch(REMOTE.base + "/api/shot.img", { headers: authHeaders() })).blob(); }
    if (shotVersion === null) { shotVersion = version; return; }
    if (version === shotVersion || busy) return;
    shotVersion = version;
    const blobData = await getBlob();
    stopCapture();
    await openFile(new File([blobData], "screenshot", { type: blobData.type }));
    hop();
  } catch { /* offline: nächster Versuch */ }
}
setInterval(pollShot, 2000);

async function readPage() {
  if (cap && !busy) await grabFrame();      // frisches Bild direkt aus dem geteilten Fenster
  if (!page || busy) return;
  if (!perm) return say("Ich darf noch nicht zuschauen – schalte 👀 ein.", 4500);
  busy = true;
  try {
    setMood("think"); say("Ich schau mal drauf …", 0);
    tipTo(ink.width * 0.5, ink.height * 0.12); await sleep(700);
    const res = await api("/api/page", { images: pageTiles() });
    page.read = true; page.transcript = res.summary; applyState(res.state);
    $("fixText").hidden = false;
    $("fixText").textContent = res.unsure ? `📝 Abschrift (${res.unsure}× unsicher)` : "📝 Abschrift";
    setChat(true);
    addMsg("sys", "👀 Gelesen: " + res.summary.replace(/\s+/g, " ").slice(0, 220) + (res.summary.length > 220 ? " …" : ""));
    setMood(res.unsure ? "think" : "happy");
    say(res.unsure ? `Bei ${res.unsure} Stellen bin ich unsicher – schau bitte in die Abschrift ✏️` : "Hab sie gelesen! Was soll ich mir ansehen?", 6000);
    hop();
    await sleep(1200);
  } catch (e) {
    setChat(true); addMsg("err", e.message); say("Das Lesen hat nicht geklappt.");
  } finally { busy = false; setMood("idle"); goHome(); }
}

/* ---------------- Tippen & Zeichnen auf der Seite ---------------- */

let drag = null;
function norm(e) {
  const r = ink.getBoundingClientRect();
  return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
}
ink.addEventListener("pointerdown", (e) => {
  ink.setPointerCapture(e.pointerId);
  const n = norm(e);
  drag = { id: e.pointerId, type: e.pointerType, sx: e.clientX, sy: e.clientY, last: n, drawing: false };
});
ink.addEventListener("pointermove", (e) => {
  if (!drag || drag.id !== e.pointerId) return;
  const n = norm(e);
  if (!drag.drawing && drag.type !== "touch" && Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) > 4) drag.drawing = true;
  if (!drag.drawing) return;
  const p = e.pressure > 0 && drag.type === "pen" ? e.pressure : 0.5;
  ictx.strokeStyle = PEN_COLOR; ictx.lineCap = ictx.lineJoin = "round";
  ictx.lineWidth = ink.width * 0.0022 * (0.6 + p * 1.2);
  ictx.beginPath();
  ictx.moveTo(drag.last.x * ink.width, drag.last.y * ink.height);
  ictx.lineTo(n.x * ink.width, n.y * ink.height);
  ictx.stroke();
  drag.last = n;
});
ink.addEventListener("pointerup", (e) => {
  if (!drag || drag.id !== e.pointerId) return;
  const d = drag; drag = null;
  if (!d.drawing) onTap(norm(e));
});
ink.addEventListener("pointercancel", () => { drag = null; });

async function onTap(n) {
  if (busy || !page) return;
  if (!perm) return say("Ich darf nicht zuschauen – schalte 👀 ein.", 4500);
  if (!page.read) { await readPage(); }
  busy = true;
  pointer = n;
  try {
    const W = ink.width, H = ink.height;
    marker(n.x * W, n.y * H);
    setMood("think"); tipTo(n.x * W, n.y * H); hop(); say("Hier?", 0);
    const cw = W * 0.4, ch = H * 0.3;
    const x = Math.max(0, Math.min(W - cw, n.x * W - cw / 2)), y = Math.max(0, Math.min(H - ch, n.y * H - ch / 2));
    const res = await api("/api/page", { image: snapshot({ x, y, w: cw, h: ch }), focus: "stelle" });
    applyState(res.state);
    setMood("idle"); say("Was ist hier unklar? Frag mich!", 4500);
    $("askInput").focus();
  } catch (e) {
    setChat(true); addMsg("err", e.message); say("Das konnte ich nicht lesen.");
  } finally { busy = false; setMood("idle"); }
}

function marker(x, y) {
  ictx.save();
  ictx.strokeStyle = NOTE_COLOR; ictx.lineWidth = ink.width * 0.003; ictx.lineCap = "round";
  ictx.beginPath(); ictx.ellipse(x, y, ink.width * 0.022, ink.width * 0.016, -0.2, 0.3, Math.PI * 2 + 0.1); ictx.stroke();
  ictx.restore();
}

/* ---------------- Randnotiz schreiben ---------------- */

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
  const W = ink.width, H = ink.height, fs = Math.round(W * 0.027), lh = fs * 1.25;
  const maxW = W * 0.34;
  ictx.font = `${fs}px ${NOTE_FONT}`;
  const lines = wrapText(ictx, pickNote(reply), maxW);
  let x, y;
  if (pointer) {
    const px = pointer.x * W, py = pointer.y * H;
    x = px + maxW + fs * 2 < W ? px + fs * 1.6 : px - maxW - fs * 1.2;
    y = py - fs * 0.6;
  } else {
    x = W * 0.62; y = noteY;
  }
  x = Math.max(8, Math.min(W - maxW - 8, x));
  y = Math.max(fs, Math.min(H - lines.length * lh - 8, y));
  noteY = y + lines.length * lh + fs * 0.9;
  if (noteY > H * 0.85) noteY = H * 0.05;

  setMood("idle"); say("");
  tipTo(x, y + fs * 0.9); hop(); await sleep(950);
  blob.classList.add("writing");

  ictx.save();
  ictx.font = `${fs}px ${NOTE_FONT}`; ictx.textBaseline = "alphabetic";
  ictx.lineJoin = "round"; ictx.lineWidth = fs * 0.2;
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li], by = y + fs * 0.9 + li * lh;
    for (let ci = 0; ci < line.length; ci++) {
      const cx = x + ictx.measureText(line.slice(0, ci)).width, ch = line[ci];
      ictx.strokeStyle = "rgba(255,255,255,.85)"; ictx.strokeText(ch, cx, by);
      ictx.fillStyle = NOTE_COLOR; ictx.fillText(ch, cx, by);
      if (ch !== " ") {
        const w = ictx.measureText(ch).width;
        tipTo(cx + w, by);
        blob.style.transitionDuration = ".11s"; blob.style.transitionTimingFunction = "linear";
        await sleep(28);
      }
    }
  }
  ictx.restore();
  blob.style.transitionDuration = ""; blob.style.transitionTimingFunction = "";
  blob.classList.remove("writing");
  setMood("happy"); say("Probier’s mal selbst! ✏️", 3000); hop();
  pointer = null;
  await sleep(1600);
}

/* ---------------- Export ---------------- */

async function exportPng() {
  if (!page) return;
  const cv = document.createElement("canvas");
  cv.width = pageCv.width; cv.height = pageCv.height;
  const c = cv.getContext("2d");
  c.drawImage(pageCv, 0, 0); c.drawImage(ink, 0, 0);
  const blobData = await new Promise((r) => cv.toBlob(r, "image/png"));
  const file = new File([blobData], "seite-mit-notizen.png", { type: "image/png" });
  try {
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({ files: [file], title: "Seite mit Notizen" });
      return;
    }
  } catch (e) { if (e.name === "AbortError") return; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blobData); a.download = file.name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

/* ---------------- Verdrahtung ---------------- */

$("askForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("askInput").value; $("askInput").value = "";
  handleInput(v);
});
$("perm").addEventListener("click", async () => {
  perm = !perm; store.set("perm", perm); syncPerm();
  if (perm) { say("Danke! Ich schau nur, wenn du’s willst. 👀"); hop(); if (page && !page.read) await readPage(); }
  else { say("Okay, ich bleibe hier oben."); if (at !== "home") goHome(); }
});
function syncPerm() { $("perm").setAttribute("aria-pressed", String(perm)); }
$("share").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (e) => { openFile(e.target.files[0]); e.target.value = ""; });
$("reread").addEventListener("click", readPage);
$("fixText").addEventListener("click", () => {
  if (!page || !page.transcript) return;
  $("fixArea").value = page.transcript;
  $("fixDlg").showModal();
});
$("fixDlg").addEventListener("close", async () => {
  if ($("fixDlg").returnValue !== "ok") return;
  try {
    const text = $("fixArea").value.trim();
    applyState((await api("/api/page_text", { text })).state);
    page.transcript = text; $("fixText").textContent = "📝 Abschrift";
    say("Danke, jetzt hab ich’s richtig! 🙌"); hop();
  } catch (e) { setChat(true); addMsg("err", e.message); }
});
$("export").addEventListener("click", exportPng);
$("giveup").addEventListener("click", giveUp);
$("newTask").addEventListener("click", () => newTask());
$("save").addEventListener("click", async () => {
  try { const r = await api("/api/save", {}); say(r.saved ? "Gespeichert 💾" : "Noch nichts zu speichern."); }
  catch (e) { setChat(true); addMsg("err", e.message); }
});
$("subject").addEventListener("change", async (e) => {
  let v = e.target.value;
  if (v === "__other") { v = (prompt("Fach / Thema:") || "").trim(); if (!v) { e.target.value = state ? state.subject : ""; return; } }
  try { applyState((await api("/api/subject", { subject: v })).state); say(v ? "Fach: " + v : "Allgemein"); }
  catch (err) { addMsg("err", err.message); }
});
$("model").addEventListener("change", (e) => switchModel(e.target.value));
$("prevPg").addEventListener("click", () => page && page.pdf && page.pdfNo > 1 && showPdfPage(page.pdfNo - 1));
$("nextPg").addEventListener("click", () => page && page.pdf && page.pdfNo < page.pdf.numPages && showPdfPage(page.pdfNo + 1));

document.addEventListener("paste", (e) => {
  const f = [...(e.clipboardData ? e.clipboardData.files : [])].find((x) => x.type.startsWith("image/") || x.type === "application/pdf");
  if (f) { e.preventDefault(); openFile(f); }
});
let dragDepth = 0;
const hasFiles = (e) => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
addEventListener("dragenter", (e) => { if (hasFiles(e)) { dragDepth++; $("drop").hidden = false; } });
addEventListener("dragleave", (e) => { if (hasFiles(e) && --dragDepth <= 0) { dragDepth = 0; $("drop").hidden = true; } });
addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault(); dragDepth = 0; $("drop").hidden = true;
  openFile(e.dataTransfer.files[0]);
});
addEventListener("resize", () => {
  fitPage();
  if (at === "home") goHome(true);
});
new ResizeObserver(() => { if (at === "home") goHome(true); }).observe($("bar"));
new ResizeObserver(fitPage).observe(area);

/* ---------------- Start ---------------- */

window.TutorApp = {
  api, say, hop, setChat, addMsg, applyState, remote: REMOTE, authHeaders,
  hasPage: () => !!page,
  pageImages: () => pageTiles(),
  busy: () => busy,
};

(async function init() {
  syncPerm();
  goHome(true);
  setMood("happy"); setTimeout(() => setMood("idle"), 1800);
  try {
    const s = await api("/api/state");
    applyState(s, s.models);
    say("Hallo! Ich bin dein Tutor. 👋", 4500);
    if (s.server && window.TutorApp.initSettings) window.TutorApp.initSettings(s);      // Server-Betrieb: Einstellungen/Koppeln
    if (s.problem) {
      setChat(true); addMsg("err", s.problem);
      if (window.TutorBackend) setTimeout(() => $("settingsBtn").click(), 600);
    }
  } catch (e) {
    setChat(true); addMsg("err", e.message);
  }
})();
})();
