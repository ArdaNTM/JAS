"""Diagnostic *native* Windows microphone capture using WinMM waveIn.

Enumerates WinMM input endpoints, tries Windows default WAVE_MAPPER first,
then physical/virtual OS devices and supported PCM formats. All WinMM calls
use explicit 64-bit safe ctypes signatures, capture is bounded and never
persists, uploads, fabricates or signs any audio. A working WinMM endpoint is
not proof of a physical microphone (virtual devices also exist).

This reports OS audio capture buffer latency, NOT Nirvana Voice/STT/TTS or
barge-in end-to-end p95. No result here grants MCP permissions or makes the
six-check independent hardware evidence gate pass automatically.

    uv run --frozen python scripts/physical_microphone_probe.py --list-devices
    uv run --frozen python scripts/physical_microphone_probe.py --samples 40
    uv run --frozen python scripts/physical_microphone_probe.py --device 1
"""
from __future__ import annotations

import argparse
import array
import asyncio
import ctypes
import json
import math
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

WHDR_DONE = 0x00000001
WAVE_FORMAT_PCM = 1
WAVE_MAPPER = 0xFFFFFFFF
MAX_PNAME = 32
SAMPLES_PER_BUFFER = 960  # 60 ms at preferred 16 kHz
FORMAT_CANDIDATES: tuple[tuple[int, int], ...] = (
    (16000, 1), (48000, 1), (44100, 1),
    (16000, 2), (48000, 2), (44100, 2),
)


class RealMicrophoneUnavailable(RuntimeError):
    """Native capture could not run; preserving the Windows diagnostic reason."""


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


class WAVEINCAPSW(ctypes.Structure):
    """WAVEINCAPSW from mmeapi.h; szPname is exactly 32 UTF-16 WCHARs."""

    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.DWORD),
        ("szPname", ctypes.c_wchar * MAX_PNAME),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


@dataclass(frozen=True, slots=True)
class InputDevice:
    device_id: int
    name: str
    max_channels: int

    def public(self) -> dict[str, object]:
        return {"id": self.device_id, "name": self.name, "channels": self.max_channels}


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
    device_id: int = WAVE_MAPPER
    device_name: str = ""
    sample_rate_hz: int = 16000
    channels: int = 1

    def public(self) -> dict[str, object]:
        return {
            "check": "microphone_capture_native",
            **{key: getattr(self, key) for key in self.__dataclass_fields__},
            "native_audio_capture_verified": self.native_winmm,
            "note": "WinMM capture only; this does not measure Nirvana Voice or barge-in.",
        }


def percentile(values: list[float], fraction: float) -> float:
    """Deterministic nearest-rank p50/p95 over measured, non-synthetic samples."""
    if not values or not 0 < fraction <= 1:
        raise ValueError("Percentile requires measured samples and a valid fraction")
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 3)


def _configure_wave(wave: object) -> None:
    """Declare Windows ABI: WinMM device ID is UINT, handles are pointer-sized."""
    wave.waveInGetNumDevs.argtypes = []
    wave.waveInGetNumDevs.restype = wintypes.UINT
    wave.waveInGetDevCapsW.argtypes = [
        ctypes.c_size_t, ctypes.POINTER(WAVEINCAPSW), wintypes.UINT,
    ]
    wave.waveInGetDevCapsW.restype = wintypes.UINT
    wave.waveInGetErrorTextW.argtypes = [
        wintypes.UINT, ctypes.c_wchar_p, wintypes.UINT,
    ]
    wave.waveInGetErrorTextW.restype = wintypes.UINT
    wave.waveInOpen.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
        ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t,
        ctypes.c_size_t, wintypes.DWORD,
    ]
    wave.waveInOpen.restype = wintypes.UINT
    for name in ("waveInStart", "waveInStop", "waveInReset", "waveInClose"):
        method = getattr(wave, name)
        method.argtypes = [ctypes.c_void_p]
        method.restype = wintypes.UINT
    for name in ("waveInPrepareHeader", "waveInAddBuffer", "waveInUnprepareHeader"):
        method = getattr(wave, name)
        method.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT,
        ]
        method.restype = wintypes.UINT


def _error(wave: object, code: int, operation: str) -> str:
    """Report the MMRESULT and Windows-provided explanation, never raw PCM."""
    details = ctypes.create_unicode_buffer(256)
    status = wave.waveInGetErrorTextW(code, details, len(details))
    message = details.value if status == 0 and details.value else "Unknown WinMM error"
    return f"{operation}: MMRESULT={code} ({message[:180]})"


def enumerate_input_devices(wave: object) -> tuple[InputDevice, ...]:
    """Enumerate *real OS API results*. No hard-coded fake microphone devices."""
    number = int(wave.waveInGetNumDevs())
    if number < 1:
        raise RealMicrophoneUnavailable(
            "WinMM reports no recording endpoints. Check Windows Settings > "
            "Privacy & security > Microphone and 'Let desktop apps access your microphone'."
        )
    if number > 128:
        raise RealMicrophoneUnavailable("Unusually large, untrusted device count")
    found: list[InputDevice] = []
    for device_id in range(number):
        caps = WAVEINCAPSW()
        code = int(wave.waveInGetDevCapsW(
            device_id, ctypes.byref(caps), ctypes.sizeof(caps),
        ))
        if code:
            # Keep a listed endpoint even when its driver cannot supply caps:
            # waveInOpen will report whether capture is actually available.
            found.append(InputDevice(device_id, f"WinMM device {device_id} (caps error {code})", 0))
        else:
            found.append(InputDevice(device_id, caps.szPname[:MAX_PNAME], int(caps.wChannels)))
    return tuple(found)


def _open_capture(
    wave: object, *, devices: tuple[InputDevice, ...], requested_device: int | None,
) -> tuple[ctypes.c_void_p, InputDevice, int, int]:
    """Try Windows mapper and explicit devices with bounded format negotiation."""
    if requested_device is not None and requested_device != WAVE_MAPPER:
        matches = [item for item in devices if item.device_id == requested_device]
        if not matches:
            raise RealMicrophoneUnavailable(
                f"Device {requested_device} not enumerated; use --list-devices"
            )
        candidates = matches
    else:
        candidates = [InputDevice(WAVE_MAPPER, "Windows default recording device", 0)]
        # After Windows' default mapper fails, retry actual WinMM devices,
        # including USB/Bluetooth/default endpoints and virtual devices.
        if requested_device is None:
            candidates.extend(devices)
    errors: list[str] = []
    for device in candidates:
        for rate, channels in FORMAT_CANDIDATES:
            if device.max_channels and channels > device.max_channels:
                continue
            wavefmt = WAVEFORMATEX(
                WAVE_FORMAT_PCM, channels, rate,
                rate * channels * 2, channels * 2, 16, 0,
            )
            handle = ctypes.c_void_p()
            code = int(wave.waveInOpen(
                ctypes.byref(handle), device.device_id,
                ctypes.byref(wavefmt), 0, 0, 0,
            ))
            if code == 0 and handle.value:
                return handle, device, rate, channels
            if code == 0 and not handle.value:
                errors.append(f"id={device.device_id} {rate}Hz/{channels}ch: empty handle")
            else:
                errors.append(
                    f"id={device.device_id} {rate}Hz/{channels}ch: "
                    + _error(wave, code, "waveInOpen")
                )
    detail = "; ".join(errors[:10])
    raise RealMicrophoneUnavailable(
        f"No endpoint accepted a PCM recording format. {detail}. "
        "Check microphone privacy permissions, Bluetooth headset profile, "
        "other apps using the microphone, and --list-devices."
    )


def _collect(
    wave: object, handle: ctypes.c_void_p, *,
    rate: int, channels: int, samples: int,
) -> tuple[list[float], int]:
    """Capture only completed real WinMM buffers; reset before freeing on error."""
    arrivals: list[float] = []
    audible = 0
    started = False
    frames = max(320, round(rate * 0.06))
    global_deadline = time.monotonic() + max(15, samples * 0.25)
    for _ in range(samples):
        raw = ctypes.create_string_buffer(frames * channels * 2)
        header = WAVEHDR(
            ctypes.cast(raw, ctypes.c_void_p),
            ctypes.sizeof(raw), 0, 0, 0, 0, None, 0,
        )
        header_size = ctypes.sizeof(header)
        prep = int(wave.waveInPrepareHeader(handle, ctypes.byref(header), header_size))
        if prep:
            raise RealMicrophoneUnavailable(_error(wave, prep, "waveInPrepareHeader"))
        try:
            begin = time.perf_counter_ns()
            added = int(wave.waveInAddBuffer(handle, ctypes.byref(header), header_size))
            if added:
                raise RealMicrophoneUnavailable(_error(wave, added, "waveInAddBuffer"))
            # Do not start an empty capture queue: WinMM drivers may refuse
            # waveInStart() with no prepared buffer.
            if not started:
                code = int(wave.waveInStart(handle))
                if code:
                    raise RealMicrophoneUnavailable(_error(wave, code, "waveInStart"))
                started = True
            while not header.dwFlags & WHDR_DONE:
                if time.monotonic() >= global_deadline:
                    raise RealMicrophoneUnavailable("waveIn capture timed out with device buffers in flight")
                time.sleep(0.002)
            elapsed = (time.perf_counter_ns() - begin) / 1_000_000
            if header.dwBytesRecorded != ctypes.sizeof(raw):
                raise RealMicrophoneUnavailable(
                    f"Incomplete waveIn frame: {header.dwBytesRecorded}/{ctypes.sizeof(raw)}"
                )
            pcm = array.array("h")
            pcm.frombytes(raw.raw)
            if max(abs(v) for v in pcm) >= 250:
                audible += 1
            arrivals.append(elapsed)
        finally:
            # A timed-out or failed queued header may still be owned by the
            # driver. Reset first; never unprepare/finalize a live buffer.
            if not header.dwFlags & WHDR_DONE:
                wave.waveInReset(handle)
            code = int(wave.waveInUnprepareHeader(handle, ctypes.byref(header), header_size))
            if code:
                wave.waveInReset(handle)
                again = int(wave.waveInUnprepareHeader(handle, ctypes.byref(header), header_size))
                if again:
                    raise RealMicrophoneUnavailable(_error(wave, again, "waveInUnprepareHeader"))
    return arrivals, audible


def capture_microphone(
    *, samples: int = 40, device_id: int | None = None,
    winmm: object | None = None,
) -> MicrophoneProbe:
    """Capture from actual WinMM unless an injected OS API test double is used.

    The injected API is for deterministic CI ABI tests only. It is never
    available from the operator CLI and never produces signed evidence.
    """
    if winmm is None and sys.platform != "win32":
        raise RealMicrophoneUnavailable("Native Windows microphone capture required")
    if not 30 <= samples <= 200:
        raise ValueError("Capture requires 30..200 bounded WinMM buffers")
    if device_id is not None and not 0 <= device_id <= 0xFFFFFFFF:
        raise ValueError("Invalid WinMM endpoint ID")
    wave = winmm if winmm is not None else ctypes.WinDLL("winmm", use_last_error=True)
    _configure_wave(wave)
    devices = enumerate_input_devices(wave)
    handle, selected, rate, channels = _open_capture(
        wave, devices=devices, requested_device=device_id,
    )
    try:
        print(
            f"Capturing real OS audio: id={selected.device_id} "
            f"({selected.name}), {rate}Hz/{channels}ch. Speak now.",
            file=sys.stderr,
        )
        arrivals, audible = _collect(
            wave, handle, rate=rate, channels=channels, samples=samples,
        )
        if len(arrivals) != samples:
            raise RealMicrophoneUnavailable("Missing completed WinMM capture buffers")
        if audible < max(2, samples // 10):
            raise RealMicrophoneUnavailable(
                "Recording buffers completed, but no audible signal detected. "
                "Speak closer to the selected microphone; check Windows input levels."
            )
        return MicrophoneProbe(
            sample_count=samples,
            buffer_p50_ms=percentile(arrivals, 0.5),
            buffer_p95_ms=percentile(arrivals, 0.95),
            buffer_max_ms=round(max(arrivals), 3),
            audible_buffers=audible,
            device_id=selected.device_id,
            device_name=selected.name,
            sample_rate_hz=rate,
            channels=channels,
        )
    finally:
        # Always drop pending buffers and close the captured device.
        wave.waveInStop(handle)
        wave.waveInReset(handle)
        wave.waveInClose(handle)


def list_microphones(*, winmm: object | None = None) -> tuple[InputDevice, ...]:
    if winmm is None and sys.platform != "win32":
        raise RealMicrophoneUnavailable("Windows microphone enumeration required")
    wave = winmm if winmm is not None else ctypes.WinDLL("winmm", use_last_error=True)
    _configure_wave(wave)
    return enumerate_input_devices(wave)


async def run(samples: int = 40, device_id: int | None = None) -> MicrophoneProbe:
    """Keep blocking Windows driver calls out of the event loop."""
    return await asyncio.to_thread(capture_microphone, samples=samples, device_id=device_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real Windows microphone diagnostic")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--device", type=int, default=None,
                        help="WinMM input ID from --list-devices; default tries mapper then endpoints")
    parser.add_argument("--list-devices", action="store_true",
                        help="Enumerate native WinMM input endpoints without recording")
    args = parser.parse_args(argv)
    try:
        if args.list_devices:
            devices = list_microphones()
            print(json.dumps({
                "native_winmm_enumeration": True,
                "hardware_verified": False,
                "devices": [item.public() for item in devices],
            }, indent=2))
            return 0
        report = asyncio.run(run(args.samples, args.device))
    except (RealMicrophoneUnavailable, OSError, ValueError) as exc:
        # Unlike the original probe, preserve the actionable native error.
        # No audio, secrets or signed evidence are exposed.
        print(json.dumps({
            "native_audio_capture_verified": False,
            "hardware_verified": False,
            "barge_in_verified": False,
            "error_type": type(exc).__name__,
            "diagnostic": str(exc)[:1500],
        }, indent=2))
        return 2
    print(json.dumps(report.public(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
