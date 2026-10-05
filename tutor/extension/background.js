/* Service Worker: holt den Fokus-Status vom Tutor-Server und räumt Ablenkungen auf. */
importScripts("lib.js");
const { isBlocked, remaining } = self.TutorFocus;

const DEFAULTS = { serverUrl: "http://127.0.0.1:8765", token: "" };
const store = {
  get: (keys) => chrome.storage.local.get(keys),
  set: (obj) => chrome.storage.local.set(obj),
};

async function refresh() {
  const { serverUrl, token } = { ...DEFAULTS, ...(await store.get(["serverUrl", "token"])) };
  const prev = (await store.get("focus")).focus || { active: false };
  let next;
  try {
    const r = await fetch(serverUrl.replace(/\/$/, "") + "/api/focus", {
      headers: token ? { "X-Tutor-Token": token } : {},
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const f = await r.json();
    next = { active: f.active, remaining: f.remaining, blocklist: f.blocklist,
             fetchedAt: Date.now(), online: true };
  } catch (e) {
    // Server weg: laufende Sitzung lokal zu Ende führen, aber nie neu starten.
    next = { ...prev, online: false };
    if (remaining(prev, Date.now()) <= 0) next.active = false;
  }
  await store.set({ focus: next });
  if (next.active && !prev.active) await sweepOpenTabs(next);
  if (!next.active && prev.active) await sessionEnded();
  return next;
}

async function park(tab) {
  const { parked = [] } = await store.get("parked");
  parked.push({ url: tab.url, title: tab.title || tab.url });
  await store.set({ parked: parked.slice(-50) });
}

async function sweepOpenTabs(state) {
  for (const tab of await chrome.tabs.query({})) {
    if (tab.url && isBlocked(tab.url, state.blocklist)) {
      await park(tab);
      chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

async function sessionEnded() {
  const { parked = [] } = await store.get("parked");
  chrome.notifications.create({
    type: "basic", iconUrl: "icon.svg", title: "Fokus geschafft 🎉",
    message: parked.length ? parked.length + " Tab(s) warten im Popup auf dich." : "Gut gemacht!",
  });
}

async function guard(tabId, url) {
  const { focus } = await store.get("focus");
  if (!focus || remaining(focus, Date.now()) <= 0 || !url || !isBlocked(url, focus.blocklist)) return;
  await park({ url, title: url });
  const back = chrome.runtime.getURL("blocked.html") +
    "?left=" + remaining(focus, Date.now()) + "&from=" + new Date().getTime();
  chrome.tabs.update(tabId, { url: back }).catch(() => {});
}

chrome.tabs.onCreated.addListener((t) => guard(t.id, t.pendingUrl || t.url));
chrome.tabs.onUpdated.addListener((id, info) => { if (info.url) guard(id, info.url); });

chrome.alarms.create("poll", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "poll") refresh(); });
chrome.runtime.onStartup.addListener(refresh);
chrome.runtime.onInstalled.addListener(refresh);
chrome.runtime.onMessage.addListener((msg, _s, send) => {
  if (msg === "refresh") refresh().then(send);
  return msg === "refresh";
});
