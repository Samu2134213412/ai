/* Brücke zwischen Oberfläche und Hauptprozess. Nur das Nötigste, jede Funktion wird im
   Hauptprozess erneut geprüft (contextIsolation an, kein Node in der Oberfläche). */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("TutorDesktop", {
  isDesktop: true,
  platform: process.platform,
  pushFocus: (state) => ipcRenderer.send("focus:push", state),
  onFocusCommand: (cb) => ipcRenderer.on("focus:command", (_e, cmd) => cb(cmd)),
  listWindows: () => ipcRenderer.invoke("windows:list"),
  chooseWindow: (id) => ipcRenderer.invoke("windows:choose", id),
  getSettings: () => ipcRenderer.invoke("settings:get"),
  setSettings: (partial) => ipcRenderer.invoke("settings:set", partial),
});
