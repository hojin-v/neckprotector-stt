import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np

from sori.audio import SpeechBuffer
from sori.realtime import INPUT_TAG
from sori.hotkeys import HotkeyGesture, GlobalHotkey
from sori.keybindings import valid_hotkey, windows_virtual_keys
from sori.storage import HistoryStore, Settings


class HotkeyTests(unittest.TestCase):
    def test_new_default_and_custom_single_keys_survive_settings(self):
        self.assertEqual(Settings().hotkey, "CapsLock")
        with tempfile.TemporaryDirectory() as path:
            for key in ("CapsLock", "ScrollLock", "F13", "F24", "Right Ctrl", "A", "5", "VK:186", "Ctrl+Alt+Space"):
                settings = Settings(hotkey=key)
                settings.save(Path(path))
                self.assertEqual(Settings.load(Path(path)).hotkey, key)
        for key in ("", "F0", "F25", "VK:0", "VK:255", "Win+H", "invalid", None):
            self.assertFalse(valid_hotkey(key))

    def test_windows_physical_key_mapping(self):
        self.assertEqual(windows_virtual_keys("CapsLock"), (0x14,))
        self.assertEqual(windows_virtual_keys("F13"), (0x7C,))
        self.assertEqual(windows_virtual_keys("A"), (0x41,))
        self.assertEqual(windows_virtual_keys("VK:186"), (0xBA,))

    def test_windows_selected_key_is_consumed_but_other_keys_pass(self):
        class Suppressed(Exception):
            pass
        class Listener:
            def suppress_event(self):
                raise Suppressed()
        events = []
        hook = GlobalHotkey("CapsLock", events.append, self.fail)
        hook.listener = Listener()
        hook.required = {"caps"}
        physical = SimpleNamespace(vkCode=0x14, flags=0)
        for message in (0x0100, 0x0100, 0x0101):
            with self.assertRaises(Suppressed):
                hook._windows_filter(message, physical)
        self.assertEqual(events, ["press", "release"])
        self.assertTrue(hook.modifiers_released())
        self.assertTrue(hook._windows_filter(0x0100, SimpleNamespace(vkCode=0x41, flags=0)))
        self.assertEqual(events, ["press", "release"])
        self.assertFalse(hook._windows_filter(0x0100, SimpleNamespace(vkCode=0x14, flags=0x10, dwExtraInfo=INPUT_TAG)))
        # A remapping program's injected key must reach dictation.
        for message in (0x0100, 0x0101):
            with self.assertRaises(Suppressed):
                hook._windows_filter(message, SimpleNamespace(vkCode=0x14, flags=0x10, dwExtraInfo=0))
        self.assertEqual(events, ["press", "release", "press", "release"])
        hook.enabled = False
        self.assertTrue(hook._windows_filter(0x0100, physical))
        self.assertEqual(events, ["press", "release", "press", "release"])

    def test_toggle_ignores_repeat_until_release(self):
        key = HotkeyGesture()
        self.assertEqual(key.press(1), "toggle")
        self.assertIsNone(key.press(1.2))
        self.assertIsNone(key.release())
        self.assertEqual(key.press(2), "toggle")

    def test_hold_ignores_short_tap_and_stops_on_release(self):
        key = HotkeyGesture(mode="hold", hold_ms=250)
        self.assertIsNone(key.press(1))
        self.assertIsNone(key.tick(1.1))
        self.assertIsNone(key.release())
        key.press(2)
        self.assertEqual(key.tick(2.3), "start")
        self.assertIsNone(key.tick(2.5))
        self.assertIsNone(key.press(2.6))
        self.assertEqual(key.release(), "stop")
        self.assertIsNone(key.release())


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = HistoryStore(self.path)
        local = datetime.now().astimezone().tzinfo
        self.time = datetime(2026, 10, 8, 23, 59, 59, tzinfo=local)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def add(self, text, stamp=None, session="one"):
        return self.store.add(text, stamp or self.time, session, 2.5, "Korean", "메모장")

    def test_midnight_and_unicode_exports(self):
        first = self.add("첫 문장: 한글 👋\n다음 줄도 유지")
        self.add("다음 날 문장", self.time + timedelta(seconds=3))
        self.store.export_all()
        self.assertEqual(self.store.days(), ["2026-10-09", "2026-10-08"])
        prior = self.store.archive / "2026-10-08.md"
        self.assertIn("23:59:59", prior.read_text(encoding="utf-8"))
        self.assertNotIn("다음 날 문장", prior.read_text(encoding="utf-8"))
        row = json.loads((self.store.archive / "2026-10-08.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(row["text"], first["text"])
        self.assertEqual(row["session"], "one")

    def test_failed_export_does_not_lose_committed_text(self):
        self.add("복구할 내용")
        with patch("sori.storage.atomic_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.store.export_all()
        self.assertEqual(len(self.store.entries()), 1)
        self.store.close()
        self.store = HistoryStore(self.path)
        self.assertIn("복구할 내용", (self.store.archive / "2026-10-08.md").read_text(encoding="utf-8"))

    def test_existing_store_starts_when_archive_is_unavailable(self):
        self.add("기존 데이터")
        self.store.close()
        blocker = self.path / "not-a-folder"
        blocker.write_text("x")
        self.store = HistoryStore(self.path, str(blocker / "archive"))
        self.assertTrue(self.store.export_error)
        self.assertEqual(self.store.entries()[0]["text"], "기존 데이터")

    def test_clipboard_accumulates_every_entry_without_duplicates(self):
        self.add("첫 번째")
        self.add("두 번째", self.time, "two")
        self.assertEqual(self.store.clipboard_text("2026-10-08", "두 번째", "today"), "첫 번째\n두 번째")
        self.assertEqual(self.store.clipboard_text("2026-10-08", "두 번째", "latest"), "두 번째")

    def test_search_is_literal_and_empty_text_rejected(self):
        self.add("100% 완료")
        self.add("일반 문장")
        self.assertEqual(len(self.store.entries(search="%")), 1)
        with self.assertRaises(ValueError):
            self.add(" \n ")

    def test_settings_roundtrip_and_corruption_fallback(self):
        settings = Settings(mode="hold", hotkey="F9", auto_paste=False)
        settings.save(self.path)
        self.assertEqual(Settings.load(self.path), settings)
        (self.path / "settings.json").write_text('{"mode":"unknown"}')
        self.assertEqual(Settings.load(self.path), Settings())


class AudioTests(unittest.TestCase):
    def test_silence_is_bounded_and_never_transcribed(self):
        buffer = SpeechBuffer(16000)
        for _ in range(400):
            self.assertIsNone(buffer.feed(np.zeros(800, dtype=np.float32)))
        self.assertLessEqual(buffer.samples, 6400)
        self.assertIsNone(buffer.flush())

    def test_speech_pause_flush_keeps_boundary_and_no_repeated_audio(self):
        buffer = SpeechBuffer(16000)
        self.assertIsNone(buffer.feed(np.zeros(4000, dtype=np.float32)))
        self.assertIsNone(buffer.feed(np.full(8000, 0.1, dtype=np.float32)))
        chunk, offset = buffer.feed(np.zeros(14400, dtype=np.float32))
        self.assertEqual(len(chunk), 26400)
        self.assertEqual(offset, 0)
        self.assertEqual(np.count_nonzero(chunk), 8000)
        self.assertIsNone(buffer.flush())

    def test_stop_flushes_short_speech(self):
        buffer = SpeechBuffer(16000)
        buffer.feed(np.full(4800, 0.02, dtype=np.float32))
        chunk, _ = buffer.flush()
        self.assertEqual(len(chunk), 4800)

    def test_long_speech_is_bounded_without_dropping_samples(self):
        buffer = SpeechBuffer(16000)
        collected = []
        for _ in range(600):
            result = buffer.feed(np.full(800, 0.02, dtype=np.float32))
            if result:
                collected.append(result[0])
        tail = buffer.flush()
        if tail:
            collected.append(tail[0])
        self.assertEqual(sum(map(len, collected)), 480000)
        self.assertLessEqual(max(map(len, collected)), 16000 * 18)


if __name__ == "__main__":
    unittest.main()
