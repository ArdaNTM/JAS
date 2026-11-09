# AURA F2.6 one-command offline verification (no activation)

## Scope and limits

The pinned source build is \`38c42d1308056cc157b7233280a7d51a2d5b998f\`,
with release-lock digest \`3c75ed20803ed60d786e3b2da64f70c90cef4490be4831e3e27e829b220b0ccd\`.
Its 349 locked source files are **not** the same inventory as the 265
Windows staging payload files or the 9,028 Python runtime files.

The Work-created runtime candidate remains local at
\`D:\AURA\JAS\artifacts\aura-f26-runtime-38c42d1\`.
It is **not** committed or signed by this GitHub PR. This verifier pins
three observed evidence-document hashes, scans every runtime inventory
entry, refuses extra or missing files, and checks for reparse points.
Those hashes do **not** constitute an independent cryptographic build
provenance signature.

The static test job verifies Windows PowerShell syntax and parser
guardrails on a hosted runner. It cannot test user Windows ACLs,
actual Agent/Auditor logon tokens, kernel/VM isolation, private key
access or independent operator attestation.

## Single operator inspection

Obtain the script from the exact reviewed GitHub commit, compare its
blob and file SHA-256 against the reviewed commit, then place it in a
trusted, protected operator directory that no AURA Agent can modify.
Never run a mutable copy from \`D:\AURA\JAS\scripts\` elevated.

Under a separate real administrator token on the target Windows host:

\`\`\`powershell
& 'C:\Program Files\AURA-F26-Operator\scripts\Invoke-AuraF26PinnedAudit.ps1' -Mode Operator
\`\`\`

The operator check re-verifies the exact pinned source commit, the
349-file release lock, 265-file protected source payload, 9,028-file
Python runtime candidate inventory, three fixed evidence-document hashes,
and non-inherited trusted directory ACLs. It requires disabled
\`AuraDockerBroker\`, absent \`service.json\` and absent
\`AuraOSWorldAuditBroker\` SCM registration. It deliberately returns
exit code **2 (ACCEPTANCE_BLOCKED)** after offline evidence is validated
because separate token tests and sealed runtime deployment are pending.
No service/account/ACL state is changed by this command.

## Real token negative access tests

**Two additional independent logon sessions are mandatory.** An elevated
administrator cannot substitute self-reported \`whoami\` output for the
real Agent/Auditor token. The operator must independently witness and
record each test under a real distinct user account, with that account's
known Windows user SID from the OS:

\`\`\`powershell
& 'C:\Program Files\AURA-F26-Operator\scripts\Invoke-AuraF26PinnedAudit.ps1' -Mode Agent -ExpectedSid 'S-1-5-21-...'
& 'C:\Program Files\AURA-F26-Operator\scripts\Invoke-AuraF26PinnedAudit.ps1' -Mode Auditor -ExpectedSid 'S-1-5-21-...'
\`\`\`

Do not run these commands from the administrator's token. They check
actual process SID, refuse a token containing Administrators SID
(including deny-only visibility), and attempt *non-mutating*
read and write handle opens against the pinned private key and protected
staging payload. **Successful access is a failure**. Missing files or
indeterminate errors are *not* accepted as access denial.

The negative-access probes do not by themselves attest the **final**
runtime after a protected copy; repeat the same checks against a sealed
production runtime after independent operator packaging acceptance.

## Outstanding deployment work

1. An independent operator must verify the runtime's complete native
   DLL/PYD provenance, Python 3.13 x64 and \`-I\` isolation *from a sealed
   non-Agent-writable location*. A previous Work import smoke test alone
   cannot authorize deployment.
2. Build a protected offline package under an operator-controlled
   directory. Every file and directory must have an Administrators
   owner, inheritance disabled, SYSTEM/Administrators full control, and
   only read/execute for the dedicated Broker; verify no Agent/Auditor
   effective write or read access. Existing Trust ACLs must not be
   changed by an Agent tool.
3. Independent real Windows identity tests, root/private-key ACL,
   SCM security boundary, and a second SHA comparison after relocation
   must pass before any non-destructive promotion to protected \`bin\`.
4. Keep Broker disabled, leave \`service.json\` absent, do not install
   the SCM service, do not activate \`audit_only\`, and do not issue
   \`ISOLATION_SIGNED\`. This phase is inactive even if tests pass.

**Never interpret hosted CI success or a PASS of an offline hash check
as full Windows operator acceptance.**

## Ancestor delete-child security gate

Before treating any protected Broker child path as immutable, the operator
verifies `D:\`, `D:\AURA` and `D:\AURA\Trust` against non-administrator
write/delete and `DELETE_CHILD` rights. Protecting only
`DockerBroker\bin` is insufficient if an Agent can replace/rename its
parent directory. If this gate blocks, **do not remove broad ACLs by
trial-and-error**: review parent and child permissions and adjust the host
layout via an independent Windows administrator without disrupting the
Agent's working repository. The gate is read-only and never changes ACLs.
