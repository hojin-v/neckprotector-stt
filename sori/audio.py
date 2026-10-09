from __future__ import annotations

import numpy as np
import logging
from PySide6.QtCore import QObject, Signal


class SpeechBuffer:
    """Short final segments with cumulative previews and 350 ms of pre-roll."""

    def __init__(self, rate: int, threshold: float = 0.002):
        self.rate, self.threshold = rate, threshold
        self.blocks = []
        self.samples = 0
        self.silence = 0
        self.voiced = False
        self.offset = 0
        self.start = 0
        self.last_preview = 0

    def feed(self, block: np.ndarray) -> tuple[np.ndarray, float] | None:
        self.blocks.append(block)
        self.samples += len(block)
        self.offset += len(block)
        loud = float(np.sqrt(np.mean(block ** 2))) >= self.threshold if len(block) else False
        if loud:
            self.voiced = True
            self.silence = 0
        else:
            self.silence += len(block)
        if not self.voiced:
            # Keep the latest 350 ms, including quiet consonants before a loud syllable.
            while len(self.blocks) > 1 and self.samples - len(self.blocks[0]) >= self.rate * 0.35:
                self.samples -= len(self.blocks.pop(0))
            self.start = self.offset - self.samples
        if self.voiced and (self.silence >= self.rate * 0.45 or self.samples >= self.rate * 6):
            return self.flush()
        return None

    def flush(self) -> tuple[np.ndarray, float] | None:
        result = None
        if self.voiced and self.samples >= self.rate * 0.15:
            result = (np.concatenate(self.blocks), self.start / self.rate)
        self.blocks, self.samples, self.silence, self.voiced = [], 0, 0, False
        self.start = self.offset
        self.last_preview = 0
        return result

    def preview(self):
        if self.voiced and self.samples >= self.rate * 0.8 and self.samples - self.last_preview >= self.rate * 0.8:
            self.last_preview = self.samples
            return np.concatenate(self.blocks), self.start / self.rate
        return None


class Microphone(QObject):
    level = Signal(float)
    chunk = Signal(object, float)
    preview = Signal(object, float)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = self.io = self.buffer = None
        self.remainder = b""
        self.stopping = False
        self.frames_received = 0
        self.peak_level = 0.0
        self.monitor_only = False

    @staticmethod
    def devices() -> list[tuple[str, str]]:
        try:
            from PySide6.QtMultimedia import QMediaDevices
            return [(bytes(device.id()).hex(), device.description()) for device in QMediaDevices.audioInputs()]
        except ImportError:
            return []

    def start(self, device_id: str = "", monitor_only: bool = False) -> None:
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio
        devices = QMediaDevices.audioInputs()
        if not devices:
            raise RuntimeError("마이크가 없습니다. 연결 및 운영체제의 마이크 권한을 확인해 주세요.")
        device = next((d for d in devices if bytes(d.id()).hex() == device_id), QMediaDevices.defaultAudioInput())
        self.format = QAudioFormat()
        self.format.setSampleRate(16000)
        self.format.setChannelCount(1)
        self.format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(self.format):
            self.format = device.preferredFormat()
        self.buffer = SpeechBuffer(self.format.sampleRate())
        self.remainder = b""
        self.stopping = False
        self.frames_received = 0
        self.peak_level = 0.0
        self.monitor_only = monitor_only
        self.source = QAudioSource(device, self.format, self)
        self.source.setBufferSize(self.format.bytesForDuration(100_000))
        self.source.stateChanged.connect(self._state)
        self.io = self.source.start()
        error = self.source.error()
        logging.info("Microphone opened: device=%s rate=%s channels=%s format=%s state=%s error=%s io=%s",
                     device.description(), self.format.sampleRate(), self.format.channelCount(),
                     self.format.sampleFormat().name, self.source.state().name, error.name, self.io is not None)
        if self.io is None or error != QtAudio.Error.NoError:
            self.stop()
            raise RuntimeError(f"마이크를 열 수 없습니다 ({error.name}). 설정에서 마이크를 선택하고 마이크 테스트를 눌러주세요.")
        self.io.readyRead.connect(self._read)

    def _state(self, state):
        from PySide6.QtMultimedia import QtAudio
        if not self.stopping and state == QtAudio.State.StoppedState and self.source:
            if self.source.error() != QtAudio.Error.NoError:
                self.error.emit("마이크 연결이 중단됐습니다. 연결 상태를 확인해 주세요.")

    def _read(self):
        from PySide6.QtMultimedia import QAudioFormat
        if self.io is None:
            return
        raw = self.remainder + bytes(self.io.readAll())
        frame = self.format.bytesPerFrame()
        usable = len(raw) // frame * frame
        self.remainder = raw[usable:]
        if not usable:
            return
        sample_format = self.format.sampleFormat()
        types = {QAudioFormat.SampleFormat.Int16: ("<i2", 32768),
                 QAudioFormat.SampleFormat.Int32: ("<i4", 2147483648),
                 QAudioFormat.SampleFormat.UInt8: ("u1", 128),
                 QAudioFormat.SampleFormat.Float: ("<f4", 1)}
        dtype, divisor = types[sample_format]
        samples = np.frombuffer(raw[:usable], dtype=dtype).astype(np.float32)
        if sample_format == QAudioFormat.SampleFormat.UInt8:
            samples -= 128
        samples /= divisor
        samples = samples.reshape(-1, self.format.channelCount()).mean(axis=1)
        self.frames_received += len(samples)
        rms = float(np.sqrt(np.mean(samples ** 2)))
        self.peak_level = max(self.peak_level, rms)
        self.level.emit(min(1.0, rms * 7))
        if self.monitor_only:
            return
        # Bounded blocks avoid dependence on the audio driver's callback size.
        for start in range(0, len(samples), max(1, self.format.sampleRate() // 20)):
            result = self.buffer.feed(samples[start:start + self.format.sampleRate() // 20])
            if result:
                self._emit(*result)
            else:
                preview = self.buffer.preview()
                if preview:
                    self._emit(*preview, preview=True)

    def _emit(self, samples, offset, preview=False):
        rate = self.format.sampleRate()
        if rate != 16000:
            count = round(len(samples) * 16000 / rate)
            samples = np.interp(np.arange(count) * rate / 16000, np.arange(len(samples)), samples).astype(np.float32)
        (self.preview if preview else self.chunk).emit(samples, offset)

    def stop(self):
        self.stopping = True
        if self.source:
            if self.io:
                self._read()
            self.source.stop()
            if self.buffer:
                result = self.buffer.flush()
                if result:
                    self._emit(*result)
            self.source.deleteLater()
        self.source = self.io = None
        self.level.emit(0)
