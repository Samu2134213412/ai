/* Lokales Backend für die iPad-App: dieselben Routen wie web.py, aber ohne Server.
   Spricht direkt mit Ollama (WLAN) und speichert Aufgaben/Einstellungen auf dem Gerät. */
(function (root) {
"use strict";
const C = root.TutorCore || (typeof require !== "undefined" ? require("./core.js") : null);

const DEFAULT_CONFIG = { host: "", model: "qwen2.5:32b", light_model: "qwen2.5:3b", vision_model: "qwen2.5vl:7b",
  temperature: 0.6, subject: "", language: "Deutsch", turnsPerStage: 2, minAttempts: 2 };

class TutorError extends Error {}
class Escalate extends Error {}        // das schnelle Modell übergibt an das große
class BadLanguage extends Error {}     // Antwort mit chinesischen/asiatischen Zeichen

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

  const S = { light_ok: true, last_tier: null, last_route: {}, cfg: { ...DEFAULT_CONFIG, host: env.defaultHost || "" }, tasks: [], reminders: { enabled: false, time: "16:00" },
    blocklist: [...C.DEFAULT_BLOCKLIST], focus: { ends_at: 0, minutes: 0 }, sessions: [],
    conv: [newTask()], confirm: false, started: clock().iso };
  let ready = null;

  function newTask() { return { title: "", attempts: 0, givenUp: false, messages: [], pageNotes: [] }; }
  const cur = () => S.conv[S.conv.length - 1];
  const persist = () => storage.set("tutor.data", { cfg: S.cfg, tasks: S.tasks, reminders: S.reminders,
    blocklist: S.blocklist, focus: S.focus, sessions: S.sessions.slice(-30) });
  const load = () => (ready = ready || storage.get("tutor.data").then((d) => {
    if (d) { S.cfg = { ...DEFAULT_CONFIG, host: env.defaultHost || "", ...d.cfg }; S.tasks = d.tasks || []; S.reminders = d.reminders || S.reminders;
      S.blocklist = d.blocklist || S.blocklist; S.focus = d.focus || S.focus; S.sessions = d.sessions || []; }
    if (env.lockHost) S.cfg.host = env.defaultHost || "";      // Server-Betrieb: der Server bestimmt, wo Ollama ist
  }));

  /* ---------- Ollama ---------- */

  const connHint = () => {
    const h = S.cfg.host;
    if (!h) return "Noch keine Ollama-Adresse eingestellt. Öffne ⚙︎ und trage z. B. http://192.168.0.10:11434 ein.";
    if (/\/ollama$/.test(h)) return `Ollama ist über den PC nicht erreichbar.\n→ Läuft die Tutor-App am PC noch, ist dort „Handy verbinden“ an, läuft Ollama, und seid ihr im selben WLAN? Sonst am PC den QR-Code neu scannen.`;
    if (/^https?:\/\/(localhost|127\.0\.0\.1)(:|$)/.test(h)) return `Ollama ist unter ${h} nicht erreichbar.\n→ Ollama starten (App öffnen oder \`ollama serve\`) und erneut versuchen.`;
    return `Ollama ist unter ${h} nicht erreichbar.\n→ Läuft Ollama auf dem anderen Rechner (OLLAMA_HOST=0.0.0.0, OLLAMA_ORIGINS=*) und sind beide im selben WLAN?`;
  };
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
  async function* chatStream(model, messages, temperature) {
    const r = await ollama("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: true, keep_alive: C.KEEP_ALIVE,
        options: { temperature: temperature === undefined ? S.cfg.temperature : temperature } }) });
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
      if (e instanceof TutorError || e instanceof Escalate || e instanceof BadLanguage) throw e;
      throw new TutorError(connHint());
    }
  }
  /* chatStream + Sprach-Wächter + Übergabe-Erkennung (Spiegel von main.guarded_stream). */
  async function* guardedStream(model, messages, temperature, holdForEscape) {
    let buf = "", released = !holdForEscape;
    for await (const piece of chatStream(model, messages, temperature)) {
      if (C.hasCjk(piece)) throw new BadLanguage();
      if (released) { yield piece; continue; }
      buf += piece;
      const head = buf.replace(/^\s+/, "");
      if (head.startsWith(C.ESCAPE)) throw new Escalate();
      if (!C.ESCAPE.startsWith(head)) { released = true; yield buf; }
    }
    if (!released && buf) yield buf;
  }
  async function chatOnce(model, messages, temperature) {
    const r = await ollama("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: false, keep_alive: C.KEEP_ALIVE, options: { temperature } }) });
    if (!r.ok) await failFromResponse(r, model);
    const d = await r.json();
    return ((d.message && d.message.content) || "").trim();
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
    return { model: S.cfg.model, light_model: S.cfg.light_model, vision_model: S.cfg.vision_model, subject: S.cfg.subject, stage,
      attempts: t.attempts, given_up: t.givenUp, title: t.title, has_page: t.pageNotes.length > 0 };
  }
  async function messages(extra) {
    const sys = C.buildPrompt(await getTemplate(), S.cfg.subject, S.cfg.language) +
      C.plannerBlock(C.openTasks(S.tasks), clock().iso.slice(0, 10)) + C.pageBlock(cur()) +
      C.statusBlock(cur(), S.cfg.turnsPerStage) + (extra || "");
    return [{ role: "system", content: sys }, ...cur().messages];
  }
  const fullName2 = (m) => (m.includes(":") ? m : m + ":latest");
  const lightModel = () => {
    const m = (S.cfg.light_model || "").trim();
    return m && S.light_ok && fullName2(m) !== fullName2(S.cfg.model) ? m : "";
  };
  /* Eine Runde mit automatischer Modellwahl (Spiegel von Session.stream_turn in main.py).
     onPiece(text) liefert Textstücke, onPiece(null) heißt „bisherige Anzeige verwerfen“.
     Bei Fehler wird die Runde zurückgenommen (zählt nicht als Versuch). */
  async function streamTurn(text, onPiece) {
    const t = cur();
    let [tier, reason] = C.classify(text, { attempts: t.attempts, given_up: t.givenUp,
      has_page: t.pageNotes.length > 0, has_image: false, last_tier: S.last_tier });
    if (!t.title) t.title = text.slice(0, 80);
    t.attempts += 1; t.messages.push({ role: "user", content: text });

    const light = lightModel();
    const queue = tier === "light" && light ? [[light, "light"]] : [];
    queue.push([S.cfg.model, "main"]);
    const strict = new Set(); let notice = "", parts = [], success = false;
    try {
      while (queue.length) {
        const [model, kind] = queue.shift();
        const extra = (kind === "light" ? C.LIGHT_BLOCK : "") + (strict.has(model) ? C.STRICT_LANG : "");
        const temp = strict.has(model) ? Math.min(S.cfg.temperature, 0.3) : S.cfg.temperature;
        try {
          for await (const piece of guardedStream(model, await messages(extra), temp, kind === "light")) { parts.push(piece); onPiece(piece); }
          success = true; S.last_tier = kind;
          S.last_route = { tier: kind, model, reason, notice };
          break;
        } catch (e) {
          if (e instanceof Escalate) reason = "übergeben: braucht das große Modell";
          else if (e instanceof BadLanguage) {
            if (parts.length) { parts = []; onPiece(null); }
            if (!strict.has(model)) { strict.add(model); queue.unshift([model, kind]); }
          } else if (e instanceof TutorError && kind === "light" && !parts.length) {
            S.light_ok = false;
            notice = `Schnelles Modell '${model}' nicht verfügbar – ich antworte mit dem großen. Mit \`ollama pull ${model}\` werden einfache Antworten viel schneller.`;
          } else throw e;
        }
      }
      if (!success) {
        parts = ["Entschuldige, da ist bei mir etwas schiefgelaufen. Magst du deine Frage noch einmal stellen?"];
        onPiece(parts[0]);
        S.last_route = { tier: "main", model: S.cfg.model, reason: "Sprachfehler", notice };
      }
    } catch (e) {
      t.messages.pop(); t.attempts -= 1;
      if (e instanceof TutorError) e.state = state();
      throw e;
    } finally {
      if (parts.length) t.messages.push({ role: "assistant", content: parts.join("") });
    }
    return { done: true, state: state(), route: S.last_route };
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

  /* Seite aufräumen (oder per Zuruf ändern). Rückgabe: Notiz-Format (siehe notes.js). */
  async function tidyRoute(body) {
    const source = String(body.text || "").trim() || cur().pageNotes.join("\n").trim();
    const current = String(body.markup || "").trim(), wish = String(body.instruction || "").trim().slice(0, 300);
    if (!source && !current) throw new TutorError("Ich habe noch keine Seite gelesen. Lass den Tutor die Seite zuerst lesen (🔍 / 👀).");
    const user = current && wish
      ? `Aktuelle aufgeräumte Seite:\n${current}\n\nÄnderungswunsch: ${wish}\n\nOriginal-Abschrift zur Kontrolle (nichts davon darf verloren gehen):\n${source}`
      : `Abschrift der Seite:\n${source}` + (wish ? `\n\nWunsch: ${wish}` : "");
    let out = "";
    for (const strict of [false, true]) {
      out = await chatOnce(S.cfg.model, [{ role: "system", content: C.TIDY_PROMPT + (strict ? C.STRICT_LANG : "") }, { role: "user", content: user }], strict ? 0.1 : 0.2);
      if (!C.hasCjk(out)) break;
    }
    out = C.stripCjk(out).replace(/^```[a-z]*\n?|```$/gim, "").trim();
    if (!/\S/.test(out)) throw new TutorError("Das Aufräumen hat nichts geliefert. Bitte nochmal versuchen.");
    return { markup: out };
  }

  async function api(path, body) {
    await load();
    if (path === "/api/tidy") return tidyRoute(body || {});
    if (path === "/api/state") {
      let models = [], problem = null;
      try { models = (await installedModels()).sort(); } catch (e) { problem = e.message; }
      return { ...state(), models, problem, local: true };
    }
    if (path === "/api/settings") {
      if (body) {
        const host = env.lockHost ? S.cfg.host : String(body.host || "").trim().replace(/\/$/, "");
        if (host && !/^https?:\/\/[^\s/]+(:\d+)?$/.test(host)) throw new TutorError("Adresse bitte als http://IP:11434 angeben.");
        S.cfg = { ...S.cfg, host, model: String(body.model || S.cfg.model).trim(),
          light_model: "light_model" in body ? String(body.light_model).trim() : S.cfg.light_model,
          vision_model: String(body.vision_model || S.cfg.vision_model).trim() };
        persist();
      }
      return { host: S.cfg.host, model: S.cfg.model, light_model: S.cfg.light_model, vision_model: S.cfg.vision_model };
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
