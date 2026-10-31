const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("auraDesktop", {
  minimize: () => ipcRenderer.invoke("aura-window-minimize"),
  maximize: () => ipcRenderer.invoke("aura-window-maximize"),
  close: () => ipcRenderer.invoke("aura-window-close"),
  hudSetInteractive: (enabled) =>
    ipcRenderer.invoke("aura-hud-set-interactive", Boolean(enabled)),
  onHudInteractive: (listener) => {
    const handler = (_event, enabled) => listener(Boolean(enabled));
    ipcRenderer.on("aura-hud-interactive", handler);
    return () => ipcRenderer.removeListener("aura-hud-interactive", handler);
  },
});