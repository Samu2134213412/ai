/* Tutor – PC-App (Electron). Sie ist gleichzeitig der Tutor-Server dieses PCs:
   - der Server (../server) rechnet mit dem lokalen Ollama und speichert Verlauf/Aufgaben,
   - das Fenster (und die Handy-Oberfläche) sind nur Clients davon,
   - die Browser-Erweiterung „Tutor Fokus“ spricht ebenfalls mit ihm (Port 8765). */
const { app, BrowserWindow, Tray, Menu, ipcMain, session, desktopCapturer, nativeImage, shell, Notification, screen, globalShortcut } = require("electron");
const { execFile } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const QRCode = require("qrcode");

const { createTutorServer } = require("./server/server.js");
const { createGuard, parseProcessList } = require("./lib/guard.js");
const { createWatcher, createAuto } = require("./lib/watch.js");
const { createConfig } = require("./lib/config.js");

const WANT_PORT = Number(process.env.TUTOR_PORT) || 8765;
const LAN_PORT = Number(process.env.TUTOR_PHONE_PORT) || 8766;
let overlay = null;
let win = null, tray = null, quitting = false, origin = "", srv = null, config = null, chosenSource = null;
const run = (cmd, args) => new Promise((resolve, reject) =>
  execFile(cmd, args, { windowsHide: true, timeout: 5000, maxBuffer: 8 * 1024 * 1024 }, (e, out) => (e ? reject(e) : resolve(out))));
const guard = createGuard({ selfNames: ["tutor", "electron", "node", path.basename(process.execPath)], exec: run });

app.setAppUserModelId("de.tutor.desktop");
if (!app.requestSingleInstanceLock()) app.quit();
app.on("second-instance", () => showWindow());

const icon = () => nativeImage.createFromPath(path.join(__dirname, "assets", "icon.png"));
function showWindow() { if (!win) return; if (win.isMinimized()) win.restore(); win.show(); win.focus(); }
const toRenderer = (cmd) => { if (win && !win.isDestroyed()) win.webContents.send("focus:command", cmd); };
const fromOurPage = (e) => !!e.senderFrame && e.senderFrame.url.startsWith(origin + "/");
const owner = () => srv.backendFor(srv.ownerId);

function createWindow(hidden) {
  win = new BrowserWindow({
    width: 1180, height: 820, minWidth: 420, minHeight: 560, show: !hidden, icon: icon(),
    backgroundColor: "#fff7ec", title: "Tutor", autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false,
      sandbox: true, backgroundThrottling: false },     // Timer/Erinnerungen laufen auch im Tray weiter
  });
  win.setMenuBarVisibility(false);
  win.loadURL(`${origin}/index.html`);
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https:\/\//.test(url)) shell.openExternal(url); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(origin + "/")) { e.preventDefault(); if (/^https:\/\//.test(url)) shell.openExternal(url); } });
  win.on("close", (e) => { if (!quitting && config.get().trayOnClose && tray) { e.preventDefault(); win.hide(); } });
  win.on("closed", () => { win = null; });
}

/* GoodNotes-Leiste: durchsichtiges Fenster über dem ganzen Bildschirm, immer oben. Mausklicks gehen durch,
   außer über der Leiste (die Oberfläche meldet das per IPC). Wird bei Aufnahmen kurz ausgeblendet. */
function createOverlay() {
  const d = screen.getPrimaryDisplay();
  overlay = new BrowserWindow({
    x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height,
    transparent: true, frame: false, resizable: false, movable: false, hasShadow: false, skipTaskbar: true,
    alwaysOnTop: true, fullscreenable: false, focusable: true, show: false, title: "Tutor Leiste",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false,
      sandbox: true, backgroundThrottling: false },
  });
  overlay.setAlwaysOnTop(true, "screen-saver");
  overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  overlay.setIgnoreMouseEvents(true, { forward: true });
  try { overlay.setContentProtection(true); } catch (e) { /* nicht überall unterstützt */ }
  overlay.loadURL(`${origin}/overlay.html`);
  overlay.once("ready-to-show", () => overlay.showInactive());
  overlay.on("closed", () => { overlay = null; });
}
const e2e = (m) => { if (process.env.TUTOR_E2E) console.log(m); };
const overlayShow = () => { e2e("OVERLAY_SHOW"); if (!overlay) { createOverlay(); return true; } if (overlay.isVisible()) return false; overlay.showInactive(); return true; };
const overlayHide = () => { e2e("OVERLAY_HIDE"); if (overlay && overlay.isVisible()) overlay.hide(); };
function toggleOverlay() {
  if (!overlay) createOverlay();
  else if (overlay.isVisible()) overlay.hide();
  else overlay.showInactive();
  return !!overlay && overlay.isVisible();
}

function createTray() {
  try { tray = new Tray(icon().resize({ width: 24, height: 24 })); } catch (e) { tray = null; return; }
  tray.setToolTip("Tutor");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Tutor öffnen", click: showWindow },
    { label: "GoodNotes-Leiste ein/aus", click: toggleOverlay },
    { label: "Fokus 25 min starten", click: async () => { await owner().api("/api/focus/start", { minutes: 25 }); toRenderer({ type: "refresh" }); } },
    { label: "Fokus beenden", click: async () => { await owner().api("/api/focus/stop", {}); toRenderer({ type: "refresh" }); } },
    { type: "separator" },
    { label: "Beenden", click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on("click", showWindow);
}

function setupSession(token) {
  const ses = session.defaultSession;
  const allowed = new Set(["notifications", "media", "display-capture", "clipboard-sanitized-write"]);
  ses.setPermissionRequestHandler((wc, permission, cb, details) => cb(allowed.has(permission) && (details.requestingUrl || "").startsWith(origin)));
  ses.setPermissionCheckHandler((wc, permission, requestingOrigin) => allowed.has(permission) && (requestingOrigin || "").startsWith(origin));
  // Bildschirm-/Fensterfreigabe: nur die in der App gewählte Quelle, nie ungefragt.
  ses.setDisplayMediaRequestHandler((request, callback) => {
    const src = chosenSource; chosenSource = null;
    callback(src ? { video: src } : {});
  }, { useSystemPicker: false });
  // Dieses Fenster ist ein gekoppeltes Gerät des Besitzers: Token als Cookie setzen.
  return ses.cookies.set({ url: origin, name: "tutor_token", value: token, httpOnly: true, sameSite: "lax",
    expirationDate: Math.floor(Date.now() / 1000) + 365 * 24 * 3600 });
}

/* Geräte-Token dieses Fensters: einmal anlegen und in userData merken (sonst würde jeder Start ein Gerät mehr anlegen). */
function desktopToken(dataDir) {
  const file = path.join(dataDir, "desktop.token");
  try { const t = fs.readFileSync(file, "utf8").trim(); if (srv.users.find(t)) return t; } catch (e) { /* neu */ }
  const { token } = srv.redeem(srv.createPairing({ forOwner: true }));
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(file, token, { mode: 0o600 });
  return token;
}

function setupIpc() {
  ipcMain.handle("windows:list", async (e) => {
    if (!fromOurPage(e)) return [];
    const sources = await desktopCapturer.getSources({ types: ["window", "screen"], thumbnailSize: { width: 320, height: 200 },
      fetchWindowIcons: false });
    return sources.filter((s) => s.name && !/^tutor$/i.test(s.name))
      .map((s) => ({ id: s.id, name: s.name, screen: s.id.startsWith("screen:"), thumb: s.thumbnail.isEmpty() ? "" : s.thumbnail.toDataURL() }));
  });
  ipcMain.handle("windows:choose", async (e, id) => {
    if (!fromOurPage(e) || typeof id !== "string") return false;
    const sources = await desktopCapturer.getSources({ types: ["window", "screen"], thumbnailSize: { width: 0, height: 0 } });
    chosenSource = sources.find((s) => s.id === id) || null;
    return !!chosenSource;
  });
  // GoodNotes-Leiste
  ipcMain.on("overlay:interactive", (e, on) => {
    if (!fromOurPage(e) || !overlay) return;
    overlay.setIgnoreMouseEvents(!on, { forward: true });
    if (process.env.TUTOR_E2E) console.log("OVERLAY_INTERACTIVE " + !!on);
  });
  ipcMain.on("overlay:focus", (e) => { if (fromOurPage(e) && overlay) overlay.focus(); });
  ipcMain.on("overlay:hide", (e) => { if (fromOurPage(e) && overlay) overlay.hide(); });
  ipcMain.handle("overlay:toggle", (e) => (fromOurPage(e) ? toggleOverlay() : false));
  ipcMain.handle("overlay:capture", async (e) => {                      // Bildschirm unter der Leiste als JPEG
    if (!fromOurPage(e) || !overlay) return null;
    const d = screen.getDisplayMatching(overlay.getBounds());
    const wasVisible = overlay.isVisible();
    overlay.hide();
    await new Promise((r) => setTimeout(r, 150));                         // Fenster ist weg, bevor aufgenommen wird
    try {
      const size = { width: Math.round(d.size.width * d.scaleFactor), height: Math.round(d.size.height * d.scaleFactor) };
      const sources = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: size });
      const src = sources.find((s) => s.display_id === String(d.id)) || sources[0];
      if (!src || src.thumbnail.isEmpty()) return null;
      let img = src.thumbnail;
      if (img.getSize().width > 2600) img = img.resize({ width: 2600 });
      return { image: "data:image/jpeg;base64," + img.toJPEG(88).toString("base64"), width: img.getSize().width, height: img.getSize().height };
    } finally { if (wasVisible && overlay) overlay.showInactive(); }
  });
  // Weiteres Gerät koppeln: WLAN-Zugang einschalten, einmaligen Link + QR-Code erzeugen (nur auf Knopfdruck)
  ipcMain.handle("phone:start", async (e) => {
    if (!fromOurPage(e)) return null;
    const lan = await srv.enableLan(LAN_PORT);
    const code = srv.createPairing({ forOwner: true });
    const url = srv.pairingUrls(code).find((u) => !u.includes("127.0.0.1")) || srv.pairingUrls(code)[0];
    const qr = await QRCode.toDataURL(url, { margin: 1, width: 320, errorCorrectionLevel: "M" });
    return { url, qr, ip: lan.ips[0], port: lan.port, all: lan.ips };
  });
  ipcMain.handle("phone:stop", async (e) => { if (fromOurPage(e)) await srv.disableLan(); return true; });
  ipcMain.handle("phone:status", (e) => (fromOurPage(e) ? { running: srv.lanEnabled } : null));
  ipcMain.handle("settings:get", (e) => (fromOurPage(e) ? config.get() : null));
  ipcMain.handle("settings:set", (e, partial) => {
    if (!fromOurPage(e)) return null;
    const next = config.set(partial);
    if (partial && "autostart" in partial && app.isPackaged) app.setLoginItemSettings({ openAtLogin: next.autostart, args: ["--hidden"] });
    return next;
  });
}

/* Alle paar Sekunden: während einer Fokus-Sitzung die vom Lernenden gelisteten Programme beenden. */
function startGuardLoop() {
  setInterval(async () => {
    const apps = config.get().blockedApps;
    if (!apps.length) return;
    try {
      const f = await owner().api("/api/focus");
      if (!f.active) return;
      const killed = await guard.tick(apps);
      if (killed.length && Notification.isSupported()) new Notification({ title: "Fokus 🎯", body: `Beendet: ${killed.join(", ")}` }).show();
    } catch (e) { /* ps/tasklist nicht verfügbar */ }
  }, 4000).unref();
}

/* GoodNotes beobachten (Fenstertitel + Prozessnamen): Solange es offen ist, laufen auf Wunsch Fokus und Leiste –
   auch wenn nur GoodNotes geöffnet wurde und das Tutor-Fenster zu ist (die App läuft dann im Tray). */
function startWatching() {
  const notify = (title, body) => { if (Notification.isSupported()) new Notification({ title, body }).show(); };
  const focus = {
    info: () => owner().api("/api/focus"),
    start: async (m) => { await owner().api("/api/focus/start", { minutes: m }); toRenderer({ type: "refresh" }); },
    stop: async () => { await owner().api("/api/focus/stop", {}); toRenderer({ type: "refresh" }); },
  };
  const auto = createAuto({ getConfig: () => config.get(), focus, overlay: { show: overlayShow, hide: overlayHide }, notify });
  const getNames = async () => {
    const names = [];
    try { names.push(...(await desktopCapturer.getSources({ types: ["window"], thumbnailSize: { width: 0, height: 0 } })).map((s) => s.name)); } catch (e) { /* Berechtigung fehlt */ }
    try { names.push(...parseProcessList(process.platform, await (process.platform === "win32" ? run("tasklist", ["/FO", "CSV", "/NH"]) : run("ps", ["-A", "-o", "comm="])))); } catch (e) { /* ps nicht verfügbar */ }
    return names;
  };
  const watcher = createWatcher({ getNames, onOpen: () => auto.onOpen(), onClose: () => auto.onClose() });
  setInterval(async () => {
    const c = config.get();
    if (!c.autoFocus && !c.autoOverlay) return;
    try { await watcher.tick(); if (watcher.open) await auto.keepAlive(); } catch (e) { /* nächster Takt */ }
  }, Number(process.env.TUTOR_WATCH_MS) || 5000).unref();
}

app.whenReady().then(async () => {
  const dataDir = path.join(app.getPath("userData"), "server");
  config = createConfig(path.join(app.getPath("userData"), "settings.json"));
  srv = createTutorServer({ wwwDir: path.join(__dirname, "www"), dataDir, host: "127.0.0.1", port: WANT_PORT,
    ollama: process.env.TUTOR_OLLAMA || "http://127.0.0.1:11434" });
  let started;
  try { started = await srv.start(); } catch (e) { if (e.code !== "EADDRINUSE") throw e; started = await srv.start({ port: 0 }); }
  origin = `http://127.0.0.1:${started.port}`;
  await setupSession(desktopToken(dataDir));
  setupIpc();
  createWindow(process.argv.includes("--hidden")); createTray(); startGuardLoop(); startWatching();
  globalShortcut.register("CommandOrControl+Alt+T", toggleOverlay);        // Leiste schnell ein-/ausblenden
  if (config.get().overlay || process.env.TUTOR_OVERLAY) createOverlay();
  if (process.env.TUTOR_E2E) console.log("TUTOR_E2E_READY " + origin);
});

app.on("before-quit", () => { quitting = true; });
app.on("window-all-closed", () => { if (quitting || process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (win) showWindow(); });
app.on("will-quit", () => { globalShortcut.unregisterAll(); if (srv) srv.stop(); });
