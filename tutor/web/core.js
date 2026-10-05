/* Tutor-Kern in JS (Spiegel von main.py/planner.py) für die iPad-App ohne Server.
   Reine Funktionen, ohne DOM – läuft im Browser und in Node. Parität zu Python
   wird in tests/test_parity.py geprüft; bei Änderungen beide Seiten anpassen. */
(function (root) {
"use strict";

const GIVEN_UP = 4;
const STAGE_TEXT = {
  1: "Stufe 1 – Leitfrage. Stelle genau EINE Leitfrage. Keine Formeln, keinen " +
     "Code, keine Zwischenergebnisse der Aufgabe. Ist noch unklar, was der " +
     "Lernende versucht hat und wo es hängt, frage zuerst danach.",
  2: "Stufe 2 – Denkanstoß. Nenne das passende Konzept oder eine Analogie, " +
     "gern mit einem einfachen Beispiel mit ANDEREN Werten als in der Aufgabe. " +
     "Rechne oder programmiere die Aufgabe selbst nicht vor.",
  3: "Stufe 3 – Teilschritt. Du darfst genau EINEN Zwischenschritt vormachen. " +
     "Weitere Schritte und das Endergebnis muss der Lernende selbst finden.",
  4: "AUFGEGEBEN – der Lernende hat per /aufgeben aufgegeben. Zeige jetzt " +
     "die vollständige Lösung Schritt für Schritt, begründe jeden Schritt " +
     "kurz und schließe mit einer kurzen Verständnisfrage.",
};
const GIVE_UP_TEXT = "Ich gebe auf. Bitte zeig mir die vollständige Lösung und erkläre jeden Schritt.";

const HANDWRITING_PROMPT =
  "Das Bild ist ein Ausschnitt einer Notiz-/Arbeitsseite eines Lernenden (z. B. aus " +
  "GoodNotes), oft in unsauberer Handschrift. Schreibe ab, was darauf steht: " +
  "Aufgabenstellung, Rechenschritte, Formeln, Skizzen (kurz beschrieben). " +
  "Regeln: Nichts dazuerfinden, nichts korrigieren, nicht lösen. Ist ein Wort oder " +
  "Zeichen nicht sicher lesbar, schreibe deine beste Lesung und hänge [?] an, bei " +
  "zwei plausiblen Lesungen z. B. 3x[?8x]. Völlig Unleserliches: [unleserlich]. " +
  "Orangefarbene Randnotizen stammen vom Tutor und werden nicht abgeschrieben. " +
  "Antworte auf Deutsch, höchstens 200 Wörter.";

function extractPrompt(today) {
  return `Heute ist ${today}. Das Bild zeigt Notizen/Hausaufgaben eines Lernenden. ` +
    "Finde alle zu erledigenden Aufgaben (Hausaufgaben, Lernen für Tests, Abgaben). " +
    'Antworte NUR mit einem JSON-Array, Objekte mit "title" (kurz), "subject" ' +
    '(Fach oder ""), "due" (YYYY-MM-DD oder "", relative Angaben wie "bis Freitag" ' +
    'vom heutigen Datum aus umrechnen), "minutes" (grobe Schätzung, Ganzzahl). ' +
    "Nichts erfinden; gibt es keine Aufgaben: [].";
}

/* ---------------- Hinweisstufen ---------------- */

function stageOf(task, turnsPerStage) {
  if (task.givenUp) return GIVEN_UP;
  const per = Math.max(1, Math.trunc(turnsPerStage));
  return Math.min(1 + Math.floor(Math.max(task.attempts - 1, 0) / per), 3);
}

function statusBlock(task, turnsPerStage) {
  const stage = stageOf(task, turnsPerStage);
  return "\n\n# Status-Block (vom Programm gesetzt)\n" +
    `Nachricht Nr. ${task.attempts} des Lernenden zu dieser Aufgabe.\n` +
    `Erlaubte Hilfe: ${STAGE_TEXT[stage]}\n` +
    (stage === GIVEN_UP ? "" : "Gehe NICHT über diese Stufe hinaus und nenne kein Endergebnis.\n");
}

function pageBlock(task) {
  const notes = task.pageNotes || [];
  if (!notes.length) return "";
  return "\n\n# Seite des Lernenden (vom Programm per Bildanalyse gelesen)\n" +
    "Der Lernende hat dir seine Notizseite gezeigt. Das ist die Abschrift " +
    "(kann Lesefehler enthalten – frag bei Unklarem nach):\n" +
    notes.slice(-4).map((n) => `- ${n}`).join("\n") + "\n" +
    "Beziehe dich konkret auf Stellen der Seite. Für Lösungen gelten trotzdem " +
    "dieselben Stufenregeln.\n";
}

function buildPrompt(template, subject, language) {
  return template.split("{{fach}}").join(subject ? ` für ${subject}` : "")
                 .split("{{sprache}}").join(language);
}

/* ---------------- Planer ---------------- */

const DEFAULT_BLOCKLIST = ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "netflix.com",
  "twitch.tv", "x.com", "twitter.com", "facebook.com", "reddit.com", "snapchat.com"];
const MAX_BLOCK_MIN = 45, BREAK_MIN = 10;

const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
function parseDay(s) {                       // "YYYY-MM-DD" → UTC-Date (nur Kalenderrechnung)
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s));
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return isoDate(d) === m[0] ? d : null;
}
const addDays = (s, n) => { const d = parseDay(s); d.setUTCDate(d.getUTCDate() + n); return isoDate(d); };
const fmtMin = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;

function cleanTask(raw) {
  const title = String(raw.title == null ? "" : raw.title).trim().slice(0, 120);
  if (!title) return null;
  let minutes = parseInt(raw.minutes, 10);
  if (!Number.isFinite(minutes) || !raw.minutes) minutes = 30;
  minutes = Math.max(5, Math.min(480, minutes));
  const d = parseDay(raw.due || "");
  return { title, subject: String(raw.subject || "").trim().slice(0, 40),
           due: d ? isoDate(d) : "", minutes };
}

function parseTasksJson(text) {
  const m = /\[[\s\S]*\]/.exec(String(text));
  if (!m) return [];
  let data;
  try { data = JSON.parse(m[0]); } catch (e) { return []; }
  if (!Array.isArray(data)) return [];
  return data.filter((x) => x && typeof x === "object" && !Array.isArray(x))
             .map(cleanTask).filter(Boolean);
}

function openTasks(tasks) {
  const far = "9999-12-31";
  return tasks.filter((t) => !t.done).slice().sort((a, b) => {
    const ka = [a.due || far, a.created], kb = [b.due || far, b.created];
    return ka[0] < kb[0] ? -1 : ka[0] > kb[0] ? 1 : ka[1] < kb[1] ? -1 : ka[1] > kb[1] ? 1 : 0;
  });
}

/* now = "YYYY-MM-DDTHH:MM" (lokale Zeit). Früheste Frist zuerst, Einheiten ≤ 45 min. */
function plan(tasks, now, opts) {
  const { days = 7, dailyMinutes = 90, start = "16:00" } = opts || {};
  const [sh, sm] = start.split(":").map(Number);
  const nowDay = now.slice(0, 10), nowMin = +now.slice(11, 13) * 60 + +now.slice(14, 16);
  const blocks = [], unplaced = [], used = {}, cursor = {};
  for (const t of openTasks(tasks)) {
    let left = t.minutes;
    const lastDay = t.due || null;
    for (let i = 0; i < days; i++) {
      const day = addDays(nowDay, i);
      if (lastDay && day > lastDay) break;
      let begin = sh * 60 + sm;
      if (i === 0) begin = Math.max(begin, nowMin + 5);
      let cur = cursor[day] !== undefined ? cursor[day] : begin;
      while (left > 0 && (used[day] || 0) < dailyMinutes && cur < 1440) {
        const chunk = Math.min(left, MAX_BLOCK_MIN, dailyMinutes - (used[day] || 0));
        if (chunk < 5) break;
        blocks.push({ date: day, start: fmtMin(cur), minutes: chunk, task_id: t.id,
                      title: t.title, subject: t.subject });
        used[day] = (used[day] || 0) + chunk;
        cur += chunk + BREAK_MIN; left -= chunk;
      }
      cursor[day] = cur;
      if (left <= 0) break;
    }
    if (left > 0) unplaced.push({ task_id: t.id, title: t.title, missing: left,
      reason: lastDay ? "bis zur Frist nicht genug Zeit" : "Plan zu kurz" });
  }
  blocks.sort((a, b) => (a.date + a.start < b.date + b.start ? -1 : a.date + a.start > b.date + b.start ? 1 : 0));
  return { blocks, unplaced };
}

function plannerBlock(tasks, today) {
  if (!tasks.length) return "";
  const rows = tasks.slice(0, 6).map((t) =>
    `- ${t.title}${t.subject ? " (" + t.subject + ")" : ""}${t.due ? ", fällig " + t.due : ""}`);
  return "\n\n# Offene Aufgaben des Lernenden (aus dem Planer)\n" +
    `Heute ist ${today}. Nur erwähnen, wenn der Lernende nach Planung ` +
    "fragt oder eine Frist nah ist; kurz, ohne Druck.\n" + rows.join("\n") + "\n";
}

function setBlocklist(items) {
  const list = Array.isArray(items) ? items : String(items).split(/\s+/);
  const out = [];
  for (const raw of list) {
    const host = String(raw).trim().toLowerCase().replace(/^(https?:\/\/)?(www\.)?/, "").split("/")[0];
    if (/^[a-z0-9.-]+\.[a-z]{2,}$/.test(host) && !out.includes(host)) out.push(host);
  }
  return out;
}

/* ---------------- Kalender (.ics) ---------------- */

function ics(tasks, reminders, now, opts) {
  const p = plan(tasks, now, opts);
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//tutor//DE", "CALSCALE:GREGORIAN"];
  const stamp = now.replace(/[-:]/g, "").slice(0, 13) + "00";
  const esc = (s) => s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
  const local = (day, min) => day.replace(/-/g, "") + "T" + pad(Math.floor(min / 60)) + pad(min % 60) + "00";
  const event = (uid, day, startMin, minutes, summary, alarmMin, extra) => {
    const endTotal = startMin + minutes;
    const endDay = endTotal >= 1440 ? addDays(day, 1) : day;
    lines.push("BEGIN:VEVENT", `UID:${uid}@tutor`, `DTSTAMP:${stamp}`,
      `DTSTART:${local(day, startMin)}`, `DTEND:${local(endDay, endTotal % 1440)}`,
      `SUMMARY:${esc(summary)}`, ...(extra || []),
      "BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${esc(summary)}`,
      `TRIGGER:-PT${alarmMin}M`, "END:VALARM", "END:VEVENT");
  };
  for (const b of p.blocks) {
    const label = `Lernen: ${b.title}` + (b.subject ? ` (${b.subject})` : "");
    event(`${b.task_id}-${b.date}-${b.start}`, b.date, +b.start.slice(0, 2) * 60 + +b.start.slice(3), b.minutes, label, 10);
  }
  if (reminders && reminders.enabled) {
    const [h, m] = reminders.time.split(":").map(Number);
    event("daily", now.slice(0, 10), h * 60 + m, 15, "Zeit zum Lernen 📚", 0, ["RRULE:FREQ=DAILY"]);
  }
  lines.push("END:VCALENDAR");
  const enc = new TextEncoder(), folded = [];
  for (let ln of lines) {
    while (enc.encode(ln).length > 74) {
      let cut = 74;
      while (enc.encode(ln.slice(0, cut)).length > 74) cut--;
      folded.push(ln.slice(0, cut)); ln = " " + ln.slice(cut);
    }
    folded.push(ln);
  }
  return folded.join("\r\n") + "\r\n";
}

/* ---------------- Native Benachrichtigungen planen ---------------- */

/* Liste für LocalNotifications.schedule(): Einheiten (10 min vorher), Fokus-Ende,
   tägliche Erinnerung. Zeiten als lokale Date-Komponenten (year..minute). */
function buildNotifications(data, now) {
  const out = []; let id = 100;
  const at = (day, min) => ({ year: +day.slice(0, 4), month: +day.slice(5, 7), day: +day.slice(8, 10),
                              hour: Math.floor(min / 60), minute: min % 60 });
  const nowKey = now.slice(0, 10) + now.slice(11, 16);
  for (const b of data.plan.blocks.slice(0, 40)) {
    const startMin = +b.start.slice(0, 2) * 60 + +b.start.slice(3);
    const fire = Math.max(0, startMin - 10);
    if (b.date + pad(Math.floor(fire / 60)) + ":" + pad(fire % 60) <= nowKey) continue;
    out.push({ id: id++, title: `Gleich: ${b.title}`, body: `${b.minutes} min ab ${b.start}.`, on: at(b.date, fire), repeats: false });
  }
  if (data.reminders && data.reminders.enabled) {
    const [h, m] = data.reminders.time.split(":").map(Number);
    out.push({ id: 1, title: "Zeit zum Lernen 📚", body: "Kurze Runde? Dein Plan wartet.", on: { hour: h, minute: m }, repeats: true });
  }
  return out;
}

const api = { GIVEN_UP, STAGE_TEXT, GIVE_UP_TEXT, HANDWRITING_PROMPT, extractPrompt, stageOf, statusBlock,
  pageBlock, buildPrompt, DEFAULT_BLOCKLIST, cleanTask, parseTasksJson, openTasks, plan, plannerBlock,
  setBlocklist, ics, buildNotifications, addDays, isoDate };
if (typeof module !== "undefined" && module.exports) module.exports = api;
root.TutorCore = api;
})(typeof self !== "undefined" ? self : globalThis);
