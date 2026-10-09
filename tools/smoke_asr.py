"""Download the official public sample and run a real CPU transcription."""
import subprocess
import sys
import urllib.request
from pathlib import Path

directory = Path(".test-data")
directory.mkdir(exist_ok=True)
sample = directory / "qwen-official-english.wav"
if not sample.exists():
    urllib.request.urlretrieve(
        "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_en.wav", sample)
raise SystemExit(subprocess.call([sys.executable, "tools/check_asr.py", str(sample),
                                "--language", "English", "--cache-dir", str(directory / "models")]))
