/* Brücke zwischen Oberfläche und Hauptprozess. Nur das Nötigste, jede Funktion wird im
   Hauptprozess erneut geprüft (contextIsolation an, kein Node in der Oberfläche). */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("TutorDesktop", {
  isDesktop: true,
  platform: process.platform,
  onFocusCommand: (cb) => ipcRenderer.on("focus:command", (_e, cmd) => cb(cmd)),
  listWindows: () => ipcRenderer.invoke("windows:list"),
  chooseWindow: (id) => ipcRenderer.invoke("windows:choose", id),
  overlayInteractive: (on) => ipcRenderer.send("overlay:interactive", !!on),
  overlayFocus: () => ipcRenderer.send("overlay:focus"),
  overlayCapture: () => ipcRenderer.invoke("overlay:capture"),
  overlayHide: () => ipcRenderer.send("overlay:hide"),
  overlayToggle: () => ipcRenderer.invoke("overlay:toggle"),
  phoneStart: () => ipcRenderer.invoke("phone:start"),
  phoneStop: () => ipcRenderer.invoke("phone:stop"),
  phoneStatus: () => ipcRenderer.invoke("phone:status"),
  getSettings: () => ipcRenderer.invoke("settings:get"),
  setSettings: (partial) => ipcRenderer.invoke("settings:set", partial),
});
