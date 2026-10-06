# Bonsai layer for Apple Silicon

Run **Ternary Bonsai 2 27B** locally on an Apple Silicon Mac, with an MLX inference server and the Bonsai layer in front of it. The layer adds a sandboxed Python tool and exact Python API references to OpenAI-compatible chat requests.

This guide targets macOS on Apple Silicon (tested on an M1 Max, 32 GB). The repository also contains Windows/NVIDIA and Linux/CUDA research and build files; they are not needed for this setup. You can use the `layer/` proxy without building or running any CUDA code.

## What you need

- Apple Silicon Mac and macOS
- Python 3.12, or [`uv`](https://docs.astral.sh/uv/) so `setup_mac.sh` can install it
- Internet access for Python packages and, if the model is not already local, the model download (about 8.6 GB)
- Optional: the MLX pack already downloaded by LM Studio at:
  `~/.lmstudio/models/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit`

The model is **not** loaded through ordinary `mlx-lm`. Bonsai 2 uses PrismML's Hadamard-aware MLX loader, served here through the MLX-VLM runtime used by [PrismML's Bonsai demo](https://github.com/PrismML-Eng/Bonsai-demo). `setup_mac.sh` installs the pinned MLX packages into a separate `.venv-vlm`; the layer itself has its own venv with `wasmtime` and otherwise uses Python's standard library.

## Quick start

From the repository root:

```bash
bash setup_mac.sh
```

The setup script verifies the pinned CPython 3.12 WASI runtime's SHA-256, installs `wasmtime`, and runs 14 sandbox canaries. It also installs the PrismML-demo-tested MLX dependencies. The model weights are not part of this setup script.

Start both servers:

```bash
export BONSAI_LAYER_KEY="$(openssl rand -hex 24)"
./start_mac.sh
```

The launcher starts the MLX server on `127.0.0.1:8081` and the layer on `127.0.0.1:8080`. Press **Ctrl-C** to stop both. The launcher prints the model it selected and keeps logs in `${TMPDIR}/bonsai-layer-logs` by default.

By default, the launcher uses the model in `~/.lmstudio/models/` if it finds the expected Bonsai 2 MLX files there. Otherwise it asks MLX-VLM to download `prism-ml/Ternary-Bonsai-2-27B-mlx-2bit` from Hugging Face on first startup. To choose explicitly:

```bash
# Use the existing LM Studio model folder
BONSAI_MODEL="$HOME/.lmstudio/models/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit" ./start_mac.sh

# Or use/download the Hugging Face repo
BONSAI_MODEL="prism-ml/Ternary-Bonsai-2-27B-mlx-2bit" ./start_mac.sh
```

The local server's model ID is the selected model path. Check it with:

```bash
curl http://127.0.0.1:8080/v1/models
```

Use the returned `id` as the `model` value in chat requests. For the LM Studio path, it will look like `/Users/<you>/.lmstudio/models/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit`.

## Try the API

Plain request:

```bash
MODEL="$HOME/.lmstudio/models/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit"
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $BONSAI_LAYER_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly READY.\"}]}"
```

The layer offers `run_python` automatically when the client has not supplied its own tools. For example:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $BONSAI_LAYER_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Use Python to calculate 6 times 7, then give me the result.\"}]}"
```

Non-streaming responses include an `interpreter_trace` showing the sandbox code and result metadata. Streaming clients receive reasoning and answer deltas as they arrive; internal `run_python` tool-call deltas are withheld. If the client requests `stream_options.include_usage`, the layer emits usage summed across the model's tool-loop rounds.

## What the layer does

- **Sandboxed Python:** offers the model a `run_python` tool backed by CPython 3.12 on WASI. Each run has a fresh working directory, no host files, network sockets, or subprocesses, a memory cap, and a time limit. The user's text is available to the program as `input.txt`.
- **API cards:** for coding requests, appends exact API information for relevant Python modules to the **end of the first user message**.
- **API checks:** checks Python code from earlier tool calls against the sandbox runtime and appends detected issues to the matching tool result.
- **Tool loop:** handles up to 12 interpreter rounds, then asks for a final answer.
- **API key:** when `BONSAI_LAYER_KEY` is set, chat-completion requests without the matching bearer key receive HTTP 401.

Requests that bring their own tools pass through without layer-added cards or defaults, unless the client explicitly opts in with `"code_interpreter": true`. Conversations containing fenced code blocks and no client tools also pass through unchanged, so code-running agents can keep using their own execution environment. To explicitly disable the interpreter for a request, send `"code_interpreter": false`.

## Mac launcher settings

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `BONSAI_MODEL` | LM Studio path if present; otherwise Hugging Face ID | Model directory or repo ID |
| `BONSAI_PORT` | `8080` | Client-facing layer port |
| `BONSAI_INNER_PORT` | `8081` | Loopback-only MLX server port |
| `BONSAI_HOST` | `127.0.0.1` | Layer bind address |
| `BONSAI_LAYER_KEY` | unset | Optional bearer key required by the layer |
| `BONSAI_THINKING_BUDGET` | `4096` | MLX server's default thinking-token budget |
| `BONSAI_MAX_TOKENS` | `8192` | MLX server's default output-token limit |
| `BONSAI_REASONING_EFFORT` | `medium` | Default effort for layer-managed requests that omit it |
| `BONSAI_MLX_PYTHON` | `.venv-vlm/bin/python` | Python executable with the tested `mlx-vlm` runtime |
| `BONSAI_LAYER_PYTHON` | `layer/.venv/bin/python` | Python executable with `wasmtime` |
| `BONSAI_STARTUP_TIMEOUT` | `900` | Seconds allowed for MLX model startup |
| `BONSAI_LOG_DIR` | `${TMPDIR}/bonsai-layer-logs` | Server and layer log directory |

The MLX server provides a default thinking budget, but an API request can override it with `thinking_budget`. The layer defaults missing reasoning effort to `medium` for requests it handles. PrismML documents that `low` behaves close to `xhigh`; `medium` is the recommended shorter-thinking setting. Client-tool requests are passed through, so set their effort explicitly in the request if needed.

For LAN access, set `BONSAI_HOST=0.0.0.0` and provide a strong `BONSAI_LAYER_KEY`. Do not expose the server without authentication; the MLX inner server remains bound to loopback.

## Tests and smoke checks

After setup, run the tests without loading a model:

```bash
layer/.venv/bin/python -m unittest discover tests -v
```

The mock-upstream tests cover regular and streamed proxying, interpreter loops, reasoning deltas, client-tool passthrough, API cards, lint notes, API-key rejection, and the `code_interpreter:false` override.

To smoke-test a running MLX server manually:

```bash
curl http://127.0.0.1:8080/v1/models
```

Then send the API examples above. A coding request should return a normal answer plus `interpreter_trace`; a streamed request should relay reasoning and answer text without exposing the layer's internal tool call.

## Verified on Apple Silicon

The current Mac setup was exercised on arm64 macOS with Python 3.12. The WASI runtime checksum matched and all 14 isolation canaries passed. With `mlx-vlm 0.7.2`, the local LM Studio Bonsai 2 MLX pack loaded successfully; its Qwen3-Coder-style XML tool calls were returned as parsed OpenAI `tool_calls`. Real requests through the layer completed a sandboxed `print(6*7)` and returned `42`, in both non-streaming and streaming modes.

## License

This repository is MIT-licensed. The Bonsai model pack has its own license and terms; consult the [model card](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-mlx-2bit) before using or redistributing the weights.
