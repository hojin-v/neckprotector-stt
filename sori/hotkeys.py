from __future__ import annotations

import threading
import sys
from dataclasses import dataclass
from typing import Callable
from sori.keybindings import portable_key, windows_virtual_keys
from sori.realtime import INPUT_TAG


@dataclass
class HotkeyGesture:
    mode: str = "toggle"
    hold_ms: int = 250
    down_at: float | None = None
    started: bool = False

    def press(self, now: float) -> str | None:
        if self.down_at is not None:
            return None
        self.down_at = now
        if self.mode == "toggle":
            return "toggle"
        return None

    def tick(self, now: float) -> str | None:
        if self.mode == "hold" and self.down_at is not None and not self.started:
            if (now - self.down_at) * 1000 >= self.hold_ms:
                self.started = True
                return "start"
        return None

    def release(self) -> str | None:
        action = "stop" if self.mode == "hold" and self.started else None
        self.down_at = None
        self.started = False
        return action


class GlobalHotkey:
    def __init__(self, hotkey: str, event: Callable[[str], None], error: Callable[[str], None], activity=None):
        self.hotkey, self.event, self.error = hotkey, event, error
        self.listener = None
        self.pressed = set()
        self.active = False
        self.lock = threading.Lock()
        self.enabled = True
        self.activity = activity
        self.virtual_keys = windows_virtual_keys(hotkey)
        self.normalized = hotkey == "Ctrl+Alt+Space" or hotkey in {"Ctrl", "Alt", "Shift", "Meta"} or len(hotkey) == 1

    def start(self) -> None:
        try:
            from pynput import keyboard
            self.required = {keyboard.Key.ctrl, keyboard.Key.alt, keyboard.Key.space} if self.hotkey == "Ctrl+Alt+Space" else {portable_key(self.hotkey, keyboard)}
            options = {"win32_event_filter": self._windows_filter} if sys.platform == "win32" else {}
            self.listener = keyboard.Listener(on_press=self._press, on_release=self._release, **options)
            if self.normalized:
                self.required = {self.listener.canonical(key) for key in self.required}
            self.listener.start()
            # Wait off the UI thread; report backend/permission errors instead of hanging.
            def watch():
                try:
                    self.listener.wait()
                    self.listener.join()
                except Exception as exc:
                    self.error(f"전역 단축키를 사용할 수 없습니다: {exc}")
            threading.Thread(target=watch, daemon=True).start()
        except Exception as exc:
            self.error(f"전역 단축키를 사용할 수 없습니다: {exc}")

    def _key(self, key):
        return self.listener.canonical(key) if self.normalized else key

    def _windows_filter(self, message, data):
        # Handle the selected physical key ourselves BEFORE suppress_event raises.
        # Every other key is allowed through to Windows and the normal listener.
        if not self.enabled:
            return True
        if getattr(data, "dwExtraInfo", 0) == INPUT_TAG:
            return False
        if data.vkCode in self.virtual_keys:
            key = next(iter(self.required))
            if message in (0x0100, 0x0104):  # WM_KEYDOWN / WM_SYSKEYDOWN
                self._press(key)
            elif message in (0x0101, 0x0105):
                self._release(key)
            self.listener.suppress_event()
        elif self.activity and message in (0x0100, 0x0104):
            self.activity()
        return True

    def _press(self, key) -> None:
        if not self.enabled:
            return
        with self.lock:
            self.pressed.add(self._key(key))
            if not self.active and self.required <= self.pressed:
                self.active = True
                self.event("press")

    def _release(self, key) -> None:
        with self.lock:
            self.pressed.discard(self._key(key))
            if self.active and not self.required <= self.pressed:
                self.active = False
                self.event("release")

    def modifiers_released(self) -> bool:
        with self.lock:
            return not self.pressed

    def stop(self) -> None:
        self.enabled = False
        if self.listener:
            self.listener.stop()
