"""Transformers inspects Python source to discover lazy model imports."""
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = collect_data_files("transformers", include_py_files=True)
datas += copy_metadata("transformers", recursive=True)
hiddenimports = [
    "transformers.models.auto",
    "transformers.models.qwen3_asr.configuration_qwen3_asr",
    "transformers.models.qwen3_asr.feature_extraction_qwen3_asr",
    "transformers.models.qwen3_asr.modeling_qwen3_asr",
    "transformers.models.qwen3_asr.processing_qwen3_asr",
    "transformers.models.qwen3.configuration_qwen3",
    "transformers.models.qwen3.modeling_qwen3",
    "transformers.models.qwen2.tokenization_qwen2",
    "transformers.generation",
    "transformers.integrations.sdpa_attention",
]
module_collection_mode = "pyz+py"
