#!/usr/bin/env bash
# One-time setup for the WASI sandbox and PrismML-tested Bonsai 2 MLX server.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LAYER="$ROOT/layer"
RUNTIME="$LAYER/runtime"
URL='https://github.com/vmware-labs/webassembly-language-runtimes/releases/download/python%2F3.12.0%2B20231211-040d5a6/python-3.12.0-wasi-sdk-20.0.tar.gz'
SHA='6c1cddbb69ae09e87eee2906bdc70539bff5f2969818a6f8457d4e6a6eb67d4d'

if command -v python3.12 >/dev/null 2>&1; then
    PYTHON=$(command -v python3.12)
elif command -v uv >/dev/null 2>&1; then
    if ! uv python find 3.12 >/dev/null 2>&1; then
        uv python install 3.12
    fi
    PYTHON=$(uv python find 3.12)
else
    echo 'Python 3.12 is required (install python3.12 or uv).' >&2
    exit 1
fi

mkdir -p "$RUNTIME"
TARBALL="$RUNTIME/py.tar.gz"
curl --fail --location --retry 3 "$URL" --output "$TARBALL"
GOT=$(shasum -a 256 "$TARBALL" | awk '{print $1}')
echo "WASI runtime sha256: $GOT"
if [[ "$GOT" != "$SHA" ]]; then
    rm -f "$TARBALL"
    echo "WASI runtime checksum mismatch (expected $SHA, got $GOT)" >&2
    exit 1
fi

tar -xzf "$TARBALL" -C "$RUNTIME"
"$PYTHON" -m venv "$LAYER/.venv"
"$LAYER/.venv/bin/python" -m pip install --upgrade pip
"$LAYER/.venv/bin/python" -m pip install wasmtime
"$LAYER/.venv/bin/python" "$LAYER/wasi-python/canaries.py"

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo 'The MLX backend requires macOS on Apple Silicon.' >&2
    exit 1
fi
"$PYTHON" -m venv "$ROOT/.venv-vlm"
"$ROOT/.venv-vlm/bin/python" -m pip install \
    'mlx==0.32.2' 'mlx-vlm==0.7.2' 'transformers==5.14.1'
"$ROOT/.venv-vlm/bin/python" -c 'import mlx_vlm; print("MLX server dependencies ready (mlx-vlm", __import__("importlib.metadata", fromlist=["version"]).version("mlx-vlm") + ")")'
