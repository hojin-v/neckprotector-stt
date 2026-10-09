from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from sori.realtime import INPUT_TAG


@dataclass(frozen=True)
class InputTarget:
    token: str = ""
    title: str = "입력창"
    external: bool = False


class DesktopInput:
    def __init__(self):
        self.display = None
        self.controller = None
        self.last_external = InputTarget()
        if sys.platform == "win32":
            from ctypes import wintypes
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.user32.GetForegroundWindow.restype = wintypes.HWND
            self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            self.user32.GetForegroundWindow.argtypes = []
            self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        elif sys.platform.startswith("linux"):
            try:
                from Xlib.display import Display
                self.display = Display()
            except Exception:
                pass

    def target(self) -> InputTarget:
        try:
            if sys.platform == "win32":
                from ctypes import wintypes
                hwnd = self.user32.GetForegroundWindow()
                pid = wintypes.DWORD()
                self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                title = ctypes.create_unicode_buffer(self.user32.GetWindowTextLengthW(hwnd) + 1)
                self.user32.GetWindowTextW(hwnd, title, len(title))
                if not hwnd or not pid.value:
                    return InputTarget()
                result = InputTarget(str(hwnd), title.value or "입력창", pid.value != os.getpid())
                if result.external:
                    self.last_external = result
                return result
            if sys.platform == "darwin":
                from AppKit import NSWorkspace
                application = NSWorkspace.sharedWorkspace().frontmostApplication()
                pid = application.processIdentifier()
                return InputTarget(str(pid), application.localizedName(), pid != os.getpid())
            if self.display:
                root = self.display.screen().root
                active = root.get_full_property(self.display.intern_atom("_NET_ACTIVE_WINDOW"), 0)
                focused = self.display.get_input_focus().focus
                window = self.display.create_resource_object("window", int(active.value[0])) if active is not None else focused
                pid = window.get_full_property(self.display.intern_atom("_NET_WM_PID"), 0)
                external = pid is not None and int(pid.value[0]) != os.getpid()
                title = window.get_wm_name() or "입력창"
                # Child focus distinguishes separate controls within the same X11 window.
                return InputTarget(f"{window.id}:{getattr(focused, 'id', focused)}", str(title), external)
        except Exception:
            pass
        return InputTarget()

    def recording_target(self):
        target = self.target()
        return target if target.external else self.last_external

    def unchanged(self, target: InputTarget) -> bool:
        return bool(target.external and target.token and self.target().token == target.token)

    def windows_type(self, text: str, backspaces: int = 0, paste: bool = False) -> None:
        """Unicode SendInput preserves the cumulative clipboard, including Korean/emoji."""
        from ctypes import wintypes

        class KeyboardInput(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        class MouseInput(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class HardwareInput(ctypes.Structure):
            _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

        class InputUnion(ctypes.Union):
            _fields_ = [("ki", KeyboardInput), ("mi", MouseInput), ("hi", HardwareInput)]

        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]

        encoded = text.encode("utf-16-le")
        events = []
        for _ in range(backspaces):
            for flags in (0, 0x0002):
                events.append(Input(1, InputUnion(ki=KeyboardInput(0x08, 0, flags, 0, INPUT_TAG))))
        for pos in range(0, len(encoded) if not paste else 0, 2):
            unit = int.from_bytes(encoded[pos:pos + 2], "little")
            for flags in (0x0004, 0x0004 | 0x0002):
                events.append(Input(1, InputUnion(ki=KeyboardInput(0, unit, flags, 0, INPUT_TAG))))
        if paste and text:
            for vk, flags in ((0x11, 0), (0x56, 0), (0x56, 0x0002), (0x11, 0x0002)):
                events.append(Input(1, InputUnion(ki=KeyboardInput(vk, 0, flags, 0, INPUT_TAG))))
        if not events:
            return
        array = (Input * len(events))(*events)
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        sent = self.user32.SendInput(len(array), array, ctypes.sizeof(Input))
        if sent != len(array):
            raise RuntimeError("입력 전달이 중단됐습니다. 관리자 권한으로 실행된 앱인지 확인해 주세요.")

    def safe_to_type(self):
        if sys.platform != "win32":
            return True
        return not any(self.user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))

    def own_window_at(self, x, y):
        if sys.platform != "win32":
            return False
        from ctypes import wintypes
        self.user32.WindowFromPoint.argtypes = [wintypes.POINT]
        self.user32.WindowFromPoint.restype = wintypes.HWND
        hwnd = self.user32.WindowFromPoint(wintypes.POINT(round(x), round(y)))
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return bool(hwnd and pid.value == os.getpid())

    def paste_shortcut(self) -> None:
        from pynput.keyboard import Controller, Key
        if self.controller is None:
            self.controller = Controller()
        with self.controller.pressed(Key.cmd if sys.platform == "darwin" else Key.ctrl):
            self.controller.press("v")
            self.controller.release("v")

    def close(self):
        if self.display:
            self.display.close()


def platform_note() -> str:
    if sys.platform.startswith("linux") and "microsoft" in os.uname().release.lower():
        return "WSL에서는 Windows 앱의 단축키·입력을 제어할 수 없습니다. Windows에서 Sori.exe를 실행하세요."
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland에서는 전역 단축키와 자동 입력이 XWayland 앱에서만 동작할 수 있습니다. 전체 앱 지원에는 X11 세션을 사용하세요."
    if sys.platform == "darwin":
        return "macOS: 시스템 설정에서 마이크·손쉬운 사용·입력 모니터링 권한을 허용해 주세요."
    return ""
