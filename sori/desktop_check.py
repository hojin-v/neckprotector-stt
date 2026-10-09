"""Opt-in Windows end-to-end check using an owned editor and public audio only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path


def run_target(state: Path, command: Path):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QPlainTextEdit
    from sori.ui import configure_appearance
    app = QApplication([])
    configure_appearance(app)
    editor = QPlainTextEdit()
    editor.setWindowTitle("Sori — 자동 입력 검증 전용 창")
    editor.resize(640, 300)
    editor.show()
    editor.activateWindow()
    editor.setFocus()
    def publish():
        state.write_text(json.dumps({"pid": os.getpid(), "hwnd": str(int(editor.winId())),
                                    "text": editor.toPlainText()}, ensure_ascii=False), encoding="utf-8")
    editor.textChanged.connect(publish)
    seen = ""
    def poll():
        nonlocal seen
        if command.exists():
            value = command.read_text(encoding="utf-8")
            if value != seen:
                seen = value
                request = json.loads(value)
                if request.get("quit"):
                    app.quit()
                elif "text" in request:
                    editor.setPlainText(request["text"])
                    publish()
        publish()
    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(80)
    QTimer.singleShot(200, publish)
    result = app.exec()
    editor.close()
    return result


def run(report: Path, sample: Path | None = None, cache: Path | None = None):
    if sys.platform != "win32":
        report.write_text('{"ok":false,"error":"Windows only"}', encoding="utf-8")
        return 1
    from PySide6.QtCore import QMimeData
    from PySide6.QtWidgets import QApplication
    from pynput import keyboard
    from sori.app import Controller
    from sori.audio import SpeechBuffer
    from sori.engine import QwenEngine
    from sori.platform_input import DesktopInput
    from sori.storage import data_directory
    from sori.ui import configure_appearance
    app = QApplication.instance() or QApplication([])
    configure_appearance(app)
    backup = QMimeData()
    clipboard = app.clipboard().mimeData()
    if clipboard:
        for fmt in clipboard.formats():
            backup.setData(fmt, clipboard.data(fmt))
    result = {"frozen": bool(getattr(sys, "frozen", False))}
    controller = child = None
    with tempfile.TemporaryDirectory(prefix="sori-input-check-") as directory:
        directory = Path(directory)
        state, command = directory / "editor.json", directory / "command.json"
        try:
            controller = Controller(app, directory / "data", demo=True)
            controller.dashboard.hide()
            controller.panel.hide()
            controller.store.db.execute("DELETE FROM entries")
            controller.store.db.commit()
            controller.desktop = DesktopInput()
            controller.settings.hotkey = "F24"
            controller.setup_hotkey()
            original_save = controller.save_transcript
            saved = []
            def save(metadata, stream=False):
                entry = original_save(metadata, stream=stream)
                if entry:
                    saved.append(entry)
                return entry
            controller.save_transcript = save
            if sample:
                import librosa
                engine = QwenEngine(cache or data_directory() / "models", "cpu")
                engine.load()
                controller.engine = engine
                controller.settings.language = "English"
                samples, _ = librosa.load(sample, sr=16000, mono=True)
            launch = [sys.executable] if result["frozen"] else [sys.executable, "-m", "sori"]
            child = subprocess.Popen(launch + ["--input-target", str(state), "--input-command", str(command)])
            keys = keyboard.Controller()
            def spin(seconds=0.1):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    app.processEvents()
                    time.sleep(0.01)
            def read():
                try:
                    return json.loads(state.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return {}
            def wait(predicate, timeout=8):
                until = time.monotonic() + timeout
                while time.monotonic() < until:
                    spin()
                    if predicate():
                        return
                raise AssertionError("Desktop check timed out")
            wait(lambda: read().get("hwnd") is not None)
            # A process launched from a background terminal may not inherit foreground
            # permission. Activate only our newly created, PID-checked editor.
            import ctypes
            from ctypes import wintypes
            user32 = controller.desktop.user32
            destination = int(read()["hwnd"])
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(destination, ctypes.byref(owner))
            # uv's Windows python.exe redirector can spawn a different actual Python PID.
            if owner.value != read()["pid"]:
                raise RuntimeError(f"Invalid owned editor handle: hwnd={destination}, owner={owner.value}, published={read()['pid']}, launcher={child.pid}")
            foreground = user32.GetForegroundWindow()
            foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
            own_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            attached = bool(user32.AttachThreadInput(own_thread, foreground_thread, True)) if foreground_thread else False
            try:
                user32.SetForegroundWindow(destination)
            finally:
                if attached:
                    user32.AttachThreadInput(own_thread, foreground_thread, False)
            wait(lambda: controller.desktop.target().token == read()["hwnd"])
            def safe():
                current = controller.desktop.target()
                if current.token != read()["hwnd"]:
                    raise RuntimeError(f"Focus left the owned test window: token={current.token}, title={current.title!r}, owned={read()['hwnd']}; input check aborted")
            def tap():
                if controller.desktop.target().token != read()["hwnd"]:
                    # Switching test phases can return focus to the invoking terminal.
                    # Re-activate only our PID-verified child before synthesizing a key.
                    current = user32.GetForegroundWindow()
                    thread = user32.GetWindowThreadProcessId(current, None)
                    attached = bool(user32.AttachThreadInput(own_thread, thread, True)) if thread else False
                    try:
                        user32.SetForegroundWindow(destination)
                    finally:
                        if attached:
                            user32.AttachThreadInput(own_thread, thread, False)
                    spin(0.15)
                safe()
                keys.press(keyboard.Key.f24)
                keys.release(keyboard.Key.f24)
                spin(0.35)
            def update(text, final=False):
                safe()
                if final:
                    controller.pending += 1
                controller.accept_transcript({"text": text, "final": final, "stream": True,
                    "segment": controller.session + ":test", "queued_at": time.monotonic(),
                    "duration": 1.0, "timestamp": datetime.now().astimezone(), "session": controller.session,
                    "language": "Korean", "target": controller.target, "auto_paste": True})
                spin(0.4)
            tap()
            result["mapped_key_started"] = controller.recording
            assert controller.recording
            result["panel_kept_focus"] = controller.desktop.unchanged(controller.target)
            assert result["panel_kept_focus"]
            update("입력 테스x")
            wait(lambda: read().get("text") == "입력 테스x")
            update("입력 테스트")
            wait(lambda: read().get("text") == "입력 테스트")
            result["draft_revision"] = True
            update("입력 테스트 👋", final=True)
            wait(lambda: read().get("text") == "입력 테스트 👋 ")
            result["text_while_recording"] = controller.recording
            tap()
            result["mapped_key_stopped"] = not controller.recording
            wait(lambda: not controller.panel.isVisible())
            result["auto_hide"] = True
            result["clipboard_cumulative"] = app.clipboard().text() == "입력 테스트 👋"
            controller.export_pending()
            controller.archiver.submit(lambda: None).result(timeout=5)
            result["archive_written"] = bool(list(controller.store.archive.glob("*.md")))
            # Hold mode must deliver while the designated key is still down.
            command.write_text(json.dumps({"text": "", "revision": 1}), encoding="utf-8")
            wait(lambda: read().get("text") == "")
            controller.settings.mode = "hold"
            controller.setup_hotkey()
            spin(0.2)
            safe()
            keys.press(keyboard.Key.f24)
            spin(0.4)
            assert controller.recording
            update("누른 동안 입력", final=True)
            wait(lambda: read().get("text") == "누른 동안 입력 ")
            result["hold_delivers_before_release"] = controller.recording
            keys.release(keyboard.Key.f24)
            spin(0.2)
            assert not controller.recording
            if sample:
                command.write_text(json.dumps({"text": "", "revision": 2}), encoding="utf-8")
                wait(lambda: read().get("text") == "")
                controller.settings.mode = "toggle"
                controller.setup_hotkey()
                saved.clear()
                tap()
                beginning = time.monotonic()
                buffer = SpeechBuffer(16000)
                first_text = None
                for start in range(0, len(samples), 800):
                    safe()
                    final = buffer.feed(samples[start:start + 800])
                    if final:
                        controller.transcribe_chunk(*final)
                    else:
                        preview = buffer.preview()
                        if preview:
                            controller.transcribe_preview(*preview)
                    spin(max(0, (start + 800) / 16000 - (time.monotonic() - beginning)))
                    if first_text is None and read().get("text"):
                        first_text = time.monotonic() - beginning
                final = buffer.flush()
                if final:
                    controller.transcribe_chunk(*final)
                result["public_audio_first_text_seconds"] = round(first_text, 3) if first_text else None
                result["public_audio_typed_before_stop"] = first_text is not None
                tap()
                wait(lambda: not controller.pending and not controller.inference_queue and not controller.delivery_active and not controller.live_updates, timeout=90)
                expected = "".join(entry["text"] + " " for entry in saved)
                result["public_audio_final_matches_records"] = read().get("text") == expected
                result["public_audio_records"] = len(saved)
                assert result["public_audio_typed_before_stop"] and result["public_audio_final_matches_records"]
            assert all(result[name] for name in ("mapped_key_started", "panel_kept_focus", "draft_revision",
                "text_while_recording", "mapped_key_stopped", "auto_hide", "clipboard_cumulative",
                "archive_written", "hold_delivers_before_release"))
            result["ok"] = True
        except Exception:
            result["ok"] = False
            result["error"] = traceback.format_exc()
        finally:
            if controller:
                controller.hotkey.stop()
                controller.stop()
                # Drain any submitted inference before closing the isolated database.
                until = time.monotonic() + 90
                while controller.inference_queue and time.monotonic() < until:
                    app.processEvents()
                    time.sleep(0.02)
                controller.cleanup()
                controller.dashboard.hide()
                controller.panel.hide()
                app.aboutToQuit.disconnect(controller.cleanup)
            if child:
                command.write_text('{"quit":true}', encoding="utf-8")
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=5)
            app.clipboard().setMimeData(backup)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
