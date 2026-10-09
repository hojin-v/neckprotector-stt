"""Regression for Qt 6.12's distinct legacy QAudio and current QtAudio enums."""
import sys
import types
import unittest
from enum import Enum, auto
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication
from sori.audio import Microphone


class AudioError(Enum):
    NoError = auto()
    OpenError = auto()


class AudioState(Enum):
    ActiveState = auto()
    StoppedState = auto()


class LegacyError(Enum):
    NoError = auto()


class Format:
    class SampleFormat(Enum):
        Int16 = auto()
        Int32 = auto()
        UInt8 = auto()
        Float = auto()

    def setSampleRate(self, value): self.rate = value
    def setChannelCount(self, value): self.channels = value
    def setSampleFormat(self, value): self.fmt = value
    def sampleRate(self): return self.rate
    def channelCount(self): return self.channels
    def sampleFormat(self): return self.fmt
    def bytesPerFrame(self): return 2 * self.channels
    def bytesForDuration(self, duration): return round(self.rate * 2 * duration / 1_000_000)


class MicrophoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.device = MagicMock()
        self.device.id.return_value = b"default"
        self.device.description.return_value = "Test microphone"
        self.device.isFormatSupported.return_value = True
        self.source = MagicMock()
        self.source.error.return_value = AudioError.NoError
        self.source.state.return_value = AudioState.ActiveState
        self.source.start.return_value.readAll.return_value = b""
        self.module = types.SimpleNamespace(
            QAudioFormat=Format, QAudioSource=MagicMock(return_value=self.source),
            QMediaDevices=types.SimpleNamespace(audioInputs=lambda: [self.device], defaultAudioInput=lambda: self.device),
            QtAudio=types.SimpleNamespace(Error=AudioError, State=AudioState),
            QAudio=types.SimpleNamespace(Error=LegacyError, State=AudioState),
        )
        self.mock_import = patch.dict(sys.modules, {"PySide6.QtMultimedia": self.module})
        self.mock_import.start()
        self.mic = Microphone()

    def tearDown(self):
        self.mic.stop()
        self.mock_import.stop()

    def test_current_noerror_opens_without_legacy_enum_rejection(self):
        self.assertNotEqual(AudioError.NoError, LegacyError.NoError)
        self.mic.start()
        self.assertIsNotNone(self.mic.io)
        self.source.stop.assert_not_called()
        self.mic._state(AudioState.StoppedState)
        self.assertIsNotNone(self.mic.io)

    def test_real_open_error_is_reported_and_source_closed(self):
        self.source.error.return_value = AudioError.OpenError
        with self.assertRaisesRegex(RuntimeError, "OpenError"):
            self.mic.start()
        self.source.stop.assert_called_once()
        self.assertIsNone(self.mic.source)

    def test_disconnect_reports_error_but_intentional_stop_does_not(self):
        errors = []
        self.mic.error.connect(errors.append)
        self.mic.start()
        self.source.error.return_value = AudioError.OpenError
        self.mic._state(AudioState.StoppedState)
        self.assertEqual(len(errors), 1)
        self.mic.stopping = True
        self.mic._state(AudioState.StoppedState)
        self.assertEqual(len(errors), 1)

    def test_monitor_decodes_levels_without_emitting_speech(self):
        levels, chunks = [], []
        self.mic.level.connect(levels.append)
        self.mic.chunk.connect(lambda *args: chunks.append(args))
        self.mic.start(monitor_only=True)
        self.source.start.return_value.readAll.return_value = b"\x00\x20" * 32000
        self.mic._read()
        self.assertEqual(self.mic.frames_received, 32000)
        self.assertGreater(levels[-1], 0.5)
        self.mic.stop()
        self.assertEqual(chunks, [])


if __name__ == "__main__":
    unittest.main()
