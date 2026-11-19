# AURA B2 post-merge Windows / Hyper-V Ubuntu / Docker acceptance checklist

**Prerequisite:** Owner separately approves exactly PR #158 and PR #65 merges, completes their intended branch/merge sequence and checks out updated `main` at `D:\\AURA\\JAS`. Never merge or push to `main` automatically. The script performs **read-only** probes and scoped regression tests; it does not create Owner approval, modify ACLs, enable a privileged Docker broker, launch QEMU or sign hardware receipts. Avoid personal data in disposable lab tests.

## One command after merge (Windows PowerShell, from repo root)

```powershell
& ".\\core\\.venv\\Scripts\\python.exe" ".\\core\\scripts\\b2_postmerge_check.py" --repo-root "." --vm-name "AURA-Broker-Lab" --ubuntu-host "<UBUNTU_VM_IP>" --hardware-evidence "<EXTERNAL_SIGNED_EVIDENCE.json>" --trusted-public-keys "<PINNED_PUBLIC_KEYS.json>"
```

Replace **only** the three placeholders with actual values from the Owner's isolated lab. Both evidence inputs must be produced by a separately provisioned trusted signer; the runner cannot mint evidence. For a non-invasive inventory preview (no host probes or test execution): `& ".\\core\\.venv\\Scripts\\python.exe" ".\\core\\scripts\\b2_postmerge_check.py" --repo-root "." --list-only`.

The single command verifies the 117-feature ledger and canonical source pins, tracker schema, 440-file release lock, and runs available **deduplicated B2-focused regression files** with `pytest -q --tb=short`, but records unavailable tracker-listed files as **BLOCKED** instead of inventing passing results. At this PR #158 snapshot, 73 distinct B2-focused paths were indexed, of which **51 exist and 22 are absent**; restoring those 22 is a prerequisite for complete B2 regression acceptance. It then performs Windows platform presence, read-only Docker Engine inspection, read-only `Get-VM` running-state inspection, and TCP reachability of the configured Ubuntu VM. If external Ed25519-signed evidence and separate pinned public keys exist, the existing `verify_physical_hardware.py` gate validates them. Missing/busy host dependencies produce **INCONCLUSIVE/blocked**, not fabricated PASS.

## Exact subgroup meaning and remaining live acceptance

- **B2-Owner (17)**: `34, 46, 50, 58, 61, 64, 68, 70, 71, 72, 74, 75, 108, 109, 110, 114, 117`. Primary unresolved step is manual merge/review/Owner scope acceptance for bounded offline primitives; physical environment is not inferred solely from feature name. A green unit test is not Owner approval.
- **B2-Env (71)**: `1, 3, 4, 6, 7, 9, 11, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 45, 48, 49, 51, 54, 55, 56, 57, 60, 63, 69, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 103, 104, 105, 106, 107, 113, 115, 116`. Requires actual relevant host, provisioned model, external provider, Windows/Hyper-V Ubuntu/Docker or physical device evidence. Not every item requires **all** devices; consult each record's `outstanding_gates`, `hardware_requirements`, `known_limitations` before testing.
- **All 88**: keep `TESTING`; both labels are **scheduling and evidence-collection hints**, not CI success or permission grants.

**Trust limits:** A TCP port check does not authenticate Ubuntu, the `aura-transport` principal or a root-owned broker helper; Docker availability does not prove sandbox isolation; `Get-VM Running` is not an F2.7 signed attestation. Real OSWorld-V2 execution requires the separately governed `core/scripts/run_osworld_v2_live.py` admission gates with signed network isolation and a fresh Owner approval. Do **not** use `--privileged`, bypass MCP Gateway, expose `docker.sock` to `aura-transport`, or change PR #64's sealed contracts. Physical microphone, Windows Hello, display, camera and emergency stop must be witnessed and signed separately. Use `core/scripts/hardware_stage_c_acceptance.py` for review items; only `core/scripts/verify_physical_hardware.py` with independently signed receipts provides cryptographic evidence.

**Expected status until those checks and Owner evidence exist:** `COMPLETED=29 ELIGIBLE=29` for A+B1; B2-Owner=17, B2-Env=71, both `TESTING`. The new validator refuses tampered B2 labels, contradictory readiness flags, overlap or missing IDs.
