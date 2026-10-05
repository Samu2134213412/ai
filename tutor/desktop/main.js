/* Tutor – Desktop-App (Electron). Zeigt die Web-Oberfläche in einem eigenen Fenster,
   spricht direkt mit dem lokalen Ollama und bedient die Browser-Erweiterung „Tutor Fokus“. */
const { app, BrowserWindow, Tray, Menu, ipcMain, session, desktopCapturer, nativeImage, shell, Notification } = require("electron");
const { execFile } = require("node:child_process");
const path = require("node:path");

const { FocusState } = require("./lib/focus-state.js");
const { createStaticServer } = require("./lib/static-server.js");
const { createGuard } = require("./lib/guard.js");
const { createConfig } = require("./lib/config.js");

const WANT_PORT = Number(process.env.TUTOR_PORT) || 8765;
let win = null, tray = null, quitting = false, origin = "", server = null, config = null, chosenSource = null;
const focus = new FocusState();
const guard = createGuard({
  selfNames: ["tutor", "electron", "node", path.basename(process.execPath)],
  exec: (cmd, args) => new Promise((resolve, reject) =>
    execFile(cmd, args, { windowsHide: true, timeout: 5000, maxBuffer: 8 * 1024 * 1024 }, (e, out) => (e ? reject(e) : resolve(out)))),
});

app.setAppUserModelId("de.tutor.desktop");
if (!app.requestSingleInstanceLock()) app.quit();
app.on("second-instance", () => showWindow());

const icon = () => nativeImage.createFromPath(path.join(__dirname, "assets", "icon.png"));
function showWindow() { if (!win) return; if (win.isMinimized()) win.restore(); win.show(); win.focus(); }
const toRenderer = (cmd) => { if (win && !win.isDestroyed()) win.webContents.send("focus:command", cmd); };
const fromOurPage = (e) => !!e.senderFrame && e.senderFrame.url.startsWith(origin + "/");

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

function createTray() {
  try { tray = new Tray(icon().resize({ width: 24, height: 24 })); } catch (e) { tray = null; return; }
  tray.setToolTip("Tutor");
  const menu = () => Menu.buildFromTemplate([
    { label: "Tutor öffnen", click: showWindow },
    { label: "Fokus 25 min starten", click: () => { focus.start(25); toRenderer({ type: "start", minutes: 25 }); } },
    { label: "Fokus beenden", click: () => { focus.stop(); toRenderer({ type: "stop" }); } },
    { type: "separator" },
    { label: "Beenden", click: () => { quitting = true; app.quit(); } },
  ]);
  tray.setContextMenu(menu());
  tray.on("click", showWindow);
}

function setupSession() {
  const ses = session.defaultSession;
  const allowed = new Set(["notifications", "media", "display-capture", "clipboard-sanitized-write"]);
  ses.setPermissionRequestHandler((wc, permission, cb, details) => cb(allowed.has(permission) && (details.requestingUrl || "").startsWith(origin)));
  ses.setPermissionCheckHandler((wc, permission, requestingOrigin) => allowed.has(permission) && (requestingOrigin || "").startsWith(origin));
  // Bildschirm-/Fensterfreigabe: nur die in der App gewählte Quelle, nie ungefragt.
  ses.setDisplayMediaRequestHandler((request, callback) => {
    const src = chosenSource; chosenSource = null;
    callback(src ? { video: src } : {});
  }, { useSystemPicker: false });
}

function setupIpc() {
  ipcMain.on("focus:push", (e, state) => { if (fromOurPage(e)) focus.update(state); });
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
    const f = focus.info(), apps = config.get().blockedApps;
    if (!f.active || !apps.length) return;
    try {
      const killed = await guard.tick(apps);
      if (killed.length && Notification.isSupported()) new Notification({ title: "Fokus 🎯", body: `Beendet: ${killed.join(", ")}` }).show();
    } catch (e) { /* ps/tasklist nicht verfügbar */ }
  }, 4000).unref();
}

app.whenReady().then(async () => {
  config = createConfig(path.join(app.getPath("userData"), "settings.json"));
  server = createStaticServer({ wwwDir: path.join(__dirname, "www"), focus, port: WANT_PORT, onCommand: toRenderer });
  const port = await server.listen();
  origin = `http://127.0.0.1:${port}`;
  setupSession(); setupIpc();
  createWindow(process.argv.includes("--hidden")); createTray(); startGuardLoop();
  if (process.env.TUTOR_E2E) console.log("TUTOR_E2E_READY " + origin);
});

app.on("before-quit", () => { quitting = true; });
app.on("window-all-closed", () => { if (quitting || process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (win) showWindow(); });
app.on("will-quit", () => { if (server) server.close(); });
