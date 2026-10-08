/* Mitrechnen (iPad/Handy/Browser im Klassen-Pool): Das Gerät lädt ein kleines Modell vom Tutor-PC, rechnet es im
   Browser (wllama = llama.cpp als WebAssembly, auf neueren Geräten mit WebGPU) und arbeitet Anfragen der Klasse ab.
   Läuft nur, solange die Seite offen und sichtbar ist – iPadOS pausiert Web-Apps im Hintergrund. */
(function () {
"use strict";
const App = window.TutorApp;
if (!App) return;
const $ = (id) => document.getElementById(id);
const store = { get: (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* privat */ } } };
const R = App.remote || { base: "", token: "" };
const H = () => ({ ...(App.authHeaders ? App.authHeaders() : {}) });
const dev = (() => { let d = store.get("tutor.dev", ""); if (!d) { d = Math.random().toString(36).slice(2, 12); store.set("tutor.dev", d); } return d; })();
const VENDOR = new URL("/vendor/wllama/", location.href).href;   // aus der eigenen Oberfläche (PWA vom PC oder App-Bundle)

let on = false, wl = null, loaded = "", done = 0, statusText = "", loop = null, lock = null;
const show = (t) => { statusText = t; if ($("hState")) $("hState").textContent = t; };
const model = () => ($("hModel") && $("hModel").value) || store.get("tutor.helpModel", "qwen2.5:1.5b");

async function status() {
  const r = await fetch(R.base + "/api/pool/status", { headers: H() });
  if (!r.ok) throw new Error("Kein Tutor-Server.");
  return r.json();
}

async function loadModel(name) {
  if (wl && loaded === name) return;
  if (wl) { try { await wl.exit(); } catch (e) { /* schon weg */ } wl = null; loaded = ""; }
  show("Lade Rechenkern …");
  const { Wllama } = await import(VENDOR + "index.js");
  wl = new Wllama({ default: VENDOR + "wllama.wasm" }, { suppressNativeLog: true, parallelDownloads: 2,
    logger: { debug() {}, log() {}, warn() {}, error: console.error } });
  wl.setCompat({ worker: VENDOR + "compat/wllama.js", wasm: VENDOR + "compat/wllama.wasm" });   // Safari/iPad
  const url = R.base + "/api/pool/model.gguf?name=" + encodeURIComponent(name);
  await wl.loadModelFromUrl(url, { n_ctx: 4096, headers: H(), useCache: window.isSecureContext,
    progressCallback: ({ loaded: l, total }) => show(`Lade Modell vom PC … ${total ? Math.round((l / total) * 100) : 0} %`) });
  loaded = name;
}

/* Eine Aufgabe rechnen und stückweise zurückschicken. */
async function work(job) {
  const ctl = new AbortController();
  let buf = "", sending = Promise.resolve(), cancel = false;
  const push = (extra) => {
    const content = buf; buf = "";
    sending = sending.then(async () => {
      if (cancel) return;
      const r = await fetch(R.base + "/api/pool/push?dev=" + dev, { method: "POST", headers: { ...H(), "Content-Type": "application/json" },
        body: JSON.stringify({ job: job.job, content, ...extra }) });
      const d = await r.json().catch(() => ({ cancel: true }));
      if (d.cancel) { cancel = true; ctl.abort(); }
    }).catch(() => { cancel = true; ctl.abort(); });
    return sending;
  };
  const timer = setInterval(() => { if (buf) push(); }, 250);
  show(`Rechne für die Klasse … (${done} erledigt)`);
  try {
    const stream = await wl.createChatCompletion({ messages: job.messages, stream: true, abortSignal: ctl.signal,
      temperature: typeof job.temperature === "number" ? job.temperature : 0.6, max_tokens: Math.min(1024, job.max_tokens || 512) });
    for await (const chunk of stream) {
      const piece = chunk.choices && chunk.choices[0] && chunk.choices[0].delta && chunk.choices[0].delta.content;
      if (piece) buf += piece;
      if (cancel) break;
    }
    clearInterval(timer);
    if (!cancel) { await push({ done: true }); done++; }
  } catch (e) {
    clearInterval(timer);
    if (!cancel) await push({ error: "Tablet: " + (e.message || e) });
  }
  show(`Hilft mit · ${done} Anfrage(n) für die Klasse erledigt`);
}

let pullCtl = null;
async function run() {
  for (;;) {
    if (!on) return;
    const name = model();
    if (document.hidden) { show("Pausiert (Seite im Hintergrund)"); await new Promise((r) => document.addEventListener("visibilitychange", r, { once: true })); continue; }
    try {
      await loadModel(name);
      if (!statusText.startsWith("Hilft")) show(`Hilft mit · ${done} Anfrage(n) für die Klasse erledigt`);
      const r = await fetch(R.base + `/api/pool/pull?dev=${dev}&name=${encodeURIComponent(navigator.platform || "Tablet")}&models=${encodeURIComponent(name)}`, { headers: H(), signal: (pullCtl = new AbortController()).signal });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "Server antwortet nicht.");
      const { job } = await r.json();
      if (job && on) await work(job);
    } catch (e) {
      if (!on) return;
      show("⚠ " + (e.message || e) + " – neuer Versuch gleich …");
      await new Promise((r) => setTimeout(r, 8000));
    }
  }
}

async function wake(want) {
  try {
    if (want && navigator.wakeLock && !lock) { lock = await navigator.wakeLock.request("screen"); lock.addEventListener("release", () => { lock = null; }); }
    if (!want && lock) { await lock.release(); lock = null; }
  } catch (e) { /* nicht erlaubt */ }
}

function setOn(v) {
  on = v; store.set("tutor.help", v ? "1" : "");
  if ($("hOn")) $("hOn").checked = v;
  wake(v);
  if (v && !loop) loop = run().finally(() => { loop = null; });
  if (!v && pullCtl) pullCtl.abort();
  if (!v) show(done ? `Aus · ${done} Anfrage(n) erledigt` : "Aus");
}

/* Einstellungen: nur im Server-Betrieb und nicht in der PC-App (die trägt mit Ollama bei). */
async function refreshBox() {
  const box = $("helpSettings");
  if (!box || window.TutorDesktop) return;
  let st; try { st = await status(); } catch (e) { box.hidden = true; return; }
  box.hidden = false;
  const sel = $("hModel"), pick = store.get("tutor.helpModel", "qwen2.5:1.5b");
  sel.replaceChildren(...(st.models.length ? st.models : [pick]).map((m) => new Option(m + (m.endsWith("0.5b") ? " (sehr klein)" : m.endsWith("3b") ? " (nur neue iPads)" : ""), m)));
  sel.value = st.models.includes(pick) ? pick : sel.options[0].value;
  $("hOn").disabled = !st.enabled || !st.models.length;
  if (!st.enabled) show("Am PC ist der Klassen-Pool aus (PC-App → ⚙︎ → Klassen-Pool).");
  else if (!st.models.length) show("Am PC fehlt ein kleines Modell. Dort: ollama pull qwen2.5:1.5b");
  else if (!statusText) show(on ? "Hilft mit" : "Aus");
  else show(statusText);
}

function init() {
  if (!$("helpSettings")) return;
  $("settingsBtn").addEventListener("click", () => setTimeout(refreshBox, 0));
  $("hOn").addEventListener("change", () => setOn($("hOn").checked));
  $("hModel").addEventListener("change", () => { store.set("tutor.helpModel", $("hModel").value); if (on && pullCtl) pullCtl.abort(); });   // nächste Runde lädt das neue Modell
  if (store.get("tutor.help", "") === "1") status().then((st) => { if (st.enabled && st.models.length) setOn(true); }).catch(() => {});
  document.addEventListener("visibilitychange", () => { if (on && !document.hidden) wake(true); });
}
init();
window.TutorHelper = { setOn, get state() { return { on, done, loaded, status: statusText }; } };
})();
