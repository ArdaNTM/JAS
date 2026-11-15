# Feature #108 — bounded read-only RFC822/MIME preview (partial)

`aura_core.application.offline_email.preview_eml` processes
**already-authorized** raw RFC822/MIME bytes using the Python standard
library. It decodes metadata and one plain-text body, omits HTML rather than
rendering or executing it, and returns attachment **metadata plus SHA-256
only**. It does not expose attachment bytes in the preview, send mail,
fetch links, load mail accounts, authenticate users or invoke providers.

Limits: ≤512 KiB raw message, ≤32 MIME parts, ≤20 attachments, ≤256 KiB
per attachment, ≤100k plain-text body characters. Ambiguous From/To/Subject
headers, unsupported/defective MIME, duplicate plain-text bodies, unsafe
attachment filenames and excessive parts fail closed. Returned text is
explicitly untrusted and must be escaped in a UI.

This is not an anti-malware scanner, HTML sanitizer, spam classifier,
trusted sender certificate or an email connector. SHA-256 is only a content
fingerprint, not publisher authenticity. The input must be obtained by an
existing authenticated, PermissionEngine/MCP Gateway authorized account
integration. No consent, mail sending, mailbox read/write or Owner approval
is claimed. Feature #108 remains TESTING/PARTIAL until authenticated
connectors, send/modify approvals, privacy and real end-to-end acceptance.

Tests:
`cd core && uv run pytest -q tests/test_offline_email_preview.py`;
complete Core Assurance and Final Release Lock required.
