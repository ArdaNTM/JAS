const {
  app,
  BrowserWindow,
  ipcMain,
  nativeImage,
  Tray,
  Menu,
  globalShortcut,
  screen,
} = require("electron");

const { spawn } = require("child_process");
const path = require("path");
const { randomUUID } = require("crypto");

const ROOT = path.resolve(__dirname, "..");
const CORE = path.join(ROOT, "core");

let mainWindow = null;
let tray = null;
let backend = null;
let hudWindow = null; // Primary overlay; retained for compatibility
const hudWindows = new Map();
let hudInteractive = false;
let hudPanels = [];
let hudRegions = [];
let hudDrag = null;
let hudDragTimer = null;
let hudSequence = 0;
const HUD_MODE = process.env.AURA_HUD_MODE === "1";

function startBackend() {
  if (backend && !backend.killed) {
    return;
  }

  backend = spawn(
    process.platform === "win32" ? "uv.exe" : "uv",
    ["run", "python", "-m", "aura_core"],
    {
      cwd: CORE,
      env: {
        ...process.env,
        AURA_RESEARCH_MCP_TRANSPORT:
          process.env.AURA_RESEARCH_MCP_TRANSPORT || "stdio",
        AURA_RESEARCH_MCP_COMMAND:
          process.env.AURA_RESEARCH_MCP_COMMAND || "python",
        AURA_RESEARCH_MCP_ARGS:
          process.env.AURA_RESEARCH_MCP_ARGS ||
          path.join(
            CORE,
            "scripts",
            "local_research_mcp.py",
          ),
      },
      windowsHide: true,
      stdio: "ignore",
    },
  );

  backend.on("exit", () => {
    backend = null;
  });
}

function stopBackend() {
  if (!backend || backend.killed) {
    return;
  }

  try {
    backend.kill();
  } catch {
    // Process may already have exited.
  }

  backend = null;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 940,
    minWidth: 1080,
    minHeight: 680,
    title: "AURA",
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    hasShadow: true,
    autoHideMenuBar: true,

    webPreferences: {
      preload: path.join(
        __dirname,
        "electron-preload.cjs",
      ),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (
    process.env.AURA_DESKTOP_MODE ===
    "production"
  ) {
    mainWindow.loadFile(
      path.join(
        __dirname,
        "dist",
        "index.html",
      ),
    );
  } else {
    mainWindow.loadURL(
      "http://127.0.0.1:5173",
    );
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// One transparent window per physical display. A single giant virtual desktop
// window is unreliable with negative coordinates and mixed DPI scale factors.
// Presentation state, not permissions or model outputs, is shared in main.
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const displays = () => screen.getAllDisplays().sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y);
const owner = (event) => [...hudWindows.entries()].find(([, w]) =>
  !w.isDestroyed() && w.webContents === event.sender)?.[0] ?? null;

function sceneFor(id) {
  const display = displays().find(d => d.id === id);
  return {
    displayId: id,
    primary: id === screen.getPrimaryDisplay().id,
    bounds: display?.bounds ?? null,
    interactive: hudInteractive,
    panels: hudPanels.filter(panel => panel.displayId === id),
    regions: id === screen.getPrimaryDisplay().id ? hudRegions : [],
  };
}
function broadcastScene() {
  for (const [id, win] of hudWindows) {
    if (!win.isDestroyed() && !win.webContents.isDestroyed()) {
      win.webContents.send("aura-hud-scene", sceneFor(id));
    }
  }
}
function createHudForDisplay(display) {
  const bounds = display.bounds;
  const win = new BrowserWindow({
    x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height,
    frame: false, transparent: true, backgroundColor: "#00000000",
    alwaysOnTop: true, skipTaskbar: true, hasShadow: false,
    resizable: false, show: false,
    webPreferences: {
      preload: path.join(__dirname, "electron-preload.cjs"),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      backgroundThrottling: false,
    },
  });
  win.setContentProtection(true);
  win.setIgnoreMouseEvents(true, { forward: true });
  win.setAlwaysOnTop(true, "floating");
  const url = "http://127.0.0.1:5173/?auraHud=1";
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, target) => {
    if (target !== url) event.preventDefault();
  });
  win.webContents.on("did-finish-load", () => win.webContents.send("aura-hud-scene", sceneFor(display.id)));
  win.loadURL(url);
  win.once("ready-to-show", () => win.showInactive());
  win.on("closed", () => {
    hudWindows.delete(display.id);
    if (hudWindow === win) hudWindow = null;
  });
  return win;
}
function syncHudWindows() {
  const current = displays();
  const ids = new Set(current.map(d => d.id));
  for (const [id, win] of hudWindows) {
    if (!ids.has(id)) {
      hudWindows.delete(id);
      if (!win.isDestroyed()) win.close();
    }
  }
  for (const d of current) {
    const win = hudWindows.get(d.id);
    if (!win || win.isDestroyed()) {
      hudWindows.set(d.id, createHudForDisplay(d));
    } else {
      const b = d.bounds, now = win.getBounds();
      if (now.x !== b.x || now.y !== b.y || now.width !== b.width || now.height !== b.height) {
        win.setBounds(b);
      }
    }
  }
  const primary = screen.getPrimaryDisplay();
  hudWindow = hudWindows.get(primary.id) ?? hudWindows.values().next().value ?? null;
  const available = new Set(hudWindows.keys());
  for (const p of hudPanels) if (!available.has(p.displayId)) p.displayId = primary.id;
  broadcastScene();
}
function createHudWindow() {
  syncHudWindows();
}

function setHudInteractive(enabled) {
  if (!hudWindows.size) return false;
  hudInteractive = Boolean(enabled);
  if (!hudInteractive) stopHudDrag();
  for (const win of hudWindows.values()) {
    if (!win.isDestroyed()) {
      win.setIgnoreMouseEvents(!hudInteractive, { forward: true });
      win.webContents.send("aura-hud-interactive", hudInteractive);
    }
  }
  if (hudInteractive) hudWindow?.focus();
  broadcastScene();
  return hudInteractive;
}
function toggleHudInteractive() {
  return setHudInteractive(!hudInteractive);
}
function addHudPanel(body) {
  if (!body || typeof body !== "object" || typeof body.title !== "string" ||
      body.title.trim().length < 1 || body.title.length > 100) return null;
  const current = displays();
  if (!current.length) return null;
  const placement = current[hudSequence % current.length];
  const slot = Math.floor(hudSequence / current.length) % 4;
  hudSequence++;
  const b = placement.bounds;
  const cardW = Math.min(340, Math.max(210, b.width * 0.27));
  const xSlots = [0.04, 0.60, 0.10, 0.56];
  const ySlots = [0.18, 0.15, 0.57, 0.59];
  const panel = {
    id: randomUUID(),
    displayId: placement.id,
    x: Math.round(b.x + clamp(b.width * xSlots[slot], 8, Math.max(8, b.width - cardW - 8))),
    y: Math.round(b.y + clamp(b.height * ySlots[slot], 8, Math.max(8, b.height - 210))),
    title: body.title.slice(0, 100),
    kind: typeof body.kind === "string" ? body.kind.slice(0, 40) : "object",
    copy: typeof body.copy === "string" ? body.copy.slice(0, 4000) : "",
    media: null,
  };
  hudPanels.push(panel);
  hudPanels = hudPanels.slice(-9);
  broadcastScene();
  return panel.id;
}
function stopHudDrag() {
  hudDrag = null;
  if (hudDragTimer !== null) clearInterval(hudDragTimer);
  hudDragTimer = null;
}
function moveDraggedPanel() {
  if (!hudDrag) return;
  const panel = hudPanels.find(p => p.id === hudDrag.id);
  if (!panel) return stopHudDrag();
  const cursor = screen.getCursorScreenPoint();
  const target = screen.getDisplayNearestPoint(cursor);
  const b = target.bounds;
  panel.displayId = target.id;
  panel.x = Math.round(clamp(cursor.x - hudDrag.offsetX, b.x + 4, b.x + Math.max(4, b.width - 220)));
  panel.y = Math.round(clamp(cursor.y - hudDrag.offsetY, b.y + 4, b.y + Math.max(4, b.height - 145)));
  broadcastScene();
}
function createTray() {
  tray = new Tray(
    nativeImage.createEmpty(),
  );

  tray.setToolTip(
    "AURA Autonomous Intelligence",
  );

  tray.setContextMenu(
    Menu.buildFromTemplate([
      ...(HUD_MODE ? [
        { label: "Show HUD", click: () => { createHudWindow(); for (const w of hudWindows.values()) w.showInactive(); } },
        { label: "Hide HUD", click: () => { for (const w of hudWindows.values()) w.hide(); } },
        { label: "Toggle HUD input (Ctrl+Alt+H)", click: toggleHudInteractive },
        { type: "separator" },
      ] : []),
      {
        label: "Open AURA",
        click: () => {
          if (HUD_MODE) {
            createHudWindow();
            for (const w of hudWindows.values()) w.showInactive();
          } else {
            if (!mainWindow) createWindow();
            mainWindow.show();
            mainWindow.focus();
          }
        },
      },
      {
        type: "separator",
      },
      {
        label: "Quit AURA",
        click: () => {
          app.quit();
        },
      },
    ]),
  );
}

ipcMain.handle(
  "aura-window-minimize",
  () => {
    mainWindow?.minimize();
  },
);

ipcMain.handle(
  "aura-window-maximize",
  () => {
    if (!mainWindow) {
      return;
    }

    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  },
);

ipcMain.handle(
  "aura-window-close",
  () => {
    mainWindow?.hide();
  },
);

ipcMain.handle("aura-hud-set-interactive", (event, enabled) => {
  if (!HUD_MODE || owner(event) === null) return false;
  return setHudInteractive(enabled);
});
ipcMain.handle("aura-hud-get-scene", event =>
  HUD_MODE && owner(event) !== null ? sceneFor(owner(event)) : null);
ipcMain.handle("aura-hud-publish-panel", (event, body) => {
  if (!HUD_MODE || owner(event) !== screen.getPrimaryDisplay().id) return null;
  return addHudPanel(body);
});
ipcMain.handle("aura-hud-update-panel", (event, id, media) => {
  if (!HUD_MODE || owner(event) === null || typeof id !== "string") return false;
  const panel = hudPanels.find(p => p.id === id);
  if (!panel || !media || typeof media !== "object") return false;
  try {
    const url = new URL(media.url);
    const page = new URL(media.page);
    if (url.protocol !== "https:" || url.hostname !== "upload.wikimedia.org" ||
        page.protocol !== "https:" || page.hostname !== "commons.wikimedia.org") return false;
    panel.media = { url: url.href, page: page.href,
      artist: String(media.artist || "").slice(0, 120),
      license: String(media.license || "").slice(0, 80) };
    broadcastScene();
    return true;
  } catch { return false; }
});
ipcMain.handle("aura-hud-dismiss-panel", (event, id) => {
  if (!HUD_MODE || owner(event) === null) return false;
  hudPanels = hudPanels.filter(p => p.id !== id);
  broadcastScene();
  return true;
});
ipcMain.handle("aura-hud-set-regions", (event, regions) => {
  if (!HUD_MODE || owner(event) === null || !Array.isArray(regions)) return false;
  hudRegions = regions.slice(0, 8).filter(r =>
    r && r.verified === false && r.source === "model_estimate" &&
    ["x","y","width","height"].every(k => typeof r[k] === "number" &&
      Number.isFinite(r[k]) && r[k] >= 0 && r[k] <= 1) &&
    r.x + r.width <= 1.001 && r.y + r.height <= 1.001
  ).map(r => ({...r, label: String(r.label || "").slice(0, 80)}));
  broadcastScene();
  return true;
});
ipcMain.handle("aura-hud-drag-start", (event, id) => {
  if (!HUD_MODE || !hudInteractive || owner(event) === null) return false;
  const panel = hudPanels.find(p => p.id === id);
  if (!panel) return false;
  stopHudDrag();
  const cursor = screen.getCursorScreenPoint();
  hudDrag = { id, offsetX: cursor.x - panel.x, offsetY: cursor.y - panel.y };
  hudDragTimer = setInterval(moveDraggedPanel, 32);
  return true;
});
ipcMain.handle("aura-hud-drag-end", event => {
  if (owner(event) === null) return false;
  stopHudDrag(); return true;
});

app.whenReady().then(() => {
  if (HUD_MODE) {
    createHudWindow();
    screen.on("display-added", syncHudWindows);
    screen.on("display-removed", syncHudWindows);
    screen.on("display-metrics-changed", syncHudWindows);
    globalShortcut.register("Control+Alt+H", toggleHudInteractive);
  } else {
    startBackend();
    createWindow();
  }
  createTray();
});

app.on("before-quit", () => {
  globalShortcut.unregisterAll();
  stopHudDrag();
  if (!HUD_MODE) stopBackend();
});

app.on("window-all-closed", (event) => {
  event.preventDefault();
});

app.on("activate", () => {
  if (HUD_MODE) {
    createHudWindow();
    hudWindow?.showInactive();
    return;
  }
  if (!mainWindow) createWindow();
  mainWindow.show();
});