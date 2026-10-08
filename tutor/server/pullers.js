/* Mitrechnende Tablets/Handys im Klassen-Pool („Abholer“). Ein iPad kann keine Anfragen annehmen – es holt sie ab:
   Es fragt den Tutor-Server dauerhaft „hast du Arbeit für mich?“ (long poll), rechnet die Antwort mit einem kleinen
   Modell im Browser (wllama, WebAssembly/WebGPU) und schickt den Text stückweise zurück. Für den Rest des Pools sieht
   das aus wie ein weiteres Ollama mit diesem kleinen Modell. */
const crypto = require("node:crypto");

/* Nur kleine Modelle – größere passen nicht in den Speicher eines Tablets. */
const PULL_MODELS = ["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b"];
const POLL_MS = 25000, IDLE_MS = 60000, ALIVE_MS = 35000;

function createPullers({ clock = Date.now, onChange = () => {}, pollMs = POLL_MS, idleMs = IDLE_MS } = {}) {
  const workers = new Map();          // id -> { id, name, models, job, waiter, seen, done }
  const jobs = new Map();             // jobId -> job

  const alive = (w) => !!w.waiter || clock() - w.seen < ALIVE_MS;
  const list = () => [...workers.values()].filter(alive);
  const gone = () => { for (const [k, w] of workers) if (!alive(w) && !w.job) workers.delete(k); };

  function register(id, name, models) {
    const ms = (Array.isArray(models) ? models : String(models || "").split(",")).map((m) => String(m).trim()).filter((m) => PULL_MODELS.includes(m));
    let w = workers.get(id);
    const fresh = !w;
    if (!w) { w = { id, name: String(name || "Tablet").slice(0, 40), models: [], job: null, waiter: null, seen: 0, done: 0 }; workers.set(id, w); }
    w.models = ms; w.seen = clock();
    if (fresh) onChange();
    return w;
  }

  /* Abholen: sofort eine wartende Aufgabe, sonst bis pollMs warten (null = nichts zu tun). */
  function take(id, { name, models } = {}, signal) {
    gone();
    const w = register(id, name, models);
    if (!w.models.length) return Promise.resolve(null);
    if (w.job && !w.job.sent) { w.job.sent = true; return Promise.resolve(payload(w.job)); }
    if (w.waiter) w.waiter(null);                      // alte Verbindung des Geräts ablösen
    return new Promise((resolve) => {
      const done = (v) => { clearTimeout(t); if (w.waiter === done) w.waiter = null; w.seen = clock(); resolve(v); };
      const t = setTimeout(() => done(null), pollMs);
      w.waiter = done;
      if (signal) signal.addEventListener("abort", () => done(null), { once: true });
      onChange();
    });
  }
  const payload = (job) => ({ job: job.id, model: job.body.model, messages: job.body.messages.map((m) => ({ role: m.role, content: String(m.content || "") })),
    temperature: job.body.options && job.body.options.temperature, max_tokens: (job.body.options && job.body.options.num_predict) || 512 });

  function free(model) { return list().find((w) => !w.job && w.waiter && w.models.includes(model)) || null; }
  const models = () => [...new Set(list().flatMap((w) => w.models))];
  const busy = () => list().filter((w) => w.job).length;

  /* Eine Anfrage auf einem Tablet ausführen und als Ollama-Antwort (NDJSON oder JSON) in `res` schreiben. */
  function run(w, body, res, signal) {
    return new Promise((resolve) => {
      const id = crypto.randomBytes(8).toString("hex");
      const stream = body.stream !== false;
      const job = { id, workerId: w.id, body, res, stream, text: "", sent: false, cancelled: false, timer: null, finish: null };
      const line = (content, done) => JSON.stringify({ model: body.model, created_at: new Date(clock()).toISOString(), message: { role: "assistant", content }, done }) + "\n";
      const finish = (err) => {
        if (job.finish === null) return;
        job.finish = null; clearTimeout(job.timer); jobs.delete(id);
        if (w.job === job) { w.job = null; if (!err) w.done++; }
        if (!res.writableEnded) {
          if (err && !res.headersSent) { res.writeHead(502, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: err })); }
          else if (err) res.end(JSON.stringify({ error: err }) + "\n");
          else if (stream) res.end(line("", true));
          else { res.writeHead(200, { "Content-Type": "application/json" }); res.end(line(job.text, true)); }
        }
        onChange();
        resolve(!err);
      };
      job.finish = finish;
      const arm = () => { clearTimeout(job.timer); job.timer = setTimeout(() => finish("Das Tablet antwortet nicht mehr."), idleMs); };
      job.chunk = (content) => {
        if (!content) return;
        job.text += content;
        if (stream) { if (!res.headersSent) res.writeHead(200, { "Content-Type": "application/x-ndjson" }); res.write(line(content, false)); }
        arm();
      };
      if (signal) signal.addEventListener("abort", () => { job.cancelled = true; finish("abgebrochen"); }, { once: true });
      jobs.set(id, job); w.job = job; arm();
      if (w.waiter) { job.sent = true; w.waiter(payload(job)); }
      onChange();
    });
  }

  /* Stück Text vom Tablet. Antwort { ok, cancel } – cancel: Anfrage wurde abgebrochen, aufhören. */
  function push(id, jobId, { content, done, error } = {}) {
    const job = jobs.get(String(jobId || ""));
    if (!job || job.workerId !== id) return { ok: false, cancel: true };
    const w = workers.get(id); if (w) w.seen = clock();
    if (job.cancelled) return { ok: false, cancel: true };
    if (typeof content === "string") job.chunk(content.slice(0, 20000));
    if (error) job.finish(String(error).slice(0, 200));
    else if (done) job.finish();
    return { ok: true, cancel: false };
  }

  function info() { return list().map((w) => ({ id: w.id, name: w.name, models: w.models, busy: !!w.job, done: w.done })); }
  return { take, push, run, free, models, busy, count: () => list().length, info, register };
}
module.exports = { createPullers, PULL_MODELS };
