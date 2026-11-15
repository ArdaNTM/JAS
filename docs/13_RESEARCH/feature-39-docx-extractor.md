# Feature #39 — offline DOCX text extraction (partial)

Adds `aura_core.filesystem.docx_extractor.extract_docx_text(payload: bytes)`.
The input MUST already have been read through an authenticated,
PermissionEngine/MCPGateway-governed filesystem capability. This component
never opens paths, makes network requests, renders images or runs macros.

It parses bounded ZIP + Office Open XML bytes (up to 4 MiB compressed,
8 MiB uncompressed, 128 members, 2 MiB per XML part, 100:1 member expansion
ceiling, 25,000 XML nodes, 5,000 paragraphs, and 100,000 text characters).
It rejects ZIP-slip paths, symlinks, encrypted/unsupported compression,
duplicate names, embedded executables/macros, DTD/ENTITY declarations,
external relationships, and unsupported/malformed content types. It
returns paragraphs in document order, untrusted text and the archive SHA-256
as a content fingerprint, **not** authenticity proof.

Limitations: no PDF parsing, OCR, images, section layout, track changes,
hyperlinks, old DOC files, or encrypted DOCX support. External relationships
are deliberately rejected even when they only refer to hyperlinks.
No endpoint/tool is exposed and `authorization_checked=False` explicitly
states this function cannot authorize itself. High-quality document
interpretation, user acceptance, and live authorized filesystem integration
are not implemented. Feature #39 stays **TESTING / PARTIAL**, not COMPLETED.

Verification:
`cd core && uv run pytest -q tests/test_docx_extractor.py`
followed by full AURA Core Assurance and Final Release Lock.
