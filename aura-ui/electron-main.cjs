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

const ROOT = path.resolve(__dirname, "..");
const CORE = path.join(ROOT, "core");

let mainWindow = null;
let tray = null;
let backend = null;
let hudWindow = null;
let hudInteractive = false;
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

function createHudWindow() {
  if (hudWindow && !hudWindow.isDestroyed()) return;
  // One transparent compositor covering the primary work area; individual
  // holograms are positioned by the renderer, not separate privileged windows.
  const display = screen.getPrimaryDisplay().workArea;
  hudWindow = new BrowserWindow({
    width: display.width,
    height: display.height,
    x: display.x,
    y: display.y,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    resizable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "electron-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  hudWindow.setContentProtection(true);
  hudInteractive = false;
  hudWindow.setIgnoreMouseEvents(true, { forward: true });
  hudWindow.setAlwaysOnTop(true, "floating");
  const url = "http://127.0.0.1:5173/?auraHud=1";
  // Only the operator-owned loopback Vite origin is allowed in this window.
  hudWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  hudWindow.webContents.on("will-navigate", (event, target) => {
    if (target !== url) event.preventDefault();
  });
  hudWindow.loadURL(url);
  hudWindow.once("ready-to-show", () => hudWindow?.showInactive());
  hudWindow.on("closed", () => {
    hudWindow = null;
    hudInteractive = false;
  });
}

function setHudInteractive(enabled) {
  if (!hudWindow || hudWindow.isDestroyed()) return false;
  hudInteractive = Boolean(enabled);
  hudWindow.setIgnoreMouseEvents(!hudInteractive, { forward: true });
  hudWindow.webContents.send("aura-hud-interactive", hudInteractive);
  if (hudInteractive) hudWindow.focus();
  return hudInteractive;
}

function toggleHudInteractive() {
  return setHudInteractive(!hudInteractive);
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
        { label: "Show HUD", click: () => { createHudWindow(); hudWindow?.showInactive(); } },
        { label: "Hide HUD", click: () => hudWindow?.hide() },
        { label: "Toggle HUD input (Ctrl+Alt+H)", click: toggleHudInteractive },
        { type: "separator" },
      ] : []),
      {
        label: "Open AURA",
        click: () => {
          if (HUD_MODE) {
            createHudWindow();
            hudWindow?.showInactive();
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
  if (!HUD_MODE || !hudWindow || event.sender !== hudWindow.webContents) return false;
  return setHudInteractive(enabled);
});

app.whenReady().then(() => {
  if (HUD_MODE) {
    createHudWindow();
    globalShortcut.register("Control+Alt+H", toggleHudInteractive);
  } else {
    startBackend();
    createWindow();
  }
  createTray();
});

app.on("before-quit", () => {
  globalShortcut.unregisterAll();
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