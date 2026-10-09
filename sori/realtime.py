"""Bounded inference queue and draft edits shared by the desktop and audio tests."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import regex

# Identifies only Sori's own SendInput events; remapping tools remain eligible hotkeys.
INPUT_TAG = 0x534F5249


@dataclass
class Draft:
    text: str = ""

    def change(self, text: str) -> tuple[int, str]:
        common = 0
        old, new = regex.findall(r"\X", self.text), regex.findall(r"\X", text)
        for left, right in zip(old, new):
            if left != right:
                break
            common += 1
        remove, suffix = len(old) - common, "".join(new[common:])
        self.text = text
        return remove, suffix


class InferenceQueue:
    """Keep final segments in order; replace stale previews instead of accumulating them."""
    def __init__(self):
        self.finals = deque()
        self.preview = None
        self.busy = False

    def add(self, request):
        if request["final"]:
            self.finals.append(request)
            if self.preview and self.preview["segment"] == request["segment"]:
                self.preview = None
        elif not any(item["segment"] == request["segment"] for item in self.finals):
            self.preview = request

    def next(self):
        if self.busy:
            return None
        request = self.finals.popleft() if self.finals else self.preview
        if request is self.preview:
            self.preview = None
        self.busy = request is not None
        return request

    def finished(self):
        self.busy = False

    def __bool__(self):
        return self.busy or bool(self.finals) or self.preview is not None
