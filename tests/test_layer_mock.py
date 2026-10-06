"""End-to-end tests for bonsai_layer against a deterministic OpenAI-style mock."""
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "layer" / "bonsai_layer.py"
PYTHON = ROOT / "layer" / ".venv" / "bin" / "python"
TOOL_ID = "run-1"


class MockState:
    requests = []


class MockHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        MockState.requests.append(body)
        calls_tool = any(
            t.get("function", {}).get("name") == "run_python"
            for t in body.get("tools", [])
        )
        has_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        if calls_tool and not has_result:
            call = {"id": TOOL_ID, "type": "function", "function": {
                "name": "run_python", "arguments": json.dumps({"code": "print(6 * 7)"})}}
            if body.get("stream"):
                events = [
                    {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [
                        {"index": 0, "delta": {"reasoning_content": "checking"}, "finish_reason": None}]},
                    {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [
                        {"index": 0, "delta": {"tool_calls": [{"index": 0, "id": TOOL_ID,
                         "type": "function", "function": {"name": "run_python", "arguments":
                         json.dumps({"code": "print(6 * 7)"})}}]}, "finish_reason": None}]},
                    {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
                    {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [],
                     "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
                ]
                self._sse(events)
                return
            self._json({"id": "mock", "model": "mock", "choices": [{"index": 0, "message": {
                "role": "assistant", "content": "", "reasoning_content": "checking", "tool_calls": [call]},
                "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 3, "completion_tokens": 2,
                                                                  "total_tokens": 5}})
            return
        if body.get("stream"):
            events = [
                {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [
                    {"index": 0, "delta": {"reasoning_content": "done"}, "finish_reason": None}]},
                {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [
                    {"index": 0, "delta": {"content": "42"}, "finish_reason": None}]},
                {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "stop"}]},
                {"id": "mock", "model": "mock", "object": "chat.completion.chunk", "choices": [],
                 "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}},
                "[DONE]",
            ]
            self._sse(events)
            return
        self._json({"id": "mock", "model": "mock", "choices": [{"index": 0, "message": {
            "role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}})

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in events:
            data = "[DONE]" if event == "[DONE]" else json.dumps(event)
            self.wfile.write(("data: " + data + "\n\n").encode())
            self.wfile.flush()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LayerMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PYTHON.exists():
            raise unittest.SkipTest("run setup_mac.sh first to install wasmtime in layer/.venv")
        MockState.requests = []
        cls.mock_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.mock_thread = threading.Thread(target=cls.mock_server.serve_forever, daemon=True)
        cls.mock_thread.start()
        cls.port = free_port()
        env = dict(os.environ, BONSAI_LAYER_KEY="test-key")
        cls.layer_proc = subprocess.Popen([
            str(PYTHON), str(LAYER), "--host", "127.0.0.1", "--port", str(cls.port),
            "--upstream", f"http://127.0.0.1:{cls.mock_server.server_port}", "--reasoning-effort", "medium"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}/v1/chat/completions"
        deadline = time.time() + 10
        while time.time() < deadline:
            if cls.layer_proc.poll() is not None:
                raise RuntimeError("layer exited before becoming ready")
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("layer did not start")

    @classmethod
    def tearDownClass(cls):
        cls.layer_proc.terminate()
        cls.layer_proc.wait(timeout=10)
        cls.mock_server.shutdown()
        cls.mock_server.server_close()

    def post(self, payload, key="test-key"):
        req = urllib.request.Request(self.base, json.dumps(payload).encode(), {
            "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read())

    def test_plain_passthrough(self):
        result = self.post({"messages": [{"role": "user", "content": "hello"}], "code_interpreter": False})
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")

    def test_run_python_loop(self):
        result = self.post({"messages": [{"role": "user", "content": "Compute 6 times 7"}]})
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")
        self.assertEqual(result["interpreter_trace"][0]["stdout_head"], "42\n")

    def test_streamed_run_python_relays_reasoning(self):
        req = urllib.request.Request(self.base, json.dumps({
            "messages": [{"role": "user", "content": "Compute 6 times 7"}], "stream": True,
            "stream_options": {"include_usage": True}}).encode(), {
            "Content-Type": "application/json", "Authorization": "Bearer test-key"})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read().decode()
        self.assertIn('"reasoning_content": "checking"', data)
        self.assertIn('"reasoning_content": "done"', data)
        self.assertIn('"content": "42"', data)
        self.assertIn('"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}', data)
        self.assertNotIn('"name": "run_python"', data)

    def test_client_tools_passthrough(self):
        before = len(MockState.requests)
        payload = {"messages": [{"role": "user", "content": "Use my tool"}],
                   "tools": [{"type": "function", "function": {"name": "client_tool",
                             "parameters": {"type": "object"}}}]}
        result = self.post(payload)
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")
        sent = MockState.requests[before]
        self.assertEqual(sent, payload)

    def test_api_cards_injected_for_import_request(self):
        before = len(MockState.requests)
        self.post({"messages": [{"role": "user", "content": "Write a zip archive.\nimport zipfile"}],
                   "code_interpreter": False})
        sent = MockState.requests[before]
        self.assertIn("Reference: exact APIs of the Python modules", sent["messages"][0]["content"])
        self.assertIn("zipfile.ZipFile", sent["messages"][0]["content"])

    def test_lint_note_appended_to_matching_tool_result(self):
        before = len(MockState.requests)
        payload = {"messages": [
            {"role": "assistant", "tool_calls": [{"id": "bad-code", "type": "function", "function": {
                "name": "write_file", "arguments": json.dumps({"code": "import zipfile\nzipfile.make_archivez('x')"})}}]},
            {"role": "tool", "tool_call_id": "bad-code", "content": "write failed"},
            {"role": "user", "content": "Continue"}], "code_interpreter": False}
        self.post(payload)
        content = MockState.requests[before]["messages"][1]["content"]
        self.assertIn("[API check by the server", content)
        self.assertIn("make_archivez", content)

    def test_wrong_api_key_rejected_locally(self):
        before = len(MockState.requests)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post({"messages": [{"role": "user", "content": "hello"}]}, key="wrong")
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(len(MockState.requests), before)

    def test_code_interpreter_false_override(self):
        before = len(MockState.requests)
        self.post({"messages": [{"role": "user", "content": "Calculate 1+1"}], "code_interpreter": False})
        sent = MockState.requests[before]
        self.assertNotIn("tools", sent)
        self.assertNotIn("code_interpreter", sent)
        self.assertEqual(sent["reasoning_effort"], "medium")

    def test_fenced_code_no_tools_passthrough(self):
        before = len(MockState.requests)
        self.post({"messages": [{"role": "user", "content": "Run this:\n```python\nprint(1)\n```"}]})
        sent = MockState.requests[before]
        self.assertNotIn("tools", sent)
        self.assertEqual(sent["messages"][0]["content"], "Run this:\n```python\nprint(1)\n```")


if __name__ == "__main__":
    unittest.main()
