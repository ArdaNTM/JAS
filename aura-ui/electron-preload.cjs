const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("auraDesktop", {
  minimize: () => ipcRenderer.invoke("aura-window-minimize"),
  maximize: () => ipcRenderer.invoke("aura-window-maximize"),
  close: () => ipcRenderer.invoke("aura-window-close"),
});