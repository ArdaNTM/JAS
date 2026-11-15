"""Bounded header-only inspection of already-authorized image/audio bytes.

Never decodes images, plays media, fetches URLs or authorizes downstream
parsers. A validated header is not proof that the complete file is safe.
"""
from __future__ import annotations

import hashlib
import io
import math
import struct
import wave
import zlib
from dataclasses import dataclass

_MAX_BYTES = 8 * 1024 * 1024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class MediaHeader:
    kind: str
    media_type: str
    source_sha256: str
    width: int | None = None
    height: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    samples: int | None = None
    duration_seconds: float | None = None
    untrusted: bool = True
    content_integrity_verified: bool = False
    safe_to_render: bool = False
    authorization_checked: bool = False


def _dimension(width: int, height: int) -> None:
    if not 1 <= width <= 10000 or not 1 <= height <= 10000:
        raise ValueError("invalid media dimensions")
    if width * height > 50_000_000:
        raise ValueError("media pixel budget exceeded")


def inspect_media_header(
    payload: bytes, *, declared_media_type: str | None = None
) -> MediaHeader:
    """Inspect PNG/GIF/PCM-WAV headers from in-memory bytes only."""
    if type(payload) is not bytes or not 10 <= len(payload) <= _MAX_BYTES:
        raise ValueError("bounded media bytes required")
    digest = hashlib.sha256(payload).hexdigest()
    values: dict[str, object]
    if payload.startswith(_PNG_SIGNATURE):
        if len(payload) < 33 or payload[8:16] != b"\x00\x00\x00\rIHDR":
            raise ValueError("invalid PNG IHDR")
        header = payload[16:29]
        crc = int.from_bytes(payload[29:33], "big")
        if zlib.crc32(b"IHDR" + header) != crc:
            raise ValueError("invalid PNG IHDR checksum")
        width, height, depth, color, compression, filtering, interlace = struct.unpack(
            ">IIBBBBB", header
        )
        _dimension(width, height)
        supported_depths = {
            0: {1, 2, 4, 8, 16},
            2: {8, 16},
            3: {1, 2, 4, 8},
            4: {8, 16},
            6: {8, 16},
        }
        if (
            depth not in supported_depths.get(color, set())
            or compression != 0 or filtering != 0 or interlace not in (0, 1)
        ):
            raise ValueError("unsupported PNG image header")
        values = {
            "kind": "png", "media_type": "image/png",
            "width": width, "height": height,
        }
    elif payload.startswith((b"GIF87a", b"GIF89a")):
        if len(payload) < 13:
            raise ValueError("truncated GIF header")
        width, height = struct.unpack_from("<HH", payload, 6)
        _dimension(width, height)
        values = {
            "kind": "gif", "media_type": "image/gif",
            "width": width, "height": height,
        }
    elif payload.startswith(b"RIFF") and payload[8:12] == b"WAVE":
        if len(payload) < 44:
            raise ValueError("truncated WAV header")
        with wave.open(io.BytesIO(payload), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            frames = handle.getnframes()
            comp_type = handle.getcomptype()
        if (
            not 1 <= channels <= 8 or not 8000 <= sample_rate <= 384000
            or not 1 <= sample_width <= 4 or not 0 <= frames <= 10_000_000
            or comp_type != "NONE"
        ):
            raise ValueError("unsupported WAV encoding or budget")
        if frames * channels * sample_width > _MAX_BYTES:
            raise ValueError("WAV decoded audio budget exceeded")
        duration = frames / sample_rate
        if not math.isfinite(duration) or duration > 600:
            raise ValueError("WAV duration exceeds limit")
        values = {
            "kind": "wav", "media_type": "audio/wav",
            "sample_rate_hz": sample_rate, "channels": channels,
            "samples": frames, "duration_seconds": round(duration, 6),
        }
    else:
        raise ValueError("unknown or unsupported media header")
    if declared_media_type is not None and (
        type(declared_media_type) is not str
        or declared_media_type != values["media_type"]
    ):
        raise ValueError("declared and observed media types disagree")
    return MediaHeader(source_sha256=digest, **values)
