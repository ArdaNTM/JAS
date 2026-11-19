# Provider-agnostic read-only smart home inventory — feature #85 (partial)

`core/src/aura_core/application/governed_home_inventory.py` is a principal-bound, **read-only** facade on existing `MCPGateway`, `CapabilityRegistry`, `ProviderRegistry` and `PermissionEngine`. It never performs network scanning, LAN/SSDP/mDNS discovery, home automation, physical device control or direct Home Assistant/API calls. Its only data source is an already-registered MCP provider and separately granted `home.device.discover` policy.

## Trust contract
- Trusted composition constructs `GovernedHomeInventoryReader(gateway, authenticated_principal_id=...)` after independently authenticating the owner. A caller cannot override principal or scope on discovery.
- `discover()` calls the existing MCP Gateway with exact capability/operation `home.device.discover`, risk MEDIUM, scope `home/devices/read-only`, tool `list_devices` and no arguments. Without explicit ALLOW, provider dispatch never happens.
- A successful result is strictly structured and bounded (maximum 64 device IDs). Exposes only ephemeral bounded ID, coarse allowlisted category (`light/switch/sensor/climate/other`) and availability. Rejects duplicate/invalid IDs and sensitive `lock`/`camera` categories pending separate high-risk/privacy authorization.
- Output is immutable `UNTRUSTED_DEVICE_METADATA`, never proof of a trusted device, authenticated sensor measurement, real topology, or action grant. No raw network addresses, GPS/location, secret Home Assistant tokens, endpoints, camera images or user content.

## Tests
`cd core && uv run pytest -q tests/test_governed_home_inventory.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use real Service/Capability/Provider registries, Core PermissionEngine and MCP Gateway with a fake networkless MCP provider. Covers positive explicit ALLOW, default-deny, wrong scope, rejected sensitive metadata and malformed input, absent mutation commands, invalid principal and no secret leakage from provider exceptions.

## Acceptance limitations
- **Not** real Home Assistant, Matter, Zigbee, HomeKit, physical device discovery, control or automation. A separate registered local Home MCP adapter, credential/bootstrap and network security, owner household authorization and live hardware tests are required.
- All physical actions (locks, climate changes, switches, robot motions) require separate Gateway/PermissionEngine/Owner authorization. Discovery is not an action grant.
- Feature #85 remains TESTING/PARTIAL_VERIFIED after exact-head CI; no device tests, HA integrations, user dashboard or COMPLETED claim.
- Standard library and existing Core only; no new dependency/license.
