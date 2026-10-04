const { app, BrowserWindow } = require("electron");
const path = require("path");

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1120,
    minHeight: 720,
    title: "AURA Operations Console",
    autoHideMenuBar: true,
    backgroundColor: "#02070d",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (process.env.AURA_DESKTOP_MODE === "production") {
    mainWindow.loadFile(path.join(__dirname, "dist", "index.html"));
  } else {
    mainWindow.loadURL("http://127.0.0.1:5173");
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (!mainWindow) createWindow();
});