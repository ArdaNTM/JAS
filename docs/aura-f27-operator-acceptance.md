# F2.7 operator acceptance — inactive candidate and future live audit

Issue #63; Draft PR #64 stacked on PR #61's feature branch. The historical F2.6 release lock (349 files) is preserved in release-manifest.f26.json. The current release-manifest.final.json is a NEW F2.7 review-candidate lock, not a production approval.

## Offline promotion

The existing F2.6 Python 3.13 Work candidate has 9,028 pinned files. An independent Administrator must verify the exact Git commit and Git blob of scripts/Invoke-AuraF27OfflinePromotion.ps1, then extract to a protected directory OUTSIDE the writable D:\AURA checkout. Do NOT run an elevated script directly from D:\AURA\JAS.

Windows PowerShell 5.1, after the pinned script has been independently reviewed, extracted, and protected at C:\Program Files\AURA-F26-Operator\F27-Reviewed\Invoke-AuraF27OfflinePromotion.ps1:

    $ErrorActionPreference = 'Stop'
    $Script = 'C:\Program Files\AURA-F26-Operator\F27-Reviewed\Invoke-AuraF27OfflinePromotion.ps1'
    & $Script -SelfTest
    if ($LASTEXITCODE -ne 0) { throw 'STOP: promotion static test failed' }
    & $Script
    if ($LASTEXITCODE -ne 0) { throw 'STOP: candidate SHA verification failed' }
    & $Script -Promote
    if ($LASTEXITCODE -ne 0) { throw 'STOP: inactive candidate promotion failed' }

Promotion is non-destructive and fails if the destination exists. The script checks candidate SHA-256, seals EACH file and directory DACL (SYSTEM/Admin Full, dedicated Broker Read/Execute, owner Admin, no inheritance), checks relocated Python -I imports, rehashes 9,028 files before and after the same-volume rename to the requested f26-38c42d1 directory. It never enables AuraDockerBroker, installs SCM, creates service.json, issues a signature, or performs remote SSH.

The newly sealed f26-38c42d1 is an INACTIVE F2.6 runtime. IT DOES NOT CONTAIN F2.7 CODE. The new F2.7 SCM transport requires a separately constructed and independently sealed F2.7 runtime inventory before activation.

## Effective access tests under real Agent and Auditor logon sessions

The independently reviewed scripts/Test-AuraF27SealedRuntimeToken.ps1 must also be obtained from the same pinned Git commit and protected location. Run once under each separate REAL Agent and Auditor Windows token (not in the admin PowerShell). The expected SID must be independently corroborated with Windows account records.

    $Script = 'C:\Program Files\AURA-F26-Operator\F27-Reviewed\Test-AuraF27SealedRuntimeToken.ps1'
    $ExpectedSid = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
    & $Script -Mode Agent -ExpectedSid $ExpectedSid
    if ($LASTEXITCODE -ne 0) { throw 'STOP: Agent access acceptance failed' }

Use -Mode Auditor in the separate Auditor session. No File.Open handle may succeed for Read OR Write. Missing files and non-AccessDenied IO failures do NOT count as a PASS.

## F2.7 LIVE activation gate — independent operator ONLY

The Windows adapter now has a *gated* branch: deny_only is the default, and audit_only is accepted only after a fresh Ed25519 signature by an OFF-HOST operator key, exact policy/Windows SID/run/VM/disk/runtime-inventory/SSH host-key hash binding, expiry within 15 minutes, sealed file and complete runtime checks, real SCM logon identity, and a durable Windows approval nonce. Requests require an actual authenticated Auditor named-pipe token and an atomic Windows request nonce. Ubuntu requires pinned forced SSH, unprivileged aura-transport, SO_PEERCRED root-helper Unix socket, an independent Linux durable nonce, strict Docker resource/run ownership and fixed negative network probes. Successful measurements are UNSIGNED observations, never ISOLATION_SIGNED.

Do NOT activate based on GitHub CI alone. Before SCM installation/activation: produce a new signed F2.7 runtime release, verify actual Windows and Ubuntu identities, correct protected replay database schema/ACLs, verify known-host fingerprint out of band from Ubuntu console, test wrong SID/approval/signature/nonce/run/VM/host-key/negative probes, collect independent operator attestation and plan rollback. No credentials or signing private keys belong in the repository or logs. Leave AuraDockerBroker disabled, SCM absent, service.json absent, deny_only until these tests are complete and independently approved.

## F2.7: separate, sealed inactive runtime build (new release candidate)

The host-reported protected **F2.6** baseline and Agent/Auditor negative-access tests
were PASS. Its `f26-38c42d1` directory remains immutable and is NEVER overlaid.

A new, independently reviewed, operator-only script
`scripts/Invoke-AuraF27BuildRuntime.ps1` builds F2.7 from the same 9,028
F2.6 Python binaries **after** rehashing all 9,028 against the independently
pinned F2.6 inventory. It overlays exactly 16 explicitly allowlisted Git
files: the SCM adapter, the F2.7 Ed25519 approval/bridge/SSH modules and
the strict dependency closure. Every source is verified against a reviewed
40-character commit via `git archive` and `git hash-object`.

The builder requires `-Build -SourceCommit <reviewed-40-character-Git-sha>`
and may only be run from a protected operator copy whose Git blob has been
verified before elevation. `-SelfTest` is safe in CI, requiring no host.
It builds a **new**, non-overwriting `D:\AURA\Trust\DockerBroker\bin\f27-<sha12>`
candidate through a protected `.f27-staging-* ` directory; verifies
full per-file SHA-256 and persisted NTFS ACL with SYSTEM/Admin Full Control,
Broker Read/Execute and NO Agent/Auditor, then checks isolated Python 3.13
imports before same-volume promotion. The runtime SHA-256 inventory and
receipt are stored in independently protected
`C:\Program Files\AURA-F26-Operator\F27-build-<sha12>`, OUTSIDE the code
tree (no self-referential manifests). New runtime file count is based on
the original 9,028 plus the explicit overlay, accounting for overlaps:
do NOT assume exactly 9,044 until the verified host build reports it.

Host acceptance requires the verified on-disk candidate manifest, the
relocated import check, a new real-token Agent/Auditor denial test for this
**F2.7** target, and separate independent review of signer/SCM/SSH.
No production policy is written or activated by this build; no keys, SSH
credentials, nonce ledger, service installation, Docker operations or
`ISOLATION_SIGNED` receipt are created. Keep `AuraDockerBroker` disabled
and `deny_only` enforced. A GitHub CI selftest is NOT a complete host
promotion or end-to-end audit.

## 2026-11-09 — Windows native `python -c` quote-loss remediation

In the first real F2.7 Build, 9,028 source files plus 16 pinned overlay sources
were copied and sealed, but Windows PowerShell 5.1 stripped quotes from
embedded Python `-c` source and the isolated import step failed with
`SyntaxError` before any final target was promoted.

The updated builder executes a **separate immutable Git-reviewed Python file**
`scripts/verify_f27_runtime_imports.py`, first verifying its Git blob,
copying it into the protected operator evidence directory, sealing its ACL
and hashing it. The sealed staged Python then executes
`python.exe -I -B <sealed-operator-proof>/verify_f27_runtime_imports.py`.
No inline `-c` Python is passed through PowerShell or copied into the runtime.
Linux/Windows CI run Python's syntax compiler on the exact verifier bytes.

**Only the previously failed staging folder**
`.f27-staging-3921783feff1470e9ed927898fe815d0` may be cleaned by invoking
`-CleanupStale -StaleStageName .f27-staging-3921783feff1470e9ed927898fe815d0`
with `-SourceCommit 3df215826216131ea82826fa3b491ecd97f8625b`.
This operation uses pinned old Git source objects and protected old build
proof, verifies baseline 9,028 file SHA-256 and all original 16 overlay
source blobs, then verifies the **entire staged file inventory, every ACL,
and every reparse-point exclusion** before deleting exactly that folder.
It does not modify the old `F27-build-3df215826216` evidence or any
successful runtime. If an unexpected file or ACL is found, cleanup stops;
never bypass it with a wildcard or broad recursive delete.

Only after exact cleanup PASS, use the new reviewed commit's `-Build` mode
to produce its own separate F2.7 runtime directory and SHA-256 inventory.
The old `f26-38c42d1` baseline and operator root remain unchanged.

## 2026-11-09 — Import verifier must NEVER be treated as a runtime overlay

A host-reported F2.7 retry at pinned `3f518d003bded08e93908b8f47747f9dc6e6a260`
passed the SHA/ACL-protected 9,028-file F2.6 copy, but
`[IO.File]::Copy` failed with `DirectoryNotFoundException` referencing
the **staging root itself**, not a missing nested subdirectory.
Root cause: the archive contains **17** source files (16 runtime overlays
plus `scripts/verify_f27_runtime_imports.py`), but the loop copied all
17 using `$Overlay[$Key]`. The verifier has no runtime destination,
so its empty mapped path resolved to the root directory.

The corrected builder uses separate `$OverlayPaths` (16 destinations)
and `$Paths` (17 Git archive/verification sources). For every overlay,
it checks non-empty explicit destination, no traversal/ADS, containment
within the staging directory, correct parent-path resolution, and
existing sealed parent directories created using the restrictive
SYSTEM/Admin + Broker RX DACL **before** `[IO.File]::Copy`.
Top-level service script and nested package parents are both checked.
The verifier remains in the separately protected operator evidence
directory, never copied as a runtime module.

For the new failed stage only, use the reviewed builder's
`-CleanupStale -StaleStageName .f27-staging-05a452e270324f82982a2055f032c282
-SourceCommit 3f518d003bded08e93908b8f47747f9dc6e6a260`.
Cleanup validates exact stage/commit pairing, 9,028 baseline SHA hashes,
all 16 source overlay SHA values, exact 9,044-file (unless an overlay
overlaps the baseline; index count is authoritative) sealed stage,
per-item owners/ACLs and absence of reparse paths before removing only
the nominated staging directory. If any check fails, do not manually
delete or weaken ACLs. The previous failed build's evidence remains
intact; the new build uses a **different commit-keyed proof directory**.

## F2.7 production-candidate native Windows token probe

The independently reviewed, read-only `scripts/Test-AuraF27NativeRuntimeToken.ps1`
checks the exact, *already built* 9,044-file candidate
`D:\AURA\Trust\DockerBroker\bin\f27-26ffdba485cc`, with manifest SHA-256
`d9eb33c8ec0c494aec1039919699d4362e5222684048b160589b5bf88adcf21d`.
The original F2.6 negative-access probe is NOT valid for new F2.7 acceptance.
Independent Administrator must first verify the exact receipt and every one
of the 9,044 file digests (with protected paths/no reparse and sealed DACLs)
from operator-only evidence `C:\Program Files\AURA-F26-Operator\F27-build-26ffdba485cc`, and confirm the exact three runtime target files
(`python.exe`, `python3.dll`, `DLLs/_asyncio.pyd`) are in the manifest.
A separately published, independently blob-verified, Admin-owned read-only
runner must allow ONLY the local `AuraAgent` and `AuraAuditor` accounts to
read and execute the probe. Run once with separate real Windows logon tokens,
passing individually checked SIDs, capture outputs and require exactly six
denied Read/Write handles per identity, plus exit zero and matching token SID.
Never grant the Agent or Auditor runtime read access to make the probe run.

**F2.7 standalone import test and negative token probes are not an Ed25519
operator approval**, do not create `service.json`, trusted public keys,
`operator-approval.json` or `f27-nonces.sqlite3`, do not enable the Broker
or start Ubuntu units at this stage. The independent signer must be off-host,
with exact 9,044-file manifest bytes, approved service policy, SSH known_hosts
bytes, run/VM and disk hash claims bound and reviewed separately. PR stays Draft.

## F2.7 P0: root-owned measured QCOW2 disk and signed hash binding

The previous Windows bridge accepted an Ed25519-signed disk SHA-256 claim
without computing the current Ubuntu host QCOW2 digest. This is a live
activation P0 blocker. The current offline candidate adds the exact
\`measure_vm_disk\` SSH/root-helper operation, permitted only for the signed
run's full VM ID. The root helper verifies a unique \`/System.qcow2\` read-only
bind, Docker labels/image/network, root-controlled *non-writable* path
ancestors and root-owned read-only QCOW2 snapshot. It hashes the actual file
with kernel no-follow flags and checks fd inode, size, timestamps and Docker
mount metadata before/after the read. It returns only bounded SHA-256/source/
device/inode/size metadata, never an arbitrary file-read response.

The Windows SCM bridge requires matching trusted measurements before
the network probes AND after all probes, both matching the signed disk
hash and each other. A changed source, mutated disk, wrong run/VM,
writable mount, symlink, or concurrent file metadata mutation denies.
The Linux root helper is in the trusted computing base. This does not
defeat a compromised root account or prove absolute concurrent immutability;
operator must use an independently provisioned stable, root-owned QCOW2
snapshot under directories writable only by root.

**NOT DEPLOYED**: The old sealed 9,044-file F2.7 runtime remains unchanged,
and the inactive Ubuntu installed helper remains at its previous reviewed
version. Any future live acceptance requires a NEW Windows sealed runtime
promotion, independent file/ACL/token reacceptance, independent Ubuntu
root-helper update, valid OSWorld run evidence and fresh off-host signature.
No SCM service, SSH key install, policy enablement, socket enablement or
ISOLATION_SIGNED approval happens in this offline commit.
