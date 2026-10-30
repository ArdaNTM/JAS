import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { createServer as createViteServer } from "vite";

const token = "test-only-AURA-bearer-" + "Q".repeat(48);
let upstreamAuthorized = 0;
const backend = http.createServer((req, res) => {
  if (req.headers.authorization === `Bearer ${token}`) {
    upstreamAuthorized++;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  res.writeHead(401);
  res.end("not authorized");
});
backend.listen(0, "127.0.0.1");
await once(backend, "listening");
const corePort = backend.address().port;
const reserve = http.createServer((req, res) => res.end());
reserve.listen(0, "127.0.0.1");
await once(reserve, "listening");
const uiPort = reserve.address().port;
await new Promise((resolve, reject) => reserve.close(err => err ? reject(err) : resolve()));
Object.assign(process.env, {
  AURA_API_BEARER_TOKEN: token,
  AURA_CORE_PORT: String(corePort),
  AURA_UI_PORT: String(uiPort),
});
let vite;
try {
  vite = await createViteServer({ configFile: "./vite.config.ts" });
  await vite.listen();
  const base = `http://127.0.0.1:${uiPort}`;
  const good = await fetch(base + "/api/speech/transcribe", {
    method: "POST",
    headers: { origin: base, "content-type": "application/json" },
    body: JSON.stringify({ audio_base64: "ZGF0YQ==" }),
  });
  assert.equal(good.status, 200, "Proxy must authenticate same-origin calls");
  assert.equal((await good.json()).ok, true);
  const event = await fetch(base + "/api/events/stream", { headers: { origin: base } });
  assert.equal(event.status, 200, "SSE path must also carry Core auth");
  await event.body.cancel();
  const forbidden = await fetch(base + "/api/speech/transcribe", {
    method: "POST",
    headers: { origin: "http://evil.invalid", "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(forbidden.status, 403, "Reject cross-origin proxy use");
  // Undici fetch normalizes Host; exercise a raw HTTP request instead.
  const badHost = await new Promise((resolve, reject) => {
    const req = http.request({
      hostname: "127.0.0.1", port: uiPort, method: "GET",
      path: "/api/speech/transcribe", headers: { Host: "evil.invalid" },
    }, (res) => {
      res.resume();
      res.on("end", () => resolve(res.statusCode));
    });
    req.on("error", reject);
    req.end();
  });
  assert.equal(badHost, 403, "Reject DNS-rebinding host");
  assert.equal(upstreamAuthorized, 2, "Only the two approved requests reach Core");
  console.log("PASS: AURA authenticated loopback proxy");
} finally {
  if (vite) await vite.close();
  await new Promise((resolve) => backend.close(resolve));
}
