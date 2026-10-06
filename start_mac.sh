#!/usr/bin/env bash
# Start the tested PrismML Bonsai 2 MLX server behind the Bonsai proxy.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HF_MODEL='prism-ml/Ternary-Bonsai-2-27B-mlx-2bit'
LOCAL_MODEL="$HOME/.lmstudio/models/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit"
if [[ -n "${BONSAI_MODEL:-}" ]]; then
    MODEL=$BONSAI_MODEL
elif [[ -f "$LOCAL_MODEL/config.json" && -f "$LOCAL_MODEL/model.safetensors" ]]; then
    MODEL=$LOCAL_MODEL
else
    MODEL=$HF_MODEL
fi
PORT=${BONSAI_PORT:-8080}
INNER=${BONSAI_INNER_PORT:-8081}
HOST=${BONSAI_HOST:-127.0.0.1}
THINKING_BUDGET=${BONSAI_THINKING_BUDGET:-4096}
REASONING_EFFORT=${BONSAI_REASONING_EFFORT:-medium}
MAX_TOKENS=${BONSAI_MAX_TOKENS:-8192}
STARTUP_TIMEOUT=${BONSAI_STARTUP_TIMEOUT:-900}
MLX_PYTHON=${BONSAI_MLX_PYTHON:-$ROOT/.venv-vlm/bin/python}
LAYER_PYTHON=${BONSAI_LAYER_PYTHON:-$ROOT/layer/.venv/bin/python}

valid_port() { [[ "$1" =~ ^[1-9][0-9]{0,4}$ ]] && (( 10#$1 <= 65535 )); }
valid_port "$PORT" || { echo 'BONSAI_PORT must be between 1 and 65535.' >&2; exit 1; }
valid_port "$INNER" || { echo 'BONSAI_INNER_PORT must be between 1 and 65535.' >&2; exit 1; }
(( PORT != INNER )) || { echo 'BONSAI_PORT and BONSAI_INNER_PORT must differ.' >&2; exit 1; }
[[ "$THINKING_BUDGET" =~ ^[0-9]+$ ]] || { echo 'BONSAI_THINKING_BUDGET must be a non-negative integer.' >&2; exit 1; }
[[ "$REASONING_EFFORT" == medium || "$REASONING_EFFORT" == low || "$REASONING_EFFORT" == xhigh ]] || {
    echo 'BONSAI_REASONING_EFFORT must be medium, low, or xhigh.' >&2; exit 1;
}
[[ "$MAX_TOKENS" =~ ^[1-9][0-9]*$ ]] || { echo 'BONSAI_MAX_TOKENS must be a positive integer.' >&2; exit 1; }
[[ "$STARTUP_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { echo 'BONSAI_STARTUP_TIMEOUT must be a positive integer.' >&2; exit 1; }
[[ -x "$MLX_PYTHON" ]] || { echo "MLX Python not found: $MLX_PYTHON (set BONSAI_MLX_PYTHON)." >&2; exit 1; }
"$MLX_PYTHON" -c 'import mlx_vlm' >/dev/null 2>&1 || {
    echo "mlx-vlm is unavailable in $MLX_PYTHON; use the Bonsai-demo tested .venv-vlm environment." >&2
    exit 1
}
[[ -x "$LAYER_PYTHON" ]] || { echo 'Layer venv missing; run bash setup_mac.sh first.' >&2; exit 1; }

if [[ -n "${BONSAI_LOG_DIR:-}" ]]; then
    LOG_DIR=$BONSAI_LOG_DIR
else
    LOG_DIR="${TMPDIR%/}/bonsai-layer-logs"
fi
mkdir -p "$LOG_DIR"
SERVER_LOG="$LOG_DIR/mlx-server.log"
LAYER_LOG="$LOG_DIR/bonsai-layer.log"
SERVER_PID=
LAYER_PID=
cleanup() {
    trap - EXIT INT TERM
    [[ -n "$LAYER_PID" ]] && kill "$LAYER_PID" 2>/dev/null || true
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
    [[ -n "$LAYER_PID" ]] && wait "$LAYER_PID" 2>/dev/null || true
    [[ -n "$SERVER_PID" ]] && wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$MLX_PYTHON" -m mlx_vlm.server --model "$MODEL" --host 127.0.0.1 --port "$INNER" \
    --enable-thinking --thinking-budget "$THINKING_BUDGET" --max-tokens "$MAX_TOKENS" \
    >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

ready=0
for _ in $(seq 1 "$STARTUP_TIMEOUT"); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "MLX server exited during startup; see $SERVER_LOG" >&2
        tail -n 40 "$SERVER_LOG" >&2 || true
        exit 1
    fi
    if curl --silent --fail "http://127.0.0.1:$INNER/v1/models" >/dev/null; then
        ready=1
        break
    fi
    sleep 1
done
if (( ! ready )); then
    echo "MLX server did not become ready; see $SERVER_LOG" >&2
    exit 1
fi

BONSAI_LAYER_KEY=${BONSAI_LAYER_KEY:-} "$LAYER_PYTHON" "$ROOT/layer/bonsai_layer.py" \
    --host "$HOST" --port "$PORT" --upstream "http://127.0.0.1:$INNER" \
    --reasoning-effort "$REASONING_EFFORT" >"$LAYER_LOG" 2>&1 &
LAYER_PID=$!
layer_ready=0
for _ in $(seq 1 30); do
    if ! kill -0 "$LAYER_PID" 2>/dev/null; then
        echo "Bonsai layer exited during startup; see $LAYER_LOG" >&2
        tail -n 40 "$LAYER_LOG" >&2 || true
        exit 1
    fi
    if curl --silent --fail "http://127.0.0.1:$PORT/v1/models" >/dev/null; then
        layer_ready=1
        break
    fi
    sleep 1
done
if (( ! layer_ready )); then
    echo "Bonsai layer did not become ready; see $LAYER_LOG" >&2
    exit 1
fi

echo "Bonsai layer on http://$HOST:$PORT -> MLX http://127.0.0.1:$INNER (model $MODEL; logs $LOG_DIR)"
wait "$LAYER_PID"
