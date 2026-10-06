const {
  app,
  BrowserWindow,
  ipcMain,
  nativeImage,
  Tray,
  Menu,
} = require("electron");

const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const CORE = path.join(ROOT, "core");

let mainWindow = null;
let tray = null;
let backend = null;

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

function createTray() {
  tray = new Tray(
    nativeImage.createEmpty(),
  );

  tray.setToolTip(
    "AURA Autonomous Intelligence",
  );

  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: "Open AURA",
        click: () => {
          if (!mainWindow) {
            createWindow();
          }

          mainWindow.show();
          mainWindow.focus();
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

app.whenReady().then(() => {
  startBackend();
  createWindow();
  createTray();
});

app.on("before-quit", () => {
  stopBackend();
});

app.on("window-all-closed", (event) => {
  event.preventDefault();
});

app.on("activate", () => {
  if (!mainWindow) {
    createWindow();
  }

  mainWindow.show();
});