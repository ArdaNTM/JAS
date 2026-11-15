# Feature #110 — offline media header observations (partial)

`aura_core.filesystem.media_header.inspect_media_header` reads bounded
**already-authorized bytes** and identifies certain PNG, GIF and PCM-WAV
header fields using only the Python standard library.

The parser verifies PNG IHDR CRC and shape/mode, GIF width/height and
PCM-WAV channels/sample rate/approximate duration. It checks optional
declared MIME type against header-derived type, refusing disagreement.
There is no network call, filesystem opening, decoding of raster pixels,
playback, transcoding or tool execution. Output always contains
`content_integrity_verified=False`, `safe_to_render=False` and
`authorization_checked=False`.

Limits: ≤8 MiB input; PNG/GIF ≤10k per dimension and 50 million pixels;
PCM WAV ≤8 channels/384kHz/10 million frames and bounded decoded byte
estimate. Support intentionally excludes JPEG/MP4/WebP, full validation,
malware scanning, hidden polyglots, metadata stripping, authentication,
file storage, creative edits and user-facing media management.
A valid header is **NOT** a trustworthy complete file; downstream
decoding must remain in an independently sandboxed authorized processor.

Tests cover real stdlib WAV bytes, PNG IHDR CRC, GIF headers, MIME mismatch,
oversized/unphysical dimensions, invalid/unknown formats and type confusion.

Feature #110 stays PARTIAL; complete authorized file/media operations,
storage and Owner acceptance are outstanding. Run
`cd core && uv run pytest -q tests/test_media_header_inspection.py`
plus full Core Assurance and Final Release Lock.
