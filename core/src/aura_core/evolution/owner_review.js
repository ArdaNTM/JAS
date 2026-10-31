"use strict";
// This UI is served by the separately provisioned trusted owner process;
// AURA Core and its HUD cannot assert approval by sending a browser flag.
const $ = (id) => document.getElementById(id);
const status = (message) => { $("status").textContent = message; };
const toBytes = (value) => {
  if (!/^[a-zA-Z0-9_-]+$/.test(value)) throw new Error("Invalid WebAuthn encoding");
  const raw = atob(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};
const fromBytes = (buffer) => {
  const bytes = new Uint8Array(buffer);
  let result = "";
  for (let i = 0; i < bytes.length; i += 8192) {
    result += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(result).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("Owner request rejected (" + response.status + ")");
  return response.json();
}
function item(parent, heading, value) {
  const row = document.createElement("div");
  const name = document.createElement("span");
  const data = document.createElement("code");
  name.textContent = heading;
  data.textContent = String(value);
  row.className = "field";
  row.append(name, data);
  parent.append(row);
}
async function decide(record, decision, button) {
  if (!window.PublicKeyCredential || !navigator.credentials?.get) {
    status("Browser WebAuthn platform authenticator unavailable.");
    return;
  }
  if (button.disabled) return;
  button.disabled = true;
  status("Checking owner presence…");
  try {
    const challenge = await api("/api/owner/challenge", { approval_id: record.approval_id });
    const assertion = await navigator.credentials.get({
      publicKey: {
        challenge: toBytes(challenge.challenge),
        rpId: challenge.rp_id,
        allowCredentials: [{ type: "public-key", id: toBytes(challenge.credential_id) }],
        timeout: challenge.timeout_ms,
        userVerification: "required",
      },
    });
    if (!assertion || assertion.type !== "public-key") throw new Error("No verified passkey assertion");
    const response = assertion.response;
    const result = await api("/api/owner/decision", {
      challenge_id: challenge.challenge_id,
      credential_id: fromBytes(assertion.rawId),
      client_data_json: fromBytes(response.clientDataJSON),
      authenticator_data: fromBytes(response.authenticatorData),
      signature: fromBytes(response.signature),
      decision,
    });
    status("Recorded " + result.status + " · no tool activated");
    await load();
  } catch (error) {
    status(error instanceof Error ? error.message : "Owner passkey verification failed");
  } finally {
    button.disabled = false;
  }
}
function render(records) {
  const root = $("approvals");
  root.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("p");
    empty.textContent = "No owner-governed pending activation/rollback decisions.";
    root.append(empty);
    return;
  }
  for (const record of records) {
    const card = document.createElement("article");
    const title = document.createElement("h2");
    title.textContent = "Governed Skill · " + record.operation_id.toUpperCase();
    card.append(title);
    item(card, "Capability", record.capability_id);
    item(card, "Requested operation", record.operation_id);
    item(card, "Scope", record.resource_scope);
    item(card, "Full reviewed binding digest", record.request_fingerprint);
    item(card, "Expires", record.expires_at);
    item(card, "Approval version", record.version);
    const actions = document.createElement("div");
    actions.className = "actions";
    for (const choice of ["denied", "approved"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = choice === "approved" ? "Verify owner + approve" : "Verify owner + deny";
      button.className = choice === "approved" ? "allow" : "deny";
      button.addEventListener("click", () => void decide(record, choice, button));
      actions.append(button);
    }
    card.append(actions);
    root.append(card);
  }
}
async function load() {
  try {
    const result = await api("/api/owner/pending");
    render(Array.isArray(result.items) ? result.items : []);
    status("Review only · " + (result.items?.length ?? 0) + " pending");
  } catch (error) {
    status(error instanceof Error ? error.message : "Owner control plane unavailable");
  }
}
$("refresh").addEventListener("click", () => void load());
void load();
