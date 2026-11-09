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
