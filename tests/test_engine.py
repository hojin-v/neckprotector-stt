import tempfile
import unittest
from pathlib import Path

from sori.engine import QwenEngine, MODEL_ID


class CacheTests(unittest.TestCase):
    def test_missing_or_partial_download_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = QwenEngine(Path(directory))
            self.assertFalse(engine.cache_available())
            snapshot = Path(directory) / ("models--" + MODEL_ID.replace("/", "--")) / "snapshots" / "revision"
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_text("{}")
            (snapshot / "model.safetensors").touch()
            self.assertFalse(engine.cache_available())

    def test_complete_cached_download_can_start_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / ("models--" + MODEL_ID.replace("/", "--")) / "snapshots" / "revision"
            snapshot.mkdir(parents=True)
            for name in ("config.json", "processor_config.json", "tokenizer.json", "chat_template.jinja", "model.safetensors"):
                (snapshot / name).write_bytes(b"data")
            self.assertTrue(QwenEngine(Path(directory)).cache_available())


if __name__ == "__main__":
    unittest.main()
