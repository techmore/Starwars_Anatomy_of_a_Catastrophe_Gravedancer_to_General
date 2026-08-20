#!/bin/sh
# Install the isolated runtime needed for Bonsai 27B's 1-bit MLX weights.
# This intentionally does not modify the application's active Python runtime.
set -eu

RUNTIME="${GRAVEDANCER_BONSAI_RUNTIME:-$HOME/.local/share/gravedancer/bonsai-runtime}"
PYTHON_311="${PYTHON_311:-python3.11}"
MODEL="prism-ml/Bonsai-27B-mlx-1bit"
MLX_COMMIT="88c9c20"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required; install it from https://docs.astral.sh/uv/" >&2
    exit 1
fi
if ! command -v "$PYTHON_311" >/dev/null 2>&1; then
    echo "Python 3.11 is required; set PYTHON_311 to its executable path." >&2
    exit 1
fi

if [ ! -x "$RUNTIME/bin/python" ]; then
    uv venv --python "$(command -v "$PYTHON_311")" "$RUNTIME"
fi

uv pip install --python "$RUNTIME/bin/python" \
    "git+https://github.com/PrismML-Eng/mlx.git@$MLX_COMMIT" \
    "mlx-lm==0.31.2"

if [ "${1:-}" = "--download-model" ]; then
    "$RUNTIME/bin/python" - <<PY
from huggingface_hub import snapshot_download
print(snapshot_download("$MODEL"))
PY
fi

echo "Bonsai runtime ready: $RUNTIME/bin/python"
echo "The app detects this path automatically. To use a different location, set GRAVEDANCER_BONSAI_PYTHON."
