# Legacy WebSocket secret fail-closed security — feature #103 (partial)

The legacy `core/src/aura_core/security/auth.py::verify_ws_token` previously accepted an implicit hard-coded password when `AURA_WS_SECRET` was absent. This change removes that insecure default: the verifier now rejects missing, weak, whitespace-padded, malformed Unicode and invalid credentials, and compares explicit configured UTF-8 bytes with `hmac.compare_digest`.

## Boundaries
- The modern Core WebSocket authentication path already uses `WebSocketTicketManager` in `core/src/aura_core/security/ws_ticket.py` with short-lived single-use tickets and a local-only live event route. That path is unchanged; `verify_ws_token` is a compatibility primitive and does not supersede it.
- Security improvement intentionally breaks legacy clients relying on the default example password. An operator must supply a sufficiently strong explicit secret; no automatic generation or secret persistence is implemented.
- Never return/log raw credentials. No new principal claim, permission, Owner approval or MCP Gateway authority is introduced.

## Tests
`cd core && uv run pytest -q tests/test_legacy_ws_auth.py`
`cd core && uv run python scripts/verify_final_lock.py`

Expected regression coverage: absent config, old default, too-short, control characters, whitespace, wrong token, malformed Unicode, bounded length, valid explicit UTF-8 secret, modern one-time ticket unaffected.

## Outstanding full acceptance
This is **not** multi-user authenticated identity, hardware-bound credential storage, revocation, Owner enrollment, production migration or live Gateway identity verification. The legacy helper might not be invoked by production Core. Full feature #103 remains TESTING/PARTIAL_VERIFIED and must not be called COMPLETE until actual deployment and end-to-end authentication acceptance.
