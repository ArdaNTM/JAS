# F2.7 reviewed code versus physical-host evidence (Issue #63)

This is a release-acceptance ledger for the Draft PR, not an operator-signed
activation receipt. It cannot authorize Windows SCM installation or Ubuntu
auditing. The signed trust boundary is not established by GitHub Actions alone.

## Shipped offline code

- Historical F2.6 inventory: 349 files, unchanged copy stored as release-manifest.f26.json.
- F2.7 source review candidate: 358 SHA-256 release-locked files under release-manifest.final.json.
- Ed25519 operator verifier: exact policy, user SIDs, run ID, VM ID, QCOW hash, runtime inventory and pinned SSH known-host hash, with at most 15-minute lifetime.
- Windows SCM dispatch: deny_only is the default; audit_only requires sealed signed operator approval, true Windows service SID, and a protected runtime before opening named pipe or SSH.
- Strict Auditor Windows named-pipe token, durable one-shot Windows approval/request SQLite nonce and bounded unsigned response.
- Ubuntu forced SSH frontend -> SO_PEERCRED root Unix socket helper -> durable Ubuntu SQLite nonce -> ownership-checked Docker inspect/fixed probes. No arbitrary Docker arguments or privilege escalation.
- Offline-only PowerShell 5.1 promotion from the pinned 9,028-file F2.6 Work runtime into a versioned, ACL-sealed, inactive bin child, and a distinct real-token post-promotion negative access probe.

## CI versus deployment

The F2.7 Linux and Windows contract jobs pass the signed approval, replay,
wrong SID, VM binding and negative network guardrails using offline/fake
clients. On the review candidate, several hosted jobs directly emitted
"AURA FINAL RELEASE LOCK: PASS" for the 358-file digest and both F2.7
contract jobs succeeded. A successful job is not the same as a successful
workflow conclusion; inspect the current PR checks before approving.

The user previously reported pass results on real Agent and Auditor tokens
for the F2.6 staging source, NOT post-promotion F2.6 executable files, and
NOT any F2.7 signed approval/SSH live path.

## Remaining independent host acceptance

1. An operator must personally verify the source Git commit and pinned blob
   of the F2.7 promotion script BEFORE running it elevated from a protected
   directory outside the mutable JAS checkout.
2. Promote 9,028 original F2.6 runtime files without overwriting existing
   bin, verify every SHA-256 post-copy, every explicit file/directory ACL,
   Python 3.13 -I imports, Broker RX and no Agent/Auditor access.
3. Repeat real Agent and Auditor OS-token negative access checks against the
   NEW protected executable target, not only the old staging source.
4. A new F2.7 Python runtime must be built and sealed from the F2.7 source;
   F2.6 candidate is an inactive preservation/rollback step, not live code.
5. Independent operator on separate trusted system must generate/hold its
   Ed25519 signing private key OFF-HOST, witness host/run/VM evidence and
   issue a short-lived signed approval, pinned to released F2.7 code bytes.
6. Independently pin SSH host key from Ubuntu console and prove actual
   aura-transport group isolation, SO_PEERCRED, remote helper ownership,
   Docker run/VM labels and nonce replay rejection.
7. Real Windows SCM and Ubuntu E2E should be performed only after a separate
   operator-reviewed activation. No audit-only policy is provisioned by CI.
8. Rollback remains service absent/disabled, no policy, Broker disabled.
   Never claim ISOLATION_SIGNED from unsigned negative network observations.

## Security invariants

The private operator signing key must not be put in GitHub, AURA, Windows
broker or Ubuntu containers. The Agent cannot create service.json, alter
SCM logon identity, read runtime/SSH key, or sign an isolation receipt.
All missing or stale evidence blocks activation by design.
