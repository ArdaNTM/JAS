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

const hud = readFileSync(new URL("../src/HudOverlay.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/hud.css", import.meta.url), "utf8");
for (const fragment of ["screen.getAllDisplays()", "display-added", "display-removed",
  "display-metrics-changed", "hudWindows", "setIgnoreMouseEvents", "moveDraggedPanel",
  "aura-hud-set-regions", "aura-hud-publish-panel"]) {
  assert.ok(main.includes(fragment), "Multi-display HUD invariant missing: " + fragment);
}
for (const fragment of ["useContinuousAuraVoice", "hud-canvas", "model_estimate", "confirmed: true", "hud-region"]) {
  assert.ok(hud.includes(fragment), "Spatial HUD contract missing: " + fragment);
}
assert.ok(css.includes("100vw") && css.includes("100vh"), "Spatial canvas must use full viewport");
console.log("PASS: spatial panel and consented wake-word presentation invariants");

for (const fragment of ["hudGetScene", "hudPublishPanel", "hudUpdatePanel", "hudDragStart", "hudSetRegions"]) {
  assert.ok(preload.includes(fragment), "HUD IPC API missing " + fragment);
}
assert.ok(hud.includes("WIKIMEDIA COMMONS") && hud.includes("hud-media"), "Real licensed media surface missing");
assert.ok(hud.includes("trusted_session_token"), "Trusted ScreenRead token must be scoped to explicit capture calls");


// Execute the production spectrum helper using a deterministic analyser fixture.
// The real browser mic and playback are wired to the same helper.
const ts = await import("typescript");
const source = readFileSync(new URL("../src/voice/audioSpectrum.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { createSpectrumPublisher } = await import("data:text/javascript;base64," + Buffer.from(outputText).toString("base64"));
const events = [];
const previousWindow = globalThis.window;
try {
  globalThis.window = { dispatchEvent: event => events.push(event) };
  let level = 0;
  let reads = 0;
  const analyser = { frequencyBinCount: 128, getByteFrequencyData: bins => { reads++; bins.fill(level); } };
  const publish = createSpectrumPublisher(analyser, "microphone");
  publish(100);
  assert.equal(events[0].detail.source, "microphone");
  assert.equal(events[0].detail.bands.length, 64);
  assert.ok(events[0].detail.bands.every(value => value === 0));
  level = 255;
  publish(110);
  assert.equal(reads, 1, "Spectrum publication must be rate limited");
  publish(140);
  assert.ok(events[1].detail.bands.every(value => value === 1));
  level = 128;
  publish(180);
  assert.ok(events[2].detail.bands.every(value => Math.abs(value - 128 / 255) < 1e-8));
  createSpectrumPublisher(analyser, "playback")(200);
  assert.equal(events[3].detail.source, "playback");
} finally { globalThis.window = previousWindow; }
const cockpit = readFileSync(new URL("../src/components/AstralCore.tsx", import.meta.url), "utf8");
const singleMic = readFileSync(new URL("../src/voice/useAuraVoice.ts", import.meta.url), "utf8");
assert.ok(cockpit.includes("aura:audio-spectrum") && cockpit.includes("prefers-reduced-motion"));
assert.ok(singleMic.includes("getFloatTimeDomainData") && !singleMic.includes("Math.sin(phase)"));
console.log("PASS: real spectrum measurement, source isolation, silence and throttling");
