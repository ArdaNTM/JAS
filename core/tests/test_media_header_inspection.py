"""Feature #110: local media header sanity, spoofing and resource-limit tests."""
from __future__ import annotations

import io
import struct
import wave
import zlib

import pytest

from aura_core.filesystem.media_header import inspect_media_header


PNG = b"\x89PNG\r\n\x1a\n"


def png(width=24, height=18, *, bit_depth=8, color=2):
    header = struct.pack(">IIBBBBB", width, height, bit_depth, color, 0, 0, 0)
    return PNG + b"\x00\x00\x00\rIHDR" + header + struct.pack(
        ">I", zlib.crc32(b"IHDR" + header)
    )


def wav():
    result = io.BytesIO()
    with wave.open(result, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * 1600)
    return result.getvalue()


def test_real_png_header_crc_and_metadata_only():
    image = inspect_media_header(png(), declared_media_type="image/png")
    assert image.kind == "png"
    assert (image.width, image.height) == (24, 18)
    assert len(image.source_sha256) == 64
    assert image.untrusted
    assert image.content_integrity_verified is False
    assert image.safe_to_render is False
    assert image.authorization_checked is False


def test_gif87a_and_gif89a_with_pixel_limits():
    for kind in (b"GIF87a", b"GIF89a"):
        result = inspect_media_header(kind + struct.pack("<HH", 300, 200) + b"\x00\x00\x00")
        assert result.kind == "gif"
        assert (result.width, result.height) == (300, 200)


def test_pcm_wav_real_stdlib_bytes():
    audio = inspect_media_header(wav(), declared_media_type="audio/wav")
    assert audio.channels == 1
    assert audio.sample_rate_hz == 16000
    assert audio.samples == 1600
    assert audio.duration_seconds == pytest.approx(0.1)
    assert not audio.safe_to_render


def test_mime_spoof_and_corrupt_png_crc_rejected():
    with pytest.raises(ValueError, match="disagree"):
        inspect_media_header(png(), declared_media_type="image/jpeg")
    damaged = bytearray(png())
    damaged[-1] ^= 0x01
    with pytest.raises(ValueError, match="checksum"):
        inspect_media_header(bytes(damaged))


@pytest.mark.parametrize("dimensions", [
    (0, 100), (100, 0), (10001, 2), (8000, 8000),
])
def test_oversized_dimensions_rejected(dimensions):
    with pytest.raises(ValueError):
        inspect_media_header(png(*dimensions))


@pytest.mark.parametrize("blob", [
    b"", b"not a media file", b"\xff\xd8\xff\xe0FakeJPEG",
    PNG + b"\x00" * 5, b"x" * (8 * 1024 * 1024 + 1),
])
def test_invalid_or_oversized_payload_rejected(blob):
    with pytest.raises(ValueError):
        inspect_media_header(blob)


def test_unsupported_png_mode_and_type_confused_inputs():
    with pytest.raises(ValueError, match="unsupported"):
        inspect_media_header(png(bit_depth=1, color=2))
    with pytest.raises(ValueError):
        inspect_media_header(bytearray(png()))
    with pytest.raises(ValueError):
        inspect_media_header(png(), declared_media_type=True)


def test_unsupported_or_malformed_wav_rejected():
    malformed = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"broken-data" * 10
    with pytest.raises(ValueError, match="invalid WAV header"):
        inspect_media_header(malformed)
