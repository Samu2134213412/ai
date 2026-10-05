/* Lokales Backend für die iPad-App: dieselben Routen wie web.py, aber ohne Server.
   Spricht direkt mit Ollama (WLAN) und speichert Aufgaben/Einstellungen auf dem Gerät. */
(function (root) {
"use strict";
const C = root.TutorCore || (typeof require !== "undefined" ? require("./core.js") : null);

const DEFAULT_CONFIG = { host: "", model: "qwen2.5:32b", vision_model: "qwen2.5vl:7b",
  temperature: 0.6, subject: "", language: "Deutsch", turnsPerStage: 2, minAttempts: 2 };

class TutorError extends Error {}

const fullName = (m) => (m.includes(":") ? m : m + ":latest");
const stripData = (x) => String(x).replace(/^data:image\/[a-z+]+;base64,/, "");
const pad = (n) => String(n).padStart(2, "0");

function localNow(d) {
  d = d || new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function createBackend(env) {
  const F = env.fetch || ((...a) => root.fetch(...a));
  const storage = env.storage;
  const clock = env.clock || (() => ({ iso: localNow(), ms: Date.now() }));
  let templatePromise = null;
  const getTemplate = () => (templatePromise = templatePromise || (env.template
    ? Promise.resolve(env.template) : F("prompts/tutor.md").then((r) => r.text())));

  const S = { cfg: { ...DEFAULT_CONFIG }, tasks: [], reminders: { enabled: false, time: "16:00" },
    blocklist: [...C.DEFAULT_BLOCKLIST], focus: { ends_at: 0, minutes: 0 }, sessions: [],
    conv: [newTask()], confirm: false, started: clock().iso };
  let ready = null;

  function newTask() { return { title: "", attempts: 0, givenUp: false, messages: [], pageNotes: [] }; }
  const cur = () => S.conv[S.conv.length - 1];
  const persist = () => storage.set("tutor.data", { cfg: S.cfg, tasks: S.tasks, reminders: S.reminders,
    blocklist: S.blocklist, focus: S.focus, sessions: S.sessions.slice(-30) });
  const load = () => (ready = ready || storage.get("tutor.data").then((d) => {
    if (d) { S.cfg = { ...DEFAULT_CONFIG, ...d.cfg }; S.tasks = d.tasks || []; S.reminders = d.reminders || S.reminders;
      S.blocklist = d.blocklist || S.blocklist; S.focus = d.focus || S.focus; S.sessions = d.sessions || []; }
  }));

  /* ---------- Ollama ---------- */

  const connHint = () => S.cfg.host
    ? `Ollama ist unter ${S.cfg.host} nicht erreichbar.\n→ Läuft Ollama auf dem Mac/PC (OLLAMA_HOST=0.0.0.0, OLLAMA_ORIGINS=*) und sind beide im selben WLAN?`
    : "Noch keine Ollama-Adresse eingestellt. Öffne ⚙︎ und trage z. B. http://192.168.0.10:11434 ein.";
  const missHint = (m) => `Das Modell '${m}' ist nicht installiert.\n→ ollama pull ${m}`;

  async function ollama(path, init) {
    if (!S.cfg.host) throw new TutorError(connHint());
    let r;
    try { r = await F(S.cfg.host.replace(/\/$/, "") + path, init); }
    catch (e) { throw new TutorError(connHint()); }
    return r;
  }
  async function failFromResponse(r, model) {
    let msg = ""; try { msg = (await r.json()).error || ""; } catch (e) { /* kein JSON */ }
    if (r.status === 404) throw new TutorError(missHint(model));
    throw new TutorError("Ollama-Fehler: " + (msg || r.status));
  }
  async function installedModels() {
    const r = await ollama("/api/tags");
    if (!r.ok) throw new TutorError("Ollama-Fehler: " + r.status);
    const d = await r.json();
    return (d.models || []).map((m) => m.model || m.name).filter(Boolean);
  }
  async function checkModel(name) {
    const have = new Set((await installedModels()).map(fullName));
    if (!have.has(fullName(name))) throw new TutorError(missHint(name));
  }
  async function* chatStream(model, messages) {
    const r = await ollama("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: true, options: { temperature: S.cfg.temperature } }) });
    if (!r.ok) await failFromResponse(r, model);
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
          if (!line) continue;
          const ev = JSON.parse(line);
          if (ev.error) throw new TutorError("Ollama-Fehler: " + ev.error);
          const piece = ev.message && ev.message.content;
          if (piece) yield piece;
        }
      }
    } catch (e) {
      if (e instanceof TutorError) throw e;
      throw new TutorError(connHint());
    }
  }
  async function vision(prompt, image) {
    const r = await ollama("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: S.cfg.vision_model, stream: false, options: { temperature: 0.1 },
        messages: [{ role: "user", content: prompt, images: [stripData(image)] }] }) });
    if (!r.ok) await failFromResponse(r, S.cfg.vision_model);
    const d = await r.json();
    return ((d.message && d.message.content) || "").trim();
  }

  /* ---------- Sitzung ---------- */

  const stageNow = () => C.stageOf(cur(), S.cfg.turnsPerStage);
  function state() {
    const t = cur(), stage = stageNow();
    return { model: S.cfg.model, vision_model: S.cfg.vision_model, subject: S.cfg.subject, stage,
      attempts: t.attempts, given_up: t.givenUp, title: t.title, has_page: t.pageNotes.length > 0 };
  }
  async function messages() {
    const sys = C.buildPrompt(await getTemplate(), S.cfg.subject, S.cfg.language) +
      C.plannerBlock(C.openTasks(S.tasks), clock().iso.slice(0, 10)) + C.pageBlock(cur()) +
      C.statusBlock(cur(), S.cfg.turnsPerStage);
    return [{ role: "system", content: sys }, ...cur().messages];
  }
  /* Eine Runde; bei Fehler wird sie zurückgenommen (zählt nicht als Versuch). */
  async function streamTurn(text, onPiece) {
    const t = cur();
    if (!t.title) t.title = text.slice(0, 80);
    t.attempts += 1; t.messages.push({ role: "user", content: text });
    const parts = [];
    try {
      for await (const piece of chatStream(S.cfg.model, await messages())) { parts.push(piece); onPiece(piece); }
    } catch (e) {
      t.messages.pop(); t.attempts -= 1;
      if (e instanceof TutorError) e.state = state();
      throw e;
    } finally {
      if (parts.length) t.messages.push({ role: "assistant", content: parts.join("") });
    }
    return { done: true, state: state() };
  }
  function requestGiveUp() {
    const t = cur();
    if (t.attempts === 0) return ["none", "Es gibt noch keine Aufgabe. Beschreibe zuerst, woran du arbeitest."];
    if (t.givenUp) return ["done", "Die Lösung ist für diese Aufgabe bereits freigegeben. /neu für die nächste."];
    if (t.attempts < S.cfg.minAttempts && !S.confirm) {
      S.confirm = true;
      return ["confirm", `Du hast erst ${t.attempts} Versuch(e). Noch ein Anlauf lohnt sich oft. Zum Bestätigen nochmal /aufgeben eingeben.`];
    }
    S.confirm = false; t.givenUp = true;
    return ["ok", ""];
  }

  /* ---------- Planer ---------- */

  const nowIso = () => clock().iso.slice(0, 16);
  const focusInfo = () => {
    const remaining = Math.max(0, Math.floor(S.focus.ends_at - clock().ms / 1000));
    return { active: remaining > 0, remaining, ends_at: S.focus.ends_at, minutes: S.focus.minutes, blocklist: [...S.blocklist] };
  };
  const plannerState = () => ({ tasks: S.tasks.map((t) => ({ ...t })), plan: C.plan(S.tasks, nowIso()),
    reminders: { ...S.reminders }, blocklist: [...S.blocklist], focus: focusInfo() });
  const uid = () => [...crypto.getRandomValues(new Uint8Array(4))].map((b) => b.toString(16).padStart(2, "0")).join("");

  async function plannerRoute(path, body) {
    if (path === "/api/tasks") {
      const t = C.cleanTask(body);
      if (!t) throw new TutorError("Titel fehlt.");
      S.tasks.push({ ...t, id: uid(), done: false, created: clock().iso });
    } else if (path === "/api/tasks/update") {
      const t = S.tasks.find((x) => x.id === String(body.id || ""));
      if (!t) throw new TutorError("Aufgabe nicht gefunden.");
      const f = body.fields || {};
      if ("done" in f) t.done = !!f.done;
      const merged = C.cleanTask({ ...t, ...f });
      if (merged) Object.assign(t, merged);
    } else if (path === "/api/tasks/delete") {
      S.tasks = S.tasks.filter((x) => x.id !== String(body.id || ""));
    } else if (path === "/api/reminders") {
      const time = /^([01]\d|2[0-3]):[0-5]\d$/.test(body.time || "") ? body.time : "16:00";
      S.reminders = { enabled: !!body.enabled, time };
    } else if (path === "/api/blocklist") {
      S.blocklist = C.setBlocklist(body.items || []);
    } else if (path === "/api/focus/start") {
      const m = Math.max(1, Math.min(240, parseInt(body.minutes || 25, 10) || 25));
      S.focus = { ends_at: clock().ms / 1000 + m * 60, minutes: m };
    } else if (path === "/api/focus/stop") {
      S.focus = { ends_at: 0, minutes: 0 };
    }
    persist();
    return plannerState();
  }

  /* ---------- Routen ---------- */

  async function pageRoute(body) {
    const imgs = (body.images || [body.image || ""]).map(stripData).filter((x) => x.length >= 100).slice(0, 4);
    if (!imgs.length) throw new TutorError("Kein Bild empfangen.");
    const focus = String(body.focus || "").slice(0, 200);
    const prompt = C.HANDWRITING_PROMPT + (focus ? ` Konzentriere dich besonders auf: ${focus}` : "");
    const parts = [];
    for (const img of imgs) parts.push(await vision(prompt, img));
    const summary = parts.filter(Boolean).join("\n");
    if (!summary) throw new TutorError("Auf der Seite konnte ich nichts lesen.");
    cur().pageNotes.push((focus === "stelle" ? "Bereich: " + summary : summary).slice(0, 2500));
    return { summary, unsure: (summary.match(/\[\?/g) || []).length, state: state() };
  }

  async function api(path, body) {
    await load();
    if (path === "/api/state") {
      let models = [], problem = null;
      try { models = (await installedModels()).sort(); } catch (e) { problem = e.message; }
      return { ...state(), models, problem, local: true };
    }
    if (path === "/api/settings") {
      if (body) {
        const host = String(body.host || "").trim().replace(/\/$/, "");
        if (host && !/^https?:\/\/[^\s/]+(:\d+)?$/.test(host)) throw new TutorError("Adresse bitte als http://IP:11434 angeben.");
        S.cfg = { ...S.cfg, host, model: String(body.model || S.cfg.model).trim(),
          vision_model: String(body.vision_model || S.cfg.vision_model).trim() };
        persist();
      }
      return { host: S.cfg.host, model: S.cfg.model, vision_model: S.cfg.vision_model };
    }
    if (path === "/api/planner") return plannerState();
    if (path === "/api/focus") return focusInfo();
    if (path === "/api/shot") return { version: 0 };
    if (path === "/api/plan.ics") return { ics: C.ics(S.tasks, S.reminders, nowIso()) };
    if (path === "/api/model") { await checkModel(String(body.name || "").trim()); S.cfg.model = body.name.trim(); persist(); return { state: state() }; }
    if (path === "/api/subject") { S.cfg.subject = String(body.subject || "").trim().slice(0, 60); persist(); return { state: state() }; }
    if (path === "/api/page") return pageRoute(body);
    if (path === "/api/page_text") {
      const text = String(body.text || "").trim().slice(0, 2500);
      cur().pageNotes = text ? [text] : [];
      return { state: state() };
    }
    if (path === "/api/save") {
      const convs = S.conv.filter((t) => t.messages.length);
      if (!convs.length) return { saved: null };
      S.sessions.push({ started: S.started, saved: clock().iso, model: S.cfg.model, subject: S.cfg.subject, tasks: convs });
      persist(); return { saved: "in der App" };
    }
    if (path === "/api/tasks/extract") {
      const imgs = (body.images || [body.image || ""]).map(stripData).filter((x) => x.length >= 100).slice(0, 4);
      if (!imgs.length) throw new TutorError("Kein Bild empfangen.");
      const found = [], seen = new Set();
      for (const img of imgs) {
        const raw = await vision(C.extractPrompt(clock().iso.slice(0, 10)), img);
        for (const t of C.parseTasksJson(raw)) {
          const k = t.title.toLowerCase() + "|" + t.due;
          if (!seen.has(k)) { seen.add(k); found.push(t); }
        }
      }
      return { candidates: found };
    }
    if (/^\/api\/(tasks|reminders|blocklist|focus)/.test(path)) return plannerRoute(path, body || {});
    throw new TutorError("Unbekannt: " + path);
  }

  async function stream(path, body, onPiece) {
    await load();
    if (path === "/api/chat") {
      const text = String(body.text || "").trim();
      if (!text) throw new TutorError("Leere Nachricht");
      S.confirm = false;
      return streamTurn(text, onPiece);
    }
    if (path === "/api/giveup") {
      const [status, msg] = requestGiveUp();
      if (status !== "ok") return { notice: msg, state: state() };
      return streamTurn(C.GIVE_UP_TEXT, onPiece);
    }
    if (path === "/api/new") {
      const text = String(body.text || "").trim();
      S.confirm = false;
      if (cur().messages.length) S.conv.push(newTask());
      else Object.assign(cur(), { title: "", givenUp: false, pageNotes: [] });
      if (text) return streamTurn(text, onPiece);
      return { state: state() };
    }
    throw new TutorError("Unbekannt: " + path);
  }

  return { api, stream, TutorError };
}

const api = { createBackend, TutorError, DEFAULT_CONFIG };
if (typeof module !== "undefined" && module.exports) module.exports = api;
root.TutorBackendLocal = api;
})(typeof self !== "undefined" ? self : globalThis);
