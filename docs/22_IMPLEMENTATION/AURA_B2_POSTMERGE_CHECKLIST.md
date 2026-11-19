# AURA B2 post-merge Windows / Hyper-V Ubuntu / Docker acceptance checklist

**Prerequisite:** PR #64 and PR #158 are already Owner-merged (`main` b09ad74). Owner manually approves PR #65 merge, checks out updated `main` at `D:\\AURA\\JAS` and verifies the new HEAD. Never merge or push to `main` automatically. The script performs **read-only** probes and scoped regression tests; it does not create Owner approval, modify ACLs, enable a privileged Docker broker, launch QEMU or sign hardware receipts. Avoid personal data in disposable lab tests.

## One command after merge (Windows PowerShell, from repo root)

```powershell
& ".\\core\\.venv\\Scripts\\python.exe" ".\\core\\scripts\\b2_postmerge_check.py" --repo-root "." --vm-name "AURA-Broker-Lab" --ubuntu-host "<UBUNTU_VM_IP>" --hardware-evidence "<EXTERNAL_SIGNED_EVIDENCE.json>" --trusted-public-keys "<PINNED_PUBLIC_KEYS.json>"
```

Replace **only** the three placeholders with actual values from the Owner's isolated lab. Both evidence inputs must be produced by a separately provisioned trusted signer; the runner cannot mint evidence. For a non-invasive inventory preview (no host probes or test execution): `& ".\\core\\.venv\\Scripts\\python.exe" ".\\core\\scripts\\b2_postmerge_check.py" --repo-root "." --list-only`.

The single command verifies the 117-feature ledger and canonical source pins, tracker schema, 440-file release lock, and runs available **deduplicated B2-Env-only (71) focused regression files** with `pytest -q --tb=short`, but records unavailable tracker-listed files as **BLOCKED** instead of inventing passing results. The runner prints the currently missing B2-Env-focused paths as **BLOCKED** instead of inventing passing results; exact counts are determined from the checked-out tree. It then performs Windows platform presence, read-only Docker Engine inspection, read-only `Get-VM` running-state inspection, and TCP reachability of the configured Ubuntu VM. If external Ed25519-signed evidence and separate pinned public keys exist, the existing `verify_physical_hardware.py` gate validates them. Missing/busy host dependencies produce **INCONCLUSIVE/blocked**, not fabricated PASS.

## Exact subgroup meaning and remaining live acceptance

- **B2-Owner (17)**: `34, 46, 50, 58, 61, 64, 68, 70, 71, 72, 74, 75, 108, 109, 110, 114, 117`. All 17 are `COMPLETED` **for explicitly bounded offline v1 `technical_goal` only** after the Owner merge and exact-head focused CI. Original production/physical/full-product requirements remain in `known_limitations`; no device acceptance is inferred.
- **B2-Env (71)**: `1, 3, 4, 6, 7, 9, 11, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 45, 48, 49, 51, 54, 55, 56, 57, 60, 63, 69, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 103, 104, 105, 106, 107, 113, 115, 116`. Requires actual relevant host, provisioned model, external provider, Windows/Hyper-V Ubuntu/Docker or physical device evidence. Not every item requires **all** devices; consult each record's `outstanding_gates`, `hardware_requirements`, `known_limitations` before testing.
- **All 71 B2-Env**: keep `TESTING`; the track is a **scheduling/evidence-collection hint**, not CI success or permission grant. The 17 B2-Owner completion records are *offline v1 only*.

**Trust limits:** A TCP port check does not authenticate Ubuntu, the `aura-transport` principal or a root-owned broker helper; Docker availability does not prove sandbox isolation; `Get-VM Running` is not an F2.7 signed attestation. Real OSWorld-V2 execution requires the separately governed `core/scripts/run_osworld_v2_live.py` admission gates with signed network isolation and a fresh Owner approval. Do **not** use `--privileged`, bypass MCP Gateway, expose `docker.sock` to `aura-transport`, or change PR #64's sealed contracts. Physical microphone, Windows Hello, display, camera and emergency stop must be witnessed and signed separately. Use `core/scripts/hardware_stage_c_acceptance.py` for review items; only `core/scripts/verify_physical_hardware.py` with independently signed receipts provides cryptographic evidence.

**Expected ledger before B2-Env live acceptance:** `COMPLETED=46 ELIGIBLE=46 TESTING=71` (A 9, B1 20, B2-Owner 17; B2-Env 71 TESTING). The new validator refuses tampered B2 labels, contradictory readiness flags, overlap or missing IDs.


## 2026-11-19 — Owner-approved bounded v1, exact new main 5e51d3f

**Signed-off in chat by repo Owner for software/simulation *scope*, not physical lab evidence.**

- B2-Env software-v1 accepted **12**: \`3,4,15,29,30,48,56,63,103,105,107,115\` — only frozen offline \`technical_goal\`; actual live UI, model, scheduler, cryptographic custody and production identity require separate v2 acceptance.
- B2-Env hardware-exception simulation-v1 accepted **7**: \`81,85,86,87,88,89,90\`. These test artificial frames, inventory/state samples or simulated MQTT transport/attestations in scoped Core paths. They **cannot** verify a physical depth camera, robot motion/estop, homeowner bridge, independently provisioned sensor, or certified safety interlock. Full-product blockers were preserved verbatim in \`known_limitations\`.
- B2-Env remaining **52 TESTING**: \`windows_local\` **45** and \`hyperv_docker\` **7**. Group indices remain the frozen 57/7/7 partition to preserve original geographic acceptance scope; \`B2_env_acceptance\` separately records 12/7 signed-off narrow v1 and 52 outstanding.
- Overall A=9, B1=20, B2-Owner=17, B2-Env accepted-v1=19 => **COMPLETED=65 ELIGIBLE=65 TESTING=52**. Under no circumstances is simulated MQTT or an unsigned pytest JSON file a real hardware certificate or a Gateway tool-authorization token.
- Owner-merged integration evidence: PR #159 to \`main\` as \`5e51d3f50b53f482e14e3d1d73a375d08e6e9eb7\`, 2572 Core PASS/14 SKIP, 13/13 GitHub workflows PASS on source head \`7beeb4a7c95e6b571fddeae95ef5b802b624cd8f\`; new PR must independently pass current CI before merge.

### One command: real pytest execution, **unsigned software-only** JSON report

After Owner manually merges this follow-up PR and updates \`main\`:

\`\`\`powershell
cd D:\AURA\JAS
& ".\core\.venv\Scripts\python.exe" ".\core\scripts\b2_postmerge_check.py" --repo-root "." --tests-only --run-pytest --evidence-out "D:\AURA\Trust\b2-env-tests.json"
\`\`\`

This runs the **remaining 52 features' deduplicated 50 focused tests** with \`pytest -q --tb=short\`, audits the 117-feature source pins and canonical release manifest, and atomically writes SHA-256 test-file digests, exact Git HEAD, pytest exit code/summary and explicit \`hardware_verified=false\` into an **unsigned** JSON record outside the repository. A failed test or failed source/ledger lock gives \`BLOCKED\`. To narrow tests: add \`--group windows_local\` (45 features) or \`--group hyperv_docker\` (7). These are **software regression tests only**; real Windows session, Ubuntu broker and physical hardware acceptance still require existing independently signed security receipts and separate Owner acceptance.
