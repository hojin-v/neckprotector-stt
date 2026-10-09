from __future__ import annotations

import os
from pathlib import Path

import numpy as np

MODEL_ID = "Qwen/Qwen3-ASR-0.6B-hf"


class QwenEngine:
    """Official Transformers backend. No vLLM or FlashAttention requirement."""

    def __init__(self, cache: Path, device: str = "auto"):
        self.cache, self.requested_device = cache, device
        self.model = self.processor = None
        self.device = "cpu"

    def cache_available(self) -> bool:
        snapshots = self.cache / ("models--" + MODEL_ID.replace("/", "--")) / "snapshots"
        required = ("config.json", "processor_config.json", "tokenizer.json", "chat_template.jinja", "model.safetensors")
        try:
            return any(all((snapshot / name).is_file() and (snapshot / name).stat().st_size > 0
                           for name in required) for snapshot in snapshots.iterdir() if snapshot.is_dir())
        except OSError:
            return False

    def load(self) -> str:
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM

        self.device = self.requested_device
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else ("xpu" if hasattr(torch, "xpu") and torch.xpu.is_available() else "cpu")
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA를 사용할 수 없습니다. CPU 또는 자동을 선택해 주세요.")
        if self.device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("Apple GPU를 사용할 수 없습니다. CPU 또는 자동을 선택해 주세요.")
        if self.device == "xpu" and not (hasattr(torch, "xpu") and torch.xpu.is_available()):
            raise RuntimeError("Intel GPU를 사용할 수 없습니다. XPU용 실행 환경과 지원 드라이버가 필요합니다. 현재 배포본에서는 CPU를 선택해 주세요.")
        dtype = torch.float16 if self.device in {"cuda", "xpu", "mps"} else torch.float32
        torch.set_num_threads(max(1, min(8, (os.cpu_count() or 4) // 2)))
        cached = self.cache_available()
        self.processor = AutoProcessor.from_pretrained(MODEL_ID, cache_dir=str(self.cache), local_files_only=cached)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            MODEL_ID, cache_dir=str(self.cache), local_files_only=cached, dtype=dtype, attn_implementation="sdpa",
        ).to(self.device).eval()
        return self.device

    def transcribe(self, samples: np.ndarray, language: str) -> str:
        import torch
        if self.model is None:
            raise RuntimeError("음성 인식 모델을 먼저 준비해 주세요.")
        request = {"audio": np.asarray(samples, dtype=np.float32), "processor_kwargs": {"audio_kwargs": {"sampling_rate": 16000}}}
        if language != "auto":
            request["language"] = language
        inputs = self.processor.apply_transcription_request(**request).to(self.model.device, self.model.dtype)
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=256, do_sample=False)
        generated = output[:, inputs["input_ids"].shape[1]:]
        return self.processor.decode(generated, return_format="transcription_only")[0].strip()
