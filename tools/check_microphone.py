"""Inspect audio devices. --open tests capture without saving or transcribing audio."""
import argparse
import json

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QAudio, QtAudio

parser = argparse.ArgumentParser()
parser.add_argument("--open", action="store_true", help="Open the default microphone briefly; discard captured bytes")
parser.add_argument("--buffer-ms", type=int, default=0, help="Override capture buffer duration to reproduce driver failures")
args = parser.parse_args()
app = QCoreApplication([])
print(json.dumps({"legacy_audio_error_matches": QAudio.Error.NoError == QtAudio.Error.NoError,
                  "legacy_audio_state_matches": QAudio.State.StoppedState == QtAudio.State.StoppedState}), flush=True)


def format_info(fmt):
    return {"rate": fmt.sampleRate(), "channels": fmt.channelCount(), "format": fmt.sampleFormat().name,
            "valid": fmt.isValid()}


devices = QMediaDevices.audioInputs()
requested = QAudioFormat()
requested.setSampleRate(16000)
requested.setChannelCount(1)
requested.setSampleFormat(QAudioFormat.SampleFormat.Int16)
for device in devices:
    print(json.dumps({"device": device.description(), "default": device.isDefault(),
                      "id": bytes(device.id()).hex(), "preferred": format_info(device.preferredFormat()),
                      "supports_16000_mono_int16": device.isFormatSupported(requested)}, ensure_ascii=True), flush=True)

if args.open and devices:
    device = QMediaDevices.defaultAudioInput()
    formats = [("preferred", device.preferredFormat()), ("16000-mono-int16", requested)]
    sources = []
    def test_next():
        if not formats:
            app.quit()
            return
        name, fmt = formats.pop(0)
        source = QAudioSource(device, fmt)
        sources.append(source)
        if args.buffer_ms:
            source.setBufferSize(fmt.bytesForDuration(args.buffer_ms * 1000))
        io = source.start()
        print(json.dumps({"attempt": name, "format": format_info(fmt), "io": io is not None,
                          "buffer_ms": args.buffer_ms, "state": source.state().name, "error": source.error().name}), flush=True)
        def finish():
            # Deliberately neither inspect speech content nor write raw audio.
            available = io.bytesAvailable() if io is not None else 0
            print(json.dumps({"attempt": name, "after_ms": 300, "available_bytes": available,
                              "state": source.state().name, "error": source.error().name}), flush=True)
            source.stop()
            source.deleteLater()
            QTimer.singleShot(100, test_next)
        QTimer.singleShot(300, finish)
    QTimer.singleShot(0, test_next)
    app.exec()
