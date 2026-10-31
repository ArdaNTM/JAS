import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

const source = readFileSync(new URL("../src/components/StageCControlPanel.tsx", import.meta.url), "utf8");

test("Stage C HUD is not an approval authority and retains a kill switch", () => {
  assert.match(source, /\/api\/stage-c\/kill-switch/);
  assert.match(source, /\/api\/stage-c\/runs/);
  assert.match(source, /Harici onay bekleniyor/);
  assert.match(source, /acil durdurma KALICI/);
  assert.doesNotMatch(source, /\/api\/approvals\/[^\s]+\/decision/);
  assert.doesNotMatch(source, /navigator\.credentials\.(get|create)/);
});
