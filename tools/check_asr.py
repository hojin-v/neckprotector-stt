"""Run an actual Qwen transcription without opening a GUI."""
import argparse
import time
from pathlib import Path

import librosa
from sori.engine import QwenEngine
from sori.storage import data_directory

parser = argparse.ArgumentParser()
parser.add_argument("audio", type=Path)
parser.add_argument("--language", default="Korean")
parser.add_argument("--device", default="cpu")
parser.add_argument("--cache-dir", type=Path, default=data_directory() / "models")
args = parser.parse_args()
samples, _ = librosa.load(args.audio, sr=16000, mono=True)
engine = QwenEngine(args.cache_dir, args.device)
started = time.monotonic()
print("Loading:", engine.load(), flush=True)
loaded = time.monotonic()
print(engine.transcribe(samples, args.language), flush=True)
elapsed = time.monotonic() - loaded
print(f"Load: {loaded-started:.2f}s; inference: {elapsed:.2f}s; audio: {len(samples)/16000:.2f}s")
