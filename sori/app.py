from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
import uuid
import hashlib
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer, QUrl, QLockFile
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QDialog, QMessageBox
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from sori.audio import Microphone
from sori.engine import QwenEngine
from sori.hotkeys import GlobalHotkey, HotkeyGesture
from sori.keybindings import hotkey_label
from sori.platform_input import DesktopInput, InputTarget, platform_note
from sori.storage import Settings, HistoryStore, data_directory, atomic_write
from sori.realtime import Draft, InferenceQueue
from sori.ui import Dashboard, FloatingPanel, SettingsDialog, icon, configure_appearance


class Bridge(QObject):
    key = Signal(str)
    model_loaded = Signal(str)
    model_failed = Signal(str)
    transcript = Signal(object)
    notice = Signal(str)
    activity = Signal(object)


class Controller(QObject):
    def __init__(self, application, directory: Path, demo=False, compact=False, background=True):
        super().__init__()
        self.application, self.directory, self.demo = application, directory, demo
        self.settings = Settings.load(directory)
        self.store = HistoryStore(directory, self.settings.archive_directory)
        self.dashboard, self.panel = Dashboard(), FloatingPanel()
        self.desktop = DesktopInput() if not demo else None
        self.microphone, self.bridge = Microphone(), Bridge()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sori-asr")
        self.archiver = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sori-history")
        self.inference_queue = InferenceQueue()
        self.live_updates = deque()
        self.drafts = {}
        self.finished_segments = set()
        self.contexts = {}
        self.dirty_days = set()
        self.last_key_event = 0
        self.mouse_listener = None
        self.start_when_ready = False
        self.engine = QwenEngine(directory / "models", self.settings.device)
        self.hotkey = None
        self.gesture = HotkeyGesture(self.settings.mode, self.settings.hold_ms)
        self.ready, self.loading, self.recording, self.quitting = demo, False, False, False
        self.pending, self.recognized = 0, 0
        self.session, self.clipboard_value = "", ""
        self.target, self.started_at = InputTarget(), None
        self.started_clock = 0
        self.last_signal = 0
        self.today = datetime.now().astimezone().date().isoformat()
        self.delivery_queue, self.delivery_active = [], False
        self.target_invalidated = False
        self.error_in_session = False
        self.tray = None
        self.bridge.key.connect(self.on_key)
        self.bridge.model_loaded.connect(self.model_loaded)
        self.bridge.model_failed.connect(self.model_failed)
        self.bridge.transcript.connect(self.accept_transcript)
        self.bridge.notice.connect(self.notice)
        self.bridge.activity.connect(self.on_activity)
        self.microphone.chunk.connect(self.transcribe_chunk)
        self.microphone.preview.connect(self.transcribe_preview)
        self.microphone.level.connect(self.set_level)
        self.microphone.error.connect(self.microphone_failed)
        self.panel.toggle.connect(self.toggle)
        self.panel.open_history.connect(self.show_dashboard)
        self.panel.open_settings.connect(self.open_settings)
        self.panel.hidden_by_user.connect(lambda: self.show_dashboard() if not self.tray else None)
        self.dashboard.open_panel.connect(self.show_panel)
        self.dashboard.open_settings.connect(self.open_settings)
        self.dashboard.prepare.connect(self.prepare_model)
        self.dashboard.copy_text.connect(self.copy)
        self.dashboard.export.connect(self.open_archive)
        self.dashboard.exit_app.connect(self.quit)
        self.dashboard.close_requested.connect(self.close_dashboard)
        self.application.aboutToQuit.connect(self.cleanup)
        self.application.setQuitOnLastWindowClosed(False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(30)
        self.day_timer = QTimer(self)
        self.day_timer.timeout.connect(self.rollover)
        self.day_timer.start(1000)
        self.archive_timer = QTimer(self)
        self.archive_timer.setSingleShot(True)
        self.archive_timer.timeout.connect(self.export_pending)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(lambda: self.dashboard.refresh(self.store) if self.dashboard.isVisible() else None)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.panel.dismiss)
        if demo:
            self.seed_demo()
        else:
            self.setup_hotkey()
        self.setup_tray()
        self.update_preferences()
        self.dashboard.refresh(self.store)
        screen = application.primaryScreen().availableGeometry()
        self.panel.move(screen.right() - self.panel.width() - 30, screen.bottom() - self.panel.height() - 30)
        self.dashboard.move(screen.center() - self.dashboard.rect().center())
        if demo or not background or not QSystemTrayIcon.isSystemTrayAvailable():
            (self.panel if compact else self.dashboard).show()
        elif compact:
            self.show_panel()
        note = platform_note() if not demo else "UI 미리보기 · 아래 기록은 예시입니다. 실제 마이크와 클립보드는 사용하지 않습니다."
        if note:
            self.notice(note)
        if self.store.export_error:
            self.notice("기록 파일 복구 실패: " + self.store.export_error)
        if not demo:
            if self.engine.cache_available():
                QTimer.singleShot(0, self.prepare_model)
            else:
                self.panel.status.setText("모델을 먼저 준비해 주세요")
                self.dashboard.hero_status.setText("처음에는 모델을 준비해 주세요.")
                self.show_dashboard()
            try:
                from pynput import mouse
                self.mouse_listener = mouse.Listener(on_click=lambda x, y, button, pressed: self.bridge.activity.emit((x, y)) if pressed else None)
                self.mouse_listener.start()
            except Exception:
                logging.exception("Mouse activity monitor could not start")

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icon("logo", "#9c77d9", 64), self)
        self.tray.setToolTip("소리 · 음성 입력")
        self.tray_menu = QMenu(self.dashboard)
        for title, callback in [("음성 입력 패널", self.show_panel), ("나의 기록", self.show_dashboard),
                                ("설정", self.open_settings), ("모델 준비 / 재시도", self.prepare_model), ("종료", self.quit)]:
            self.tray_menu.addAction(title).triggered.connect(callback)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(lambda reason: self.show_panel() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def setup_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
        self.gesture = HotkeyGesture(self.settings.mode, self.settings.hold_ms)
        self.hotkey = GlobalHotkey(self.settings.hotkey, self.bridge.key.emit, self.bridge.notice.emit,
                                  lambda: self.bridge.activity.emit(time.monotonic()))
        self.hotkey.start()

    def update_preferences(self):
        key = hotkey_label(self.settings.hotkey)
        self.panel.hint.setText(f"{key}을 눌러 시작 · 다시 눌러 마치기" if self.settings.mode == "toggle" else f"{key}을 길게 누르는 동안 입력")
        self.dashboard.sidebar_hint.setText(f"{key}을 {'누르고' if self.settings.mode == 'toggle' else '길게 누르고'}\n떠오르는 대로 말해보세요.")
        self.dashboard.hero_hint.setText(f"입력할 곳에 커서를 놓고 {key}을 {'눌러' if self.settings.mode == 'toggle' else '길게 눌러'}보세요.\n받아쓴 문장이 그 자리에 입력됩니다.")
        if self.ready:
            self.dashboard.prepare_button.setText("음성 입력 패널 열기")

    def show_panel(self):
        self.hide_timer.stop()
        self.panel.reveal()

    def show_dashboard(self):
        self.dashboard.refresh(self.store)
        self.dashboard.show()
        self.dashboard.raise_()
        self.dashboard.activateWindow()

    def close_dashboard(self):
        if self.tray:
            self.dashboard.hide()
        else:
            self.quit()

    def prepare_model(self):
        if self.ready:
            self.show_panel()
            return
        if self.loading or self.quitting:
            return
        self.loading = True
        self.panel.status.setText("음성 인식 모델 준비 중…")
        self.panel.engine_label.setText("●  첫 실행: 모델 다운로드 및 로딩")
        self.dashboard.hero_status.setText("목소리를 들을 준비 중이에요.")
        self.dashboard.prepare_button.setText("모델 다운로드 / 로딩 중…")
        self.dashboard.prepare_button.setEnabled(False)
        def load():
            try:
                self.bridge.model_loaded.emit(self.engine.load())
            except Exception as exc:
                logging.exception("Model preparation failed")
                self.bridge.model_failed.emit(str(exc))
        self.worker.submit(load)

    def model_loaded(self, device):
        self.loading, self.ready = False, True
        if self.quitting:
            self.finish_quit()
            return
        self.panel.status.setText("목소리를 들려주세요")
        self.panel.engine_label.setText(f"●  Qwen3 ASR · 0.6B · {device.upper()}")
        self.dashboard.hero_status.setText("생각의 속도로, 말하세요.")
        self.dashboard.prepare_button.setEnabled(True)
        self.update_preferences()
        self.notice(f"모델 준비 완료 · 입력할 곳에 커서를 두고 {hotkey_label(self.settings.hotkey)}을 눌러주세요.")
        if self.start_when_ready:
            self.start_when_ready = False
            self.start()

    def model_failed(self, error):
        self.loading = False
        if self.quitting:
            self.finish_quit()
            return
        self.panel.status.setText("모델 준비를 다시 시도해 주세요")
        self.panel.engine_label.setText("●  모델 준비 실패 · 기록 화면에서 재시도")
        self.dashboard.prepare_button.setText("모델 준비 다시 시도")
        self.dashboard.prepare_button.setEnabled(True)
        self.notice("모델 준비 실패: " + error)

    def on_key(self, event):
        self.last_key_event = time.monotonic()
        logging.info("Hotkey received: %s %s", self.settings.hotkey, event)
        if not self.quitting:
            self.action(self.gesture.press(time.monotonic()) if event == "press" else self.gesture.release())

    def action(self, action):
        if action == "toggle":
            self.toggle()
        elif action == "start":
            self.start()
        elif action == "stop":
            self.stop()

    def tick(self):
        self.action(self.gesture.tick(time.monotonic()))
        if self.desktop and self.target.external and (self.recording or self.pending or self.delivery_queue):
            current = self.desktop.target() if hasattr(self.desktop, "target") else None
            if current is None or current.token:
                if not self.desktop.unchanged(self.target):
                    self.target_invalidated = True
                for context in self.contexts.values():
                    if not self.desktop.unchanged(context["target"]):
                        context["invalidated"] = True
        elif self.desktop and not self.demo and hasattr(self.desktop, "target"):
            self.desktop.target()  # Remember the last external input app before a panel click.
        if self.recording:
            seconds = int(time.monotonic() - self.started_clock)
            quiet = time.monotonic() - self.last_signal >= 3
            state = "입력 신호 없음" if not self.demo and not self.microphone.frames_received and seconds >= 3 else ("음량을 확인해 주세요" if quiet else "듣고 있어요")
            self.panel.status.setText(f"{state}   {seconds // 60:02}:{seconds % 60:02}")
            if seconds >= 300:
                self.stop()
                self.notice("5분 녹음을 마쳤습니다. 계속하려면 단축키를 다시 눌러주세요.")

    def toggle(self):
        if self.start_when_ready:
            self.start_when_ready = False
            self.panel.dismiss()
            return
        self.stop() if self.recording else self.start()

    def start(self):
        if self.quitting or self.recording:
            return
        if not self.ready:
            self.start_when_ready = True
            self.prepare_model()
            self.show_panel()
            return
        if self.delivery_active:
            self.start_when_ready = True
            QTimer.singleShot(80, lambda: self.start() if self.start_when_ready else None)
            return
        self.start_when_ready = False
        if not self.pending and not self.inference_queue and not self.live_updates and not self.delivery_queue:
            self.contexts.clear()
            self.finished_segments.clear()
            self.drafts.clear()
        self.target = self.desktop.recording_target() if self.desktop and hasattr(self.desktop, "recording_target") else (self.desktop.target() if self.desktop else InputTarget())
        self.target_invalidated = False
        self.session = uuid.uuid4().hex
        self.contexts[self.session] = {"target": self.target, "invalidated": False}
        self.clipboard_value = self.store.clipboard_text(self.today, "", self.settings.clipboard)
        self.started_at = datetime.now().astimezone()
        self.started_clock = time.monotonic()
        self.last_signal = self.started_clock
        self.recognized, self.error_in_session = 0, False
        self.recording = True
        logging.info("Recording start requested: hotkey=%s target_external=%s", self.settings.hotkey, self.target.external)
        try:
            if not self.demo:
                self.microphone.start(self.settings.microphone)
        except Exception as exc:
            self.recording = False
            self.notice(str(exc))
            self.panel.status.setText("마이크를 확인해 주세요")
            self.dashboard.hero_status.setText("마이크 테스트를 해 주세요.")
            return
        self.panel.voice.active = self.dashboard.voice.active = True
        self.dashboard.hero_status.setText("당신의 목소리를 듣고 있어요.")
        self.show_panel()

    def stop(self):
        self.start_when_ready = False
        if not self.recording:
            return
        self.recording = False
        logging.info("Recording stopped: pending=%s recognized=%s", self.pending, self.recognized)
        if not self.demo:
            self.microphone.stop()
            logging.info("Microphone capture: frames=%s peak_rms=%.5f", self.microphone.frames_received, self.microphone.peak_level)
        self.panel.voice.active = self.dashboard.voice.active = False
        self.panel.status.setText("문장을 정리하고 있어요…" if self.pending else "목소리를 들려주세요")
        self.dashboard.hero_status.setText("생각의 속도로, 말하세요.")
        self.update_preferences()
        self.hide_timer.start(900)
        if not self.demo and not self.pending and not self.recognized:
            self.notice("인식할 음성이 없었습니다. 마이크와 입력 음량을 확인해 주세요.")

    def microphone_failed(self, error):
        self.stop()
        self.notice(error)

    def set_level(self, level):
        self.panel.voice.level = self.dashboard.voice.level = level
        if level >= 0.021:
            self.last_signal = time.monotonic()

    def transcribe_chunk(self, samples, offset):
        self.request_inference(samples, offset, final=True)

    def transcribe_preview(self, samples, offset):
        if self.recording:
            self.request_inference(samples, offset, final=False)

    def request_inference(self, samples, offset, final):
        if self.started_at is None:
            return
        metadata = {"timestamp": self.started_at + timedelta(seconds=offset), "session": self.session,
                    "duration": len(samples) / 16000, "language": self.settings.language, "target": self.target,
                    "auto_paste": self.settings.auto_paste, "samples": samples, "final": final, "stream": True,
                    "segment": f"{self.session}:{round(offset * 16000)}", "queued_at": time.monotonic()}
        if final:
            self.pending += 1
        self.inference_queue.add(metadata)
        self.pump_inference()

    def pump_inference(self):
        metadata = self.inference_queue.next()
        if metadata is None:
            return
        samples = metadata.pop("samples")
        def transcribe():
            began = time.monotonic()
            try:
                metadata["text"] = self.engine.transcribe(samples, metadata["language"])
            except Exception as exc:
                logging.exception("Transcription failed")
                metadata["error"] = str(exc)
                if metadata["final"]:
                    import wave
                    import numpy as np
                    try:
                        recovery = self.directory / "recovery"
                        recovery.mkdir(parents=True, exist_ok=True)
                        path = recovery / f"{metadata['timestamp']:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.wav"
                        with wave.open(str(path), "wb") as file:
                            file.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                            file.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
                        metadata["error"] += f" · 원본 음성 보관: {path}"
                    except OSError:
                        logging.exception("Audio recovery failed")
            metadata["inference_seconds"] = time.monotonic() - began
            self.bridge.transcript.emit(metadata)
        self.worker.submit(transcribe)

    def on_activity(self, activity):
        if not (self.recording or self.pending or self.inference_queue):
            return
        if isinstance(activity, tuple):
            if self.desktop and hasattr(self.desktop, "own_window_at") and self.desktop.own_window_at(*activity):
                return
            from PySide6.QtCore import QPoint
            if self.panel.isVisible() and self.panel.frameGeometry().contains(QPoint(*map(round, activity))):
                return
            self.pause_auto_input()
        else:
            QTimer.singleShot(70, lambda: self.pause_auto_input() if abs(self.last_key_event - activity) > 0.15 else None)

    def pause_auto_input(self):
        for context in self.contexts.values():
            context["invalidated"] = True
        if not self.target_invalidated:
            self.target_invalidated = True
            self.notice("키 입력이나 클릭으로 입력 위치가 바뀌어 자동 입력을 멈췄습니다. 받아쓰기는 기록과 클립보드에 보관합니다.")

    def queue_live_update(self, result):
        segment = result["segment"]
        if segment in self.finished_segments:
            return
        if result["session"] == self.session:
            self.dashboard.live_text.setText("입력 중 · " + result["text"])
            self.dashboard.live_text.setVisible(bool(result["text"]))
        if self.recording and result["session"] == self.session and result["text"]:
            shown = result["text"][-34:]
            self.panel.hint.setText(shown)
        if sys.platform != "win32":
            return
        self.live_updates = deque(item for item in self.live_updates if item["segment"] != segment or item["final"])
        self.live_updates.append(result)
        self.apply_live_update()

    def apply_live_update(self):
        if self.delivery_active or not self.live_updates:
            return
        result = self.live_updates[0]
        target = result["target"]
        invalidated = self.contexts.get(result["session"], {}).get("invalidated", self.target_invalidated)
        if not self.quitting and result["auto_paste"] and not invalidated and self.desktop.unchanged(target):
            if not self.desktop.safe_to_type():
                QTimer.singleShot(80, self.apply_live_update)
                return
        self.live_updates.popleft()
        segment = result["segment"]
        if result["auto_paste"] and not self.quitting and not invalidated and self.desktop.unchanged(target):
            draft = self.drafts.setdefault(segment, Draft())
            previous = draft.text
            erase, suffix = draft.change(result["text"] + (" " if result["final"] and result["text"] else ""))
            try:
                paste = self.settings.input_method == "paste" and bool(suffix)
                if paste:
                    self.application.clipboard().setText(suffix)
                    self.delivery_active = True
                self.desktop.windows_type(suffix, backspaces=erase, paste=paste)
                logging.info("Draft delivered: segment=%s final=%s erase=%s chars=%s method=%s", segment,
                             result["final"], erase, len(suffix), self.settings.input_method)
                if result.get("entry"):
                    self.store.delivered(result["entry"]["id"], "pasted" if paste else "typed")
                if paste:
                    QTimer.singleShot(220, self.live_delivery_finished)
            except Exception as exc:
                draft.text = previous
                self.delivery_active = False
                self.target_invalidated = True
                if result["session"] in self.contexts:
                    self.contexts[result["session"]]["invalidated"] = True
                self.notice("입력 전달 실패 · 클립보드와 기록에 보관합니다: " + str(exc))
        elif result["final"] and result["auto_paste"]:
            logging.info("Automatic input skipped: external=%s changed=%s", target.external, self.target_invalidated)
        if result["final"]:
            self.finished_segments.add(segment)
            self.drafts.pop(segment, None)
        if not self.delivery_active:
            self.restore_clipboard()
            self.apply_live_update()

    def restore_clipboard(self):
        drafts = " ".join(draft.text.strip() for draft in self.drafts.values() if draft.text.strip())
        text = drafts if drafts and self.settings.clipboard == "latest" else "\n".join(part for part in (self.clipboard_value, drafts) if part)
        if text:
            self.application.clipboard().setText(text)

    def live_delivery_finished(self):
        self.delivery_active = False
        self.restore_clipboard()
        self.apply_live_update()
        self.check_quit()

    def schedule_export(self, day):
        self.dirty_days.add(day)
        self.archive_timer.start(300)

    def export_pending(self):
        for day in sorted(self.dirty_days):
            rows = self.store.entries(day)
            archive = self.store.archive
            def export(rows=rows, archive=archive, day=day):
                try:
                    HistoryStore.write_export(archive, day, rows)
                except Exception as exc:
                    self.bridge.notice.emit("일별 파일 저장 실패 · 데이터베이스에는 보관됐습니다: " + str(exc))
            self.archiver.submit(export)
        self.dirty_days.clear()

    def accept_transcript(self, result):
        final = result.get("final", True)
        stream = result.get("stream", False)
        if final:
            self.pending -= 1
        if stream:
            self.inference_queue.finished()
            logging.info("Inference result: final=%s audio=%.2fs inference=%.2fs queue=%.2fs chars=%s", final,
                         result["duration"], result.get("inference_seconds", 0),
                         time.monotonic() - result["queued_at"], len(result.get("text", "")))
        if "error" in result:
            self.error_in_session = True
            self.notice("음성 인식 실패: " + result["error"])
            if final and stream and result["segment"] in self.drafts:
                result["text"] = self.drafts[result["segment"]].text.strip()
                if result["text"]:
                    result["entry"] = self.save_transcript(result, stream=True)
                self.queue_live_update(result)
        else:
            if stream:
                if final and result["text"]:
                    result["entry"] = self.save_transcript(result, stream=sys.platform == "win32")
                self.queue_live_update(result)
            elif result["text"]:
                self.save_transcript(result)
        if stream:
            self.pump_inference()
        if not self.recording and not self.pending:
            self.panel.status.setText("기록을 저장했어요" if self.recognized else "목소리를 들려주세요")
            if not self.recognized and not self.error_in_session:
                self.notice("인식할 음성이 없었습니다. 마이크와 입력 음량을 확인해 주세요.")
        self.check_quit()

    def save_transcript(self, result, stream=False):
        try:
            entry = self.store.add(result["text"], result["timestamp"], result["session"], result["duration"],
                                   result["language"], result["target"].title if result["target"].external else "음성 메모")
        except Exception as exc:
            self.error_in_session = True
            self.copy(result["text"])
            self.notice("기록 저장 실패 · 문장은 클립보드에 보관했습니다: " + str(exc))
            return
        self.recognized += 1
        day = datetime.now().astimezone().date().isoformat()
        self.clipboard_value = self.store.clipboard_text(day, result["text"], self.settings.clipboard) or result["text"]
        if not self.delivery_active:
            self.application.clipboard().setText(self.clipboard_value)
        self.schedule_export(entry["day"])
        self.refresh_timer.start(150)
        if not stream:
            self.delivery_queue.append((result["text"], result["target"], entry, result["auto_paste"], time.monotonic()))
            self.deliver_next()
        return entry

    def deliver_next(self):
        if self.delivery_active or not self.delivery_queue:
            return
        text, target, entry, enabled, queued = self.delivery_queue[0]
        if self.quitting or not enabled or self.target_invalidated or not self.desktop.unchanged(target):
            self.delivery_queue.pop(0)
            if enabled and target.external and not self.quitting:
                self.notice("입력창이 바뀌어 자동 입력을 멈췄습니다. 문장은 클립보드와 기록에 저장됐습니다.")
            self.deliver_next()
            return
        if sys.platform != "win32" and self.hotkey and not self.hotkey.modifiers_released():
            if time.monotonic() - queued < 2.5 or self.recording:
                QTimer.singleShot(80, self.deliver_next)
                return
            self.delivery_queue.pop(0)
            self.notice("키가 눌린 상태여서 자동 입력을 멈췄습니다. 클립보드에서 붙여넣을 수 있습니다.")
            self.deliver_next()
            return
        self.delivery_queue.pop(0)
        self.delivery_active = True
        try:
            if sys.platform == "win32":
                paste = self.settings.input_method == "paste"
                if paste:
                    self.application.clipboard().setText(text + " ")
                self.desktop.windows_type(text + " ", paste=paste)
                if paste:
                    QTimer.singleShot(220, lambda: self.delivery_finished(entry, "pasted"))
                else:
                    self.delivery_finished(entry, "typed")
            else:
                self.application.clipboard().setText(text + " ")
                def paste():
                    try:
                        if not self.desktop.unchanged(target):
                            raise RuntimeError("입력창이 바뀌었습니다. 클립보드에서 붙여넣어 주세요.")
                        self.desktop.paste_shortcut()
                        QTimer.singleShot(600, lambda: self.delivery_finished(entry, "pasted"))
                    except Exception as exc:
                        self.notice("자동 입력 실패: " + str(exc))
                        self.delivery_finished(entry, "clipboard")
                QTimer.singleShot(100, paste)
        except Exception as exc:
            self.notice("자동 입력 실패: " + str(exc))
            self.delivery_finished(entry, "clipboard")

    def delivery_finished(self, entry, delivery):
        self.delivery_active = False
        current = self.application.clipboard().text()
        if sys.platform == "win32" or current == entry["text"] + " ":
            self.application.clipboard().setText(self.clipboard_value)
        try:
            self.store.delivered(entry["id"], delivery)
            self.schedule_export(entry["day"])
        except Exception as exc:
            self.notice("기록 파일 갱신 실패: " + str(exc))
        self.deliver_next()
        self.check_quit()

    def copy(self, text):
        if text:
            self.clipboard_value = text
            if not self.demo:
                self.application.clipboard().setText(text)
            self.notice("클립보드에 복사했습니다." if not self.demo else "미리보기에서는 클립보드를 변경하지 않습니다.")

    def rollover(self):
        today = datetime.now().astimezone().date().isoformat()
        if today != self.today:
            self.schedule_export(self.today)
            if self.dashboard.selected_day == self.today:
                self.dashboard.selected_day = today
            self.today = today
            self.dashboard.refresh(self.store)

    def open_archive(self):
        try:
            self.export_pending()
            self.archiver.submit(lambda: None).result(timeout=10)
            self.store.export_all()
            self.store.archive.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.notice("기록 폴더를 열 수 없습니다: " + str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.archive.resolve())))

    def open_settings(self):
        if self.recording or self.pending or self.inference_queue or self.loading or self.delivery_active or self.delivery_queue:
            self.notice("현재 음성 처리를 마친 뒤 설정을 변경해 주세요.")
            return
        if self.hotkey:
            self.hotkey.enabled = False
        self.gesture.release()
        dialog = SettingsDialog(self.settings, self.microphone.devices(), self.dashboard if self.dashboard.isVisible() else None)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = replace(self.settings)
            dialog.update_settings(updated)
            changed_device = updated.device != self.settings.device
            try:
                archive = Path(updated.archive_directory).expanduser() if updated.archive_directory else self.directory / "history"
                atomic_write(archive / ".sori-write-check", "")
                (archive / ".sori-write-check").unlink()
                updated.save(self.directory)
                self.settings, self.store.archive = updated, archive
                self.store.export_all()
                if changed_device:
                    self.ready = False
                    self.engine = QwenEngine(self.directory / "models", self.settings.device)
                    self.dashboard.prepare_button.setText("모델 준비하기")
                if not self.demo:
                    self.setup_hotkey()
                self.update_preferences()
            except Exception as exc:
                self.notice("설정 저장 실패: " + str(exc))
        if self.hotkey:
            with self.hotkey.lock:
                self.hotkey.pressed.clear()
                self.hotkey.active = False
            self.hotkey.enabled = True

    def notice(self, message):
        logging.info(message)
        self.dashboard.footer.setText(message)
        self.dashboard.footer.setToolTip(message)
        if self.tray and not self.demo and not self.dashboard.isVisible() and not message.startswith("모델 준비 완료"):
            self.tray.showMessage("소리", message, QSystemTrayIcon.MessageIcon.Information, 4500)

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.stop()
        self.notice("남은 음성과 기록을 저장한 뒤 종료합니다.")
        if self.hotkey:
            self.hotkey.stop()
        self.deliver_next()
        self.check_quit()

    def check_quit(self):
        if self.quitting and not self.pending and not self.inference_queue and not self.loading and not self.delivery_active and not self.delivery_queue and not self.live_updates:
            self.finish_quit()

    def finish_quit(self):
        self.application.quit()

    def cleanup(self):
        self.timer.stop()
        self.day_timer.stop()
        self.archive_timer.stop()
        self.refresh_timer.stop()
        self.hide_timer.stop()
        if self.hotkey:
            self.hotkey.stop()
        if self.mouse_listener:
            self.mouse_listener.stop()
        self.microphone.stop()
        self.worker.shutdown(wait=True)
        self.export_pending()
        self.archiver.shutdown(wait=True)
        try:
            self.store.export_all()
        except OSError:
            logging.exception("Final export failed; entries remain in SQLite")
        self.store.close()
        if self.desktop:
            self.desktop.close()

    def seed_demo(self):
        now = datetime.now().astimezone()
        for ago, text, duration, target in [
            (18, "이번 주에는 작은 아이디어를 바로 기록하는 습관을 만들어보자. 완벽한 문장보다, 생각을 놓치지 않는 게 더 중요하다.", 14.2, "Notion · 나의 메모"),
            (39, "안녕하세요. 보내주신 내용 확인했습니다. 금요일 오후에 짧게 이야기 나누면 좋겠습니다.", 9.8, "메일 · 답장"),
            (65, "목소리가 곧 기록이 된다면, 생각은 조금 더 자유로워질 수 있을 것 같다.", 8.4, "음성 메모"),
        ]:
            self.store.add(text, now - timedelta(minutes=ago), uuid.uuid4().hex, duration, "Korean", target)
        self.store.export_all()


def main():
    parser = argparse.ArgumentParser(description="소리 · Qwen3-ASR local desktop dictation")
    parser.add_argument("--demo", action="store_true", help="Isolated UI preview; no microphone or input injection")
    parser.add_argument("--compact", action="store_true", help="Start with only the floating panel")
    parser.add_argument("--dashboard", action="store_true", help="Open history on launch instead of waiting in the tray")
    parser.add_argument("--data-dir", type=Path, help="Override settings/history/model directory")
    parser.add_argument("--diagnostics", type=Path, help="Write runtime check results to this JSON file and exit")
    parser.add_argument("--audio-file", type=Path, help="Transcribe this public/test audio file during diagnostics")
    parser.add_argument("--cache-dir", type=Path, help="Use this model cache during diagnostics")
    parser.add_argument("--microphone-test", action="store_true", help="Brief diagnostic capture; discard audio")
    parser.add_argument("--preview-dir", type=Path, help="Save an isolated demo preview and exit")
    parser.add_argument("--desktop-test", type=Path, help="Opt-in Windows owned-editor integration check")
    parser.add_argument("--input-target", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--input-command", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.input_target:
        from sori.desktop_check import run_target
        return run_target(args.input_target, args.input_command)
    if args.desktop_test:
        from sori.desktop_check import run
        return run(args.desktop_test, args.audio_file, args.cache_dir)
    if args.diagnostics:
        from sori.diagnostics import run
        return run(args.diagnostics, args.audio_file, args.cache_dir, args.microphone_test)
    if args.preview_dir:
        args.demo = True
    if sys.platform == "win32":
        import ctypes
        identify = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        identify.argtypes, identify.restype = [ctypes.c_wchar_p], ctypes.c_long
        identify("Sori.Dictation")
    temporary = tempfile.TemporaryDirectory(prefix="sori-demo-") if args.demo else None
    directory = Path(temporary.name) if temporary else (args.data_dir or data_directory())
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(directory / "sori.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    application = QApplication(sys.argv[:1])
    application.setApplicationName("소리")
    application.setOrganizationName("Sori")
    configure_appearance(application)
    app_icon = Path(__file__).parent / "assets" / "sori.ico"
    if app_icon.exists():
        application.setWindowIcon(QIcon(str(app_icon)))
    lock = QLockFile(str(directory / "sori.lock"))
    server_name = "sori-" + hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:20]
    if not lock.tryLock(100):
        client = QLocalSocket()
        client.connectToServer(server_name)
        if client.waitForConnected(600):
            client.write(b"dashboard" if args.dashboard else b"panel")
            client.waitForBytesWritten(600)
            client.disconnectFromServer()
        else:
            QMessageBox.information(None, "소리", "소리가 이미 실행 중입니다. 트레이의 소리 아이콘에서 기록 또는 설정을 여세요.")
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(server_name)
    controller = Controller(application, directory, args.demo, args.compact, background=not args.dashboard)
    def incoming():
        client = server.nextPendingConnection()
        def receive():
            request = bytes(client.readAll())
            controller.show_dashboard() if request == b"dashboard" else controller.show_panel()
            client.disconnectFromServer()
        client.readyRead.connect(receive)
        client.disconnected.connect(client.deleteLater)
        if client.bytesAvailable():
            receive()
    server.newConnection.connect(incoming)
    if args.preview_dir:
        def preview():
            import json
            args.preview_dir.mkdir(parents=True, exist_ok=True)
            controller.panel.show()
            application.processEvents()
            controller.dashboard.grab().save(str(args.preview_dir / "dashboard.png"))
            controller.panel.grab().save(str(args.preview_dir / "floating-panel.png"))
            controller.panel.voice.active = True
            controller.panel.voice.smoothed_level = controller.panel.voice.level = 0.65
            controller.panel.status.setText("듣고 있어요   00:12")
            controller.panel.grab().save(str(args.preview_dir / "floating-panel-listening.png"))
            dialog = SettingsDialog(controller.settings, Microphone.devices())
            dialog.show()
            application.processEvents()
            dialog.grab().save(str(args.preview_dir / "settings.png"))
            (args.preview_dir / "appearance.json").write_text(json.dumps({"font": application.font().family(),
                "panel_width": controller.panel.width(), "panel_height": controller.panel.height()}, ensure_ascii=False), encoding="utf-8")
            dialog.close()
            application.quit()
        QTimer.singleShot(200, preview)
    result = application.exec()
    server.close()
    lock.unlock()
    logging.shutdown()
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
