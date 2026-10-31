// Windows CI source-level invariants; Electron native rendering is a local smoke test.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const main = readFileSync(new URL("../electron-main.cjs", import.meta.url), "utf8");
const preload = readFileSync(new URL("../electron-preload.cjs", import.meta.url), "utf8");
const start = readFileSync(new URL("../../scripts/start_aura.ps1", import.meta.url), "utf8");

for (const fragment of [
  "AURA_HUD_MODE", "transparent: true", "frame: false",
  "alwaysOnTop: true", "skipTaskbar: true", "setIgnoreMouseEvents(true",
  "setContentProtection(true)", 'globalShortcut.register("Control+Alt+H"',
  'nodeIntegration: false', 'contextIsolation: true', 'sandbox: true',
  "setWindowOpenHandler", 'if (HUD_MODE)', "hudWindow",
]) {
  assert.ok(main.includes(fragment), `HUD shell lost invariant: ${fragment}`);
}
assert.match(main,
  /app\.whenReady\(\)\.then\(\(\)\s*=>\s*\{\s*if\s*\(HUD_MODE\)\s*\{[\s\S]*?\}\s*else\s*\{\s*startBackend\(\);\s*createWindow\(\);\s*\}/,
  "HUD mode must not start another backend");
for (const fragment of ["contextBridge.exposeInMainWorld", "hudSetInteractive", "aura-hud-set-interactive"]) {
  assert.ok(preload.includes(fragment), `HUD preload lost invariant: ${fragment}`);
}
assert.match(start, /AURA_HUD_ENABLED/);
assert.match(start, /AURA_HUD_MODE/);
assert.match(start, /taskkill\.exe\s+\/F\s+\/T\s+\/PID/);
console.log("PASS: governed Electron HUD shell / click-through invariants");
