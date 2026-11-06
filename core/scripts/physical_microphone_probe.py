"""Real Windows microphone measurement using the native WinMM waveIn API.

No synthetic sound source, device mock, generated evidence signatures or
external microphone package. Measures microphone capture-buffer arrival,
sample counts and audible non-silence. This is NOT Nirvana Voice end-to-end
first-audio latency or barge-in evidence: an actual in-app TTS playback,
interrupt, STT and independent timestamp source are required for those claims.
No recorded PCM is retained or transmitted.

Run interactively on the physical Windows host:
    uv run --frozen python scripts/physical_microphone_probe.py --samples 40
"""
from __future__ import annotations

import argparse
import array
import asyncio
import ctypes
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from ctypes import wintypes

WHDR_DONE = 0x00000001
WAVE_FORMAT_PCM = 1
WAVE_MAPPER = 0xFFFFFFFF
SAMPLE_RATE = 16000
SAMPLES_PER_BUFFER = 960


class RealMicrophoneUnavailable(RuntimeError):
    """OS sound capture failed; no synthetic fallback is allowed."""


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


def percentile(values: list[float], fraction: float) -> float:
    """Deterministic nearest-rank percentile, no numpy or fake sampling."""
    if not values or not 0 < fraction <= 1:
        raise ValueError("Percentile requires real samples and valid fraction")
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 3)


@dataclass(frozen=True, slots=True)
class MicrophoneProbe:
    sample_count: int
    buffer_p50_ms: float
    buffer_p95_ms: float
    buffer_max_ms: float
    audible_buffers: int
    native_winmm: bool = True
    nirvana_voice_end_to_end_verified: bool = False
    barge_in_verified: bool = False
    hardware_verified: bool = False

    def public(self) -> dict[str, object]:
        return {
            "check": "microphone_capture_native",
            **{key: getattr(self, key) for key in self.__dataclass_fields__},
            "note": "Native microphone input only; Nirvana TTS and barge-in remain unverified.",
        }


def capture_microphone(*, samples: int = 40) -> MicrophoneProbe:
    if sys.platform != "win32":
        raise RealMicrophoneUnavailable("Physical Windows audio capture is required")
    if not 30 <= samples <= 200:
        raise ValueError("Capture requires 30..200 bounded device buffers")
    wave = ctypes.WinDLL("winmm", use_last_error=True)
    wave.waveInGetNumDevs.restype = wintypes.UINT
    if wave.waveInGetNumDevs() < 1:
        raise RealMicrophoneUnavailable("No physical microphone capture device available")
    handle = ctypes.c_void_p()
    fmt = WAVEFORMATEX(
        WAVE_FORMAT_PCM, 1, SAMPLE_RATE, SAMPLE_RATE * 2,
        2, 16, 0,
    )
    wave.waveInOpen.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
        ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t,
        ctypes.c_size_t, wintypes.DWORD,
    ]
    for fn in (wave.waveInStart, wave.waveInStop, wave.waveInReset, wave.waveInClose):
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = wintypes.UINT
    for fn in (wave.waveInPrepareHeader, wave.waveInAddBuffer, wave.waveInUnprepareHeader):
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
        fn.restype = wintypes.UINT
    code = wave.waveInOpen(
        ctypes.byref(handle), WAVE_MAPPER,
        ctypes.byref(fmt), 0, 0, 0,
    )
    if code:
        raise RealMicrophoneUnavailable(f"WinMM waveInOpen failed: {code}")
    arrivals: list[float] = []
    audible = 0
    try:
        code = wave.waveInStart(handle)
        if code:
            raise RealMicrophoneUnavailable(f"WinMM waveInStart failed: {code}")
        print("Speak normally into the REAL microphone during sampling.", file=sys.stderr)
        for _ in range(samples):
            raw = ctypes.create_string_buffer(SAMPLES_PER_BUFFER * 2)
            header = WAVEHDR(
                ctypes.cast(raw, ctypes.c_void_p), len(raw), 0, 0, 0, 0, None, 0,
            )
            header_size = ctypes.sizeof(header)
            if wave.waveInPrepareHeader(handle, ctypes.byref(header), header_size):
                raise RealMicrophoneUnavailable("Could not prepare a real microphone buffer")
            try:
                start = time.perf_counter_ns()
                if wave.waveInAddBuffer(handle, ctypes.byref(header), header_size):
                    raise RealMicrophoneUnavailable("Could not queue microphone PCM buffer")
                deadline = time.monotonic() + 3
                while not header.dwFlags & WHDR_DONE:
                    if time.monotonic() >= deadline:
                        raise RealMicrophoneUnavailable("Real microphone buffer timed out")
                    time.sleep(0.002)
                elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
                if header.dwBytesRecorded != len(raw):
                    raise RealMicrophoneUnavailable("Incomplete physical microphone buffer")
                data = array.array("h")
                data.frombytes(raw.raw)
                peak = max(abs(sample) for sample in data)
                if peak > 400:
                    audible += 1
                arrivals.append(elapsed_ms)
            finally:
                wave.waveInUnprepareHeader(handle, ctypes.byref(header), header_size)
        if audible < max(2, samples // 10):
            raise RealMicrophoneUnavailable("No audible speech was captured; check device/mute")
        return MicrophoneProbe(
            sample_count=len(arrivals),
            buffer_p50_ms=percentile(arrivals, 0.5),
            buffer_p95_ms=percentile(arrivals, 0.95),
            buffer_max_ms=round(max(arrivals), 3),
            audible_buffers=audible,
        )
    finally:
        wave.waveInStop(handle)
        wave.waveInReset(handle)
        wave.waveInClose(handle)


async def run(samples: int = 40) -> MicrophoneProbe:
    return await asyncio.to_thread(capture_microphone, samples=samples)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=40)
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(run(args.samples))
    except (RealMicrophoneUnavailable, OSError, ValueError) as exc:
        print(json.dumps({
            "native_audio_capture_verified": False, "hardware_verified": False,
            "error_type": type(exc).__name__, "barge_in_verified": False,
        }, indent=2))
        return 2
    print(json.dumps(report.public(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
