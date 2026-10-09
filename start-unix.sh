#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
    echo "You do not need a separate Python installation." >&2
    exit 1
fi
case "$(uname -s)" in
    Darwin) export UV_PROJECT_ENVIRONMENT=.venv-macos ;;
    *) export UV_PROJECT_ENVIRONMENT=.venv-linux ;;
esac
sori_asr_extra="${SORI_ASR_EXTRA:-asr}"
case "$sori_asr_extra" in
    asr|asr-cuda) ;;
    *) echo "SORI_ASR_EXTRA must be asr or asr-cuda." >&2; exit 1 ;;
esac
if [[ -n "${WSL_INTEROP:-}" ]]; then
    echo "WSL: Windows app dictation requires start-windows.bat running on Windows." >&2
fi
uv sync --locked --managed-python --extra "$sori_asr_extra"
exec uv run --no-sync python -m sori "$@"
