"""Opt-in executable checks. Capture is brief and discarded; ASR uses a supplied file."""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path


def run(output: Path, audio: Path | None = None, cache: Path | None = None, capture=False) -> int:
    report = {"frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable}
    try:
        import PySide6
        import torch
        import transformers
        from PySide6.QtCore import QCoreApplication, QTimer
        from sori.audio import Microphone
        report.update(qt=PySide6.__version__, torch=torch.__version__, transformers=transformers.__version__)
        app = QCoreApplication.instance() or QCoreApplication([])
        report["microphones"] = Microphone.devices()
        if capture:
            mic = Microphone()
            errors = []
            mic.error.connect(errors.append)
            mic.start(monitor_only=True)
            QTimer.singleShot(500, app.quit)
            app.exec()
            mic.stop()
            report["capture"] = {"frames_received": mic.frames_received, "errors": errors}
            if not mic.frames_received or errors:
                raise RuntimeError("Microphone capture produced no frames or reported an error")
        if audio:
            import librosa
            from sori.engine import QwenEngine
            from sori.storage import data_directory
            engine = QwenEngine(cache or data_directory() / "models", "cpu")
            report["model_cached"] = engine.cache_available()
            started = time.monotonic()
            report["device"] = engine.load()
            report["load_seconds"] = round(time.monotonic() - started, 3)
            samples, _ = librosa.load(audio, sr=16000, mono=True)
            started = time.monotonic()
            report["transcript"] = engine.transcribe(samples, "English")
            report["inference_seconds"] = round(time.monotonic() - started, 3)
            if not report["transcript"]:
                raise RuntimeError("The supplied sample produced an empty transcript")
        report["ok"] = True
    except Exception:
        report["ok"] = False
        report["error"] = traceback.format_exc()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
