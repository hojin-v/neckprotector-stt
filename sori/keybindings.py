"""Portable single-key names and Windows physical-key identifiers."""
import re

DEFAULT_HOTKEY = "CapsLock"

# name: (pynput Key attribute, Windows virtual keys)
SPECIAL_KEYS = {
    "CapsLock": ("caps_lock", (0x14,)),
    "ScrollLock": ("scroll_lock", (0x91,)),
    "Pause": ("pause", (0x13,)),
    "Insert": ("insert", (0x2D,)),
    "Menu": ("menu", (0x5D,)),
    "NumLock": ("num_lock", (0x90,)),
    "Space": ("space", (0x20,)),
    "Tab": ("tab", (0x09,)),
    "Enter": ("enter", (0x0D,)),
    "Escape": ("esc", (0x1B,)),
    "Backspace": ("backspace", (0x08,)),
    "Delete": ("delete", (0x2E,)),
    "Home": ("home", (0x24,)),
    "End": ("end", (0x23,)),
    "PageUp": ("page_up", (0x21,)),
    "PageDown": ("page_down", (0x22,)),
    "Up": ("up", (0x26,)),
    "Down": ("down", (0x28,)),
    "Left": ("left", (0x25,)),
    "Right": ("right", (0x27,)),
    "Ctrl": ("ctrl", (0x11, 0xA2, 0xA3)),
    "Alt": ("alt", (0x12, 0xA4, 0xA5)),
    "Shift": ("shift", (0x10, 0xA0, 0xA1)),
    "Meta": ("cmd", (0x5B, 0x5C)),
    "Right Ctrl": ("ctrl_r", (0xA3,)),
    "Right Alt": ("alt_r", (0xA5,)),
    "Right Shift": ("shift_r", (0xA1,)),
    "Right Meta": ("cmd_r", (0x5C,)),
}


def valid_hotkey(name: str) -> bool:
    if not isinstance(name, str):
        return False
    return bool(name in SPECIAL_KEYS or name == "Ctrl+Alt+Space" or
                re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", name) or
                re.fullmatch(r"[A-Z0-9]", name) or
                re.fullmatch(r"VK:(?:[1-9][0-9]?|1[0-9]{2}|2[0-4][0-9]|25[0-4])", name))


def windows_virtual_keys(name: str) -> tuple[int, ...]:
    if name in SPECIAL_KEYS:
        return SPECIAL_KEYS[name][1]
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", name):
        return (0x70 + int(name[1:]) - 1,)
    if re.fullmatch(r"[A-Z0-9]", name):
        return (ord(name),)
    if name.startswith("VK:") and valid_hotkey(name):
        return (int(name[3:]),)
    return ()


def hotkey_label(name: str) -> str:
    if name.startswith("VK:"):
        return f"사용자 키 · 0x{int(name[3:]):02X}"
    return name


def portable_key(name: str, keyboard):
    if name in SPECIAL_KEYS:
        return getattr(keyboard.Key, SPECIAL_KEYS[name][0])
    if name.startswith("F"):
        return getattr(keyboard.Key, name.lower())
    if name.startswith("VK:"):
        return keyboard.KeyCode.from_vk(int(name[3:]))
    return keyboard.KeyCode.from_char(name.lower())
