# Home Assistant-compatible entity state read — feature #86 (partial)

**Stacked on Draft PR #128**, whose `GovernedHomeInventoryReader` provides a bounded read-only device inventory. This feature adds `aura_core.application.governed_ha_state.GovernedHomeAssistantStateReader`; it does not add Home Assistant networking, credentials, discovery, automation or physical actuation.

## Trust and authorization
- Trusted application composition binds an independently authenticated principal and the prior scoped `HomeInventory`. Only devices previously enumerated as available and in safe coarse categories may be queried; direct request ID injection or a different principal/operation is not accepted.
- For **each** state read, the existing MCP Gateway receives a separate authorization request: capability/operation `home.entity.state.read`, exact `home/entities/<device-id>/read-only` scope, risk MEDIUM and tool `get_entity_state`. ALLOW from PermissionEngine is mandatory. A discovery listing is never an authorization to read arbitrary entities or perform actions.
- State response must come from the same registered provider ID as the inventory, match the exact requested device, use a small fixed state allowlist and contain a timezone-aware sample timestamp. Returns immutable `UNTRUSTED_STATE_METADATA`, **not** verified sensor truth or physical execution evidence.
- Wrong policy, missing inventory entry, offline device, malformed state, untrusted/fake camera or lock metadata, provider disagreement or callback error fails closed without raw credentials and cannot trigger any light/switch/lock action.

## Tests
`cd core && uv run pytest -q tests/test_governed_ha_state.py tests/test_governed_home_inventory.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests instantiate real JAS ServiceRegistry, CapabilityRegistry, ProviderRegistry, PermissionEngine and MCPGateway with a networkless fake MCP provider. They check positive exact policy ALLOW, default DENY before provider dispatch, wrong scope, unavailable devices, invalid inventory and sensitive device kinds, malformed payload/time, mismatched provider identity and redacted exceptions.

## Missing actual feature acceptance
- No live Home Assistant instance, REST/WebSocket OAuth access, Matter/Zigbee/Bluetooth adapters, user devices, credential storage, device ownership attestation, polling or UI.
- No user-approved automations/physical control. All actions need a separate explicitly registered capability and Owner/Gateway policy, independent of this read-only state contract.
- This PR must stay stacked on #128 until the upstream is explicitly Owner-approved, with a **combined** release-manifest lock and CI before integration. Feature #86 stays TESTING/PARTIAL_VERIFIED after exact-head tests, not COMPLETED.
- No new external package/license.
