"""Explicitly enabled Windows GUI driver (no external Python packages).

The caller must traverse the MCP Gateway's consumed interactive approval before
this driver is invoked. This module never grants capabilities or approvals.
"""
from __future__ import annotations

import asyncio
import ctypes
import sys
from threading import RLock
from ctypes import wintypes


_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _PTR)]


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", _PTR)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _InputData(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyboardInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", _InputData)]


class WindowsDesktopInputDriver:
    """Dispatch bounded SendInput actions to the active Windows desktop."""

    _KEYS = {"enter": 0x0D, "tab": 0x09, "escape": 0x1B,
             "backspace": 0x08, "space": 0x20, "up": 0x26,
             "down": 0x28, "left": 0x25, "right": 0x27}

    def __init__(self, *, user32=None):
        if sys.platform != "win32" and user32 is None:
            raise RuntimeError("Screen input requires an interactive Windows desktop")
        self._user32 = user32 if user32 is not None else ctypes.windll.user32
        self._lock = RLock()

    def _send(self, event):
        if self._user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input)) != 1:
            raise OSError("Windows SendInput could not dispatch the action")

    def _mouse(self, flags):
        self._send(_Input(0, _InputData(mi=_MouseInput(0, 0, 0, flags, 0, 0))))

    def _key(self, virtual, scan, flags):
        self._send(_Input(1, _InputData(ki=_KeyboardInput(virtual, scan, flags, 0, 0))))

    def _click(self, x, y):
        with self._lock:
            width, height = self._user32.GetSystemMetrics(0), self._user32.GetSystemMetrics(1)
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError("Click coordinates outside the primary screen")
            if self._user32.SetCursorPos(x, y) == 0:
                raise OSError("Windows could not position the cursor")
            self._mouse(0x0002)
            self._mouse(0x0004)

    async def click(self, x, y):
        if type(x) is not int or type(y) is not int:
            raise ValueError("Screen coordinates must be integers")
        await asyncio.to_thread(self._click, x, y)

    def _type_text(self, value):
        with self._lock:
            # SendInput KEYEVENTF_UNICODE works with UTF-16 code units.
            encoded = value.encode("utf-16-le")
            for i in range(0, len(encoded), 2):
                unit = encoded[i] | (encoded[i + 1] << 8)
                self._key(0, unit, 0x0004)
                self._key(0, unit, 0x0004 | 0x0002)

    async def type_text(self, value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 1000
                or any(c in value for c in "\x00\r\n\t")):
            raise ValueError("Invalid text for keyboard input")
        await asyncio.to_thread(self._type_text, value)

    def _press_key(self, code):
        with self._lock:
            self._key(code, 0, 0)
            self._key(code, 0, 0x0002)

    async def press_key(self, key):
        code = self._KEYS.get(key) if isinstance(key, str) else None
        if code is None:
            raise ValueError("Key not in the bounded allowlist")
        await asyncio.to_thread(self._press_key, code)


class DesktopVLMAdapter:
    """Combine provider-agnostic screen capture and injected VLM description."""

    def __init__(self, capture, describer):
        self._capture = capture
        self._describer = describer

    async def capture(self):
        return await self._capture.capture()

    async def describe(self, image, *, prompt):
        return await self._describer.describe(image, prompt=prompt)
