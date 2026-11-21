import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const panel = readFileSync(new URL("../src/components/EvolutionReviewPanel.tsx", import.meta.url), "utf8");
const transcript = readFileSync(new URL("../src/components/ChatTranscript.tsx", import.meta.url), "utf8");

test("assistant stream completion restores ready status", () => {
  assert.match(app, /if \(status === "ready"\) \{/);
  assert.match(app, /setTaskState\("HAZIR"\)/);
  assert.match(app, /setSystemState\("idle"\)/);
});

test("discovery remains review-only and lists source evidence", () => {
  assert.match(app, /runSelfDiscovery\(\)/);
  assert.match(app, /execution_performed/);
  assert.match(panel, /getDiscoveryProposals/);
  assert.match(panel, /discoveryCount/);
  assert.match(transcript, /noopener noreferrer/);
  assert.doesNotMatch(transcript, /\/api\/owner\/decision/);
  assert.doesNotMatch(app, /navigator\.credentials/);
});
