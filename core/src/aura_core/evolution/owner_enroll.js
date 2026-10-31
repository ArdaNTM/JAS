"use strict";
const status = (value) => { document.getElementById("status").textContent = value; };
const decode = (value) => {
  if (typeof value !== "string" || !/^[a-zA-Z0-9_-]+$/.test(value)) throw new Error("Invalid base64url");
  const raw = atob(value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4));
  return Uint8Array.from(raw, char => char.charCodeAt(0));
};
const encode = (arrayBuffer) => {
  const view = new Uint8Array(arrayBuffer);
  let text = "";
  for (let i = 0; i < view.length; i += 8192) text += String.fromCharCode(...view.subarray(i,i+8192));
  return btoa(text).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
};
async function request(path, bootstrap, body) {
  const response = await fetch(path, {
    method: "POST", cache: "no-store", credentials: "omit",
    headers: { "Content-Type":"application/json", "X-Aura-Bootstrap":bootstrap },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("Registration request denied (" + response.status + ")");
  return response.json();
}
document.getElementById("enroll").addEventListener("click", async () => {
  const input = document.getElementById("secret");
  const token = input.value.trim();
  if (!/^[a-f0-9]{64}$/.test(token)) { status("Valid 64-character bootstrap token required."); return; }
  input.value = "";
  const button = document.getElementById("enroll");
  button.disabled = true;
  try {
    if (!navigator.credentials?.create) throw new Error("WebAuthn unavailable in this browser");
    const options = await request("/api/enrollment/begin",token,{});
    const pub = options.publicKey;
    pub.challenge = decode(pub.challenge);
    pub.user.id = decode(pub.user.id);
    if (Array.isArray(pub.excludeCredentials)) {
      pub.excludeCredentials = pub.excludeCredentials.map(v=>({...v,id:decode(v.id)}));
    }
    status("Waiting for Windows Hello / platform authenticator user verification…");
    const registration = await navigator.credentials.create({publicKey:pub});
    if (!registration || registration.type !== "public-key") throw new Error("Passkey was not created");
    const result = await request("/api/enrollment/complete",token,{
      response: {
        id: registration.id,
        rawId: encode(registration.rawId),
        type:"public-key",
        response: {
          clientDataJSON: encode(registration.response.clientDataJSON),
          attestationObject: encode(registration.response.attestationObject),
        },
        clientExtensionResults: registration.getClientExtensionResults(),
      },
    });
    status("Enrollment complete: " + result.status + ". Owner public credential stored; no tool activated.");
  } catch (error) {
    status(error instanceof Error ? error.message : "Enrollment verification failed");
  } finally {
    button.disabled = false;
  }
});
