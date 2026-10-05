const { remaining, fmt } = TutorFocus;
const $ = (id) => document.getElementById(id);
const DEF = "http://127.0.0.1:8765";
let conn = { serverUrl: DEF, token: "" };

async function post(path, body) {
  const r = await fetch(conn.serverUrl.replace(/\/$/, "") + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(conn.token ? { "X-Tutor-Token": conn.token } : {}) },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "HTTP " + r.status);
}

async function render() {
  const s = await chrome.storage.local.get(["serverUrl", "token", "focus", "parked"]);
  conn = { serverUrl: s.serverUrl || DEF, token: s.token || "" };
  $("url").value = conn.serverUrl; $("token").value = conn.token;
  const f = s.focus, left = remaining(f, Date.now());
  const a = $("actions"); a.replaceChildren();
  const btn = (txt, cls, fn) => { const b = document.createElement("button"); b.textContent = txt; if (cls) b.className = cls; b.onclick = fn; a.appendChild(b); };
  if (f && f.online === false && !left) {
    $("status").innerHTML = '<span class="err">Tutor-Server nicht erreichbar. Läuft <code>python web.py</code>?</span>';
  } else if (left > 0) {
    $("status").textContent = "🔒 Fokus läuft – noch " + fmt(left);
    btn("Beenden", "", async () => { await post("/api/focus/stop"); await chrome.runtime.sendMessage("refresh"); render(); });
  } else {
    $("status").textContent = "Kein Fokus aktiv.";
    for (const m of [25, 45]) btn(m + " min starten", m === 25 ? "go" : "", async () => {
      try { await post("/api/focus/start", { minutes: m }); await chrome.runtime.sendMessage("refresh"); render(); }
      catch (e) { $("status").innerHTML = '<span class="err">' + e.message + "</span>"; }
    });
  }
  const parked = s.parked || [], p = $("parked"); p.replaceChildren();
  if (parked.length && !left) {
    const h = document.createElement("div"); h.textContent = parked.length + " geparkte Tab(s):"; p.appendChild(h);
    for (const t of parked) { const d = document.createElement("div"); const l = document.createElement("a"); l.href = t.url; l.target = "_blank"; l.textContent = t.title.slice(0, 50); d.appendChild(l); p.appendChild(d); }
    const b = document.createElement("button"); b.textContent = "Alle öffnen"; b.onclick = async () => { for (const t of parked) await chrome.tabs.create({ url: t.url, active: false }); await chrome.storage.local.set({ parked: [] }); render(); }; p.appendChild(b);
    const c = document.createElement("button"); c.textContent = "Verwerfen"; c.onclick = async () => { await chrome.storage.local.set({ parked: [] }); render(); }; p.appendChild(c);
  }
}
$("saveConn").onclick = async () => { await chrome.storage.local.set({ serverUrl: $("url").value.trim() || DEF, token: $("token").value.trim() }); await chrome.runtime.sendMessage("refresh"); render(); };
chrome.runtime.sendMessage("refresh").finally(render);
setInterval(render, 1000);
