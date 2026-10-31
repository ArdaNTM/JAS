const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("auraDesktop", {
  minimize: () => ipcRenderer.invoke("aura-window-minimize"),
  maximize: () => ipcRenderer.invoke("aura-window-maximize"),
  close: () => ipcRenderer.invoke("aura-window-close"),

  hudGetScene: () => ipcRenderer.invoke("aura-hud-get-scene"),
  hudPublishPanel: (panel) => ipcRenderer.invoke("aura-hud-publish-panel", panel),
  hudUpdatePanel: (id, media) => ipcRenderer.invoke("aura-hud-update-panel", id, media),
  hudDismissPanel: (id) => ipcRenderer.invoke("aura-hud-dismiss-panel", id),
  hudSetRegions: (regions) => ipcRenderer.invoke("aura-hud-set-regions", regions),
  hudDragStart: (id) => ipcRenderer.invoke("aura-hud-drag-start", id),
  hudDragEnd: () => ipcRenderer.invoke("aura-hud-drag-end"),
  onHudScene: (listener) => {
    const handler = (_event, data) => listener(data);
    ipcRenderer.on("aura-hud-scene", handler);
    return () => ipcRenderer.removeListener("aura-hud-scene", handler);
  },
  hudSetInteractive: (enabled) =>
    ipcRenderer.invoke("aura-hud-set-interactive", Boolean(enabled)),
  onHudInteractive: (listener) => {
    const handler = (_event, enabled) => listener(Boolean(enabled));
    ipcRenderer.on("aura-hud-interactive", handler);
    return () => ipcRenderer.removeListener("aura-hud-interactive", handler);
  },
});