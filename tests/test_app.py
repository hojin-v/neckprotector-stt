import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import Qt
from sori.app import Controller
from sori.platform_input import InputTarget
from sori.ui import SingleKeyPicker, SettingsDialog
from sori.storage import Settings


class FakeDesktop:
    def __init__(self):
        self.same = False
        self.pasted = False

    def unchanged(self, target):
        return self.same

    def paste_shortcut(self):
        self.pasted = True

    def close(self):
        pass


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.controller = Controller(self.app, Path(self.temp.name), demo=True)
        self.controller.store.db.execute("DELETE FROM entries")
        self.controller.store.db.commit()
        self.controller.desktop = FakeDesktop()

    def tearDown(self):
        self.controller.dashboard.hide()
        self.controller.panel.hide()
        self.controller.cleanup()
        self.controller.application.aboutToQuit.disconnect(self.controller.cleanup)
        self.controller.panel.deleteLater()
        self.controller.dashboard.deleteLater()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def transcript(self, text, timestamp=None, paste=False):
        self.controller.pending += 1
        self.controller.accept_transcript({
            "text": text, "timestamp": timestamp or datetime.now().astimezone(),
            "session": "sample-session", "duration": 1.5, "language": "Korean",
            "target": InputTarget("external-1", "메모장", True), "auto_paste": paste,
        })

    def test_recognized_text_reaches_clipboard_and_both_archives(self):
        self.transcript("처음 문장")
        self.transcript("다음 문장")
        self.controller.export_pending()
        self.controller.archiver.submit(lambda: None).result(timeout=5)
        day = datetime.now().astimezone().date().isoformat()
        self.assertEqual(self.app.clipboard().text(), "처음 문장\n다음 문장")
        self.assertEqual(len(self.controller.store.entries(day)), 2)
        self.assertTrue((self.controller.store.archive / (day + ".md")).exists())
        self.assertTrue((self.controller.store.archive / (day + ".jsonl")).exists())
        self.assertEqual(self.controller.pending, 0)

    def test_changed_focus_preserves_text_without_pasting(self):
        self.transcript("다른 창으로 이동해도 보관", paste=True)
        self.assertFalse(self.controller.desktop.pasted)
        self.assertFalse(self.controller.delivery_queue)
        self.assertIn("입력창이 바뀌어", self.controller.dashboard.footer.text())
        self.assertIn("다른 창으로 이동해도 보관", self.app.clipboard().text())

    def test_late_result_is_archived_on_recording_date(self):
        now = datetime.now().astimezone()
        yesterday = now - timedelta(days=1)
        self.transcript("어제 녹음한 문장", yesterday)
        self.controller.export_pending()
        self.controller.archiver.submit(lambda: None).result(timeout=5)
        self.assertEqual(self.controller.store.entries()[0]["day"], yesterday.date().isoformat())
        self.assertTrue((self.controller.store.archive / f"{yesterday.date()}.md").exists())
        self.assertEqual(self.app.clipboard().text(), "어제 녹음한 문장")

    def test_failed_inference_finishes_pending_and_reports_error(self):
        self.controller.pending = 1
        self.controller.accept_transcript({"error": "test inference error"})
        self.assertEqual(self.controller.pending, 0)
        self.assertEqual(self.controller.store.entries(), [])
        self.assertIn("test inference error", self.controller.dashboard.footer.text())

    def test_capture_function_key_updates_saved_settings(self):
        dialog = SettingsDialog(Settings(), [])
        try:
            event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F13, Qt.KeyboardModifier.NoModifier)
            dialog.hotkey.capturing = True
            dialog.hotkey.keyPressEvent(event)
            settings = Settings()
            dialog.update_settings(settings)
            self.assertEqual(settings.hotkey, "F13")
            self.assertFalse(dialog.hotkey.capturing)
            self.assertIn("F13", dialog.hotkey.text())
        finally:
            dialog.deleteLater()

    def test_escape_cancels_capture_and_repeat_does_not_change_key(self):
        picker = SingleKeyPicker("CapsLock")
        try:
            picker.capturing = True
            repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a", True)
            picker.keyPressEvent(repeat)
            self.assertEqual(picker.key_name, "CapsLock")
            self.assertTrue(picker.capturing)
            escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            picker.keyPressEvent(escape)
            self.assertEqual(picker.key_name, "CapsLock")
            self.assertFalse(picker.capturing)
        finally:
            picker.deleteLater()


if __name__ == "__main__":
    unittest.main()
