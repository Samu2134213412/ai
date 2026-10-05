/* Gibt JSON mit Ergebnissen des JS-Kerns aus; tests/test_parity.py vergleicht mit Python. */
const C = require("../web/core.js");
const tasks = [
  { id: "a1", title: "Mathe; Blatt, 4", subject: "Mathe", due: "2026-10-07", minutes: 100, done: false, created: "2026-10-01T10:00:00" },
  { id: "b2", title: "Vokabeln", subject: "", due: "", minutes: 30, done: false, created: "2026-10-02T10:00:00" },
  { id: "c3", title: "Zu viel", subject: "Bio", due: "2026-10-05", minutes: 300, done: false, created: "2026-10-03T10:00:00" },
  { id: "d4", title: "Fertig", subject: "", due: "2026-10-06", minutes: 20, done: true, created: "2026-10-03T11:00:00" },
];
const out = {
  stage: [0, 1, 2, 3, 4, 5, 6, 9].map((a) => C.stageOf({ attempts: a, givenUp: false }, 2)),
  stageGivenUp: C.stageOf({ attempts: 1, givenUp: true }, 2),
  stageText: C.STAGE_TEXT,
  status: C.statusBlock({ attempts: 3, givenUp: false }, 2),
  statusUp: C.statusBlock({ attempts: 3, givenUp: true }, 2),
  page: C.pageBlock({ pageNotes: ["a", "b", "c", "d", "e"] }),
  prompt: C.buildPrompt("X{{fach}}Y{{sprache}}", "Physik", "Deutsch"),
  promptNoSubject: C.buildPrompt("X{{fach}}Y{{sprache}}", "", "Deutsch"),
  handwriting: C.HANDWRITING_PROMPT,
  extract: C.extractPrompt("2026-10-05"),
  planNoon: C.plan(tasks, "2026-10-05T15:00"),
  planLate: C.plan(tasks, "2026-10-05T23:30"),
  planShort: C.plan(tasks, "2026-10-05T15:00", { days: 2, dailyMinutes: 50, start: "08:00" }),
  plannerBlock: C.plannerBlock(C.openTasks(tasks), "2026-10-05"),
  parse: C.parseTasksJson('Hier: [{"title":"A","minutes":"20","due":"2026-10-09"},{"nix":1},{"title":" B ","due":"2026-02-30","minutes":9999},5] ok'),
  parseBad: [C.parseTasksJson("kein json"), C.parseTasksJson("[kaputt")],
  blocklist: C.setBlocklist(["https://www.Foo.com/x", "kaputt", "foo.com", "a.b"]),
  ics: C.ics(tasks, { enabled: true, time: "17:30" }, "2026-10-05T15:00"),
  icsNoRem: C.ics(tasks, { enabled: false, time: "17:30" }, "2026-10-05T23:30"),
};
process.stdout.write(JSON.stringify(out));
