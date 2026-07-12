"""Fake OpenAI-compatible LLM server for E2E tests.

Returns deterministic streaming responses so real-backend E2E tests can
verify SSE text deltas and the approval chain without a real LLM key.

Protocol:
- Default: stream plain text tokens only.
- When the last user message contains ``E2E_TOOL_APPROVAL``, stream a
  ``write_file`` tool call with valid arguments (path + content).
- After a tool-role message is present, return a short follow-up text.
"""

from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOL_TRIGGER = "E2E_TOOL_APPROVAL"


def _write_path() -> str:
    return os.environ.get("E2E_WRITE_PATH") or os.path.abspath("e2e_write_test.txt")


def _tool_args() -> str:
    return json.dumps({
        "path": _write_path(),
        "content": "hello from e2e",
    })


class FakeLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}
        messages = body.get("messages", [])
        stream = bool(body.get("stream", False))

        last_user = ""
        last_message = messages[-1] if messages else {}
        if last_message.get("role") == "user":
            content = last_message.get("content") or ""
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            last_user = str(content)

        want_tool = TOOL_TRIGGER in last_user
        after_tool = any(msg.get("role") == "tool" for msg in messages)
        if stream:
            self._sse_stream(want_tool=want_tool, after_tool=after_tool)
        else:
            self._json_response(
                200,
                self._nonstream(want_tool=want_tool, after_tool=after_tool),
            )

    def _nonstream(self, *, want_tool: bool, after_tool: bool = False) -> dict:
        if want_tool:
            return {
                "id": "fake-ns",
                "object": "chat.completion",
                "model": "fake-e2e",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_fake_1",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": _tool_args(),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
            }
        content = (
            "Wrote the file successfully."
            if after_tool
            else "Hello, world!"
        )
        return {
            "id": "fake-ns",
            "object": "chat.completion",
            "model": "fake-e2e",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
        }

    def _sse_stream(self, *, want_tool: bool, after_tool: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        if want_tool:
            chunks = [
                {
                    "id": "fake-tc",
                    "object": "chat.completion.chunk",
                    "model": "fake-e2e",
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [{
                                "index": 0,
                                "id": "call_fake_1",
                                "type": "function",
                                "function": {"name": "write_file", "arguments": ""},
                            }],
                        },
                        "finish_reason": None,
                    }],
                },
                {
                    "id": "fake-tc",
                    "object": "chat.completion.chunk",
                    "model": "fake-e2e",
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "function": {
                                    "arguments": _tool_args(),
                                },
                            }],
                        },
                        "finish_reason": None,
                    }],
                },
                {
                    "id": "fake-tc",
                    "object": "chat.completion.chunk",
                    "model": "fake-e2e",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "tool_calls",
                    }],
                },
            ]
        else:
            pieces = (
                ["Wrote ", "the ", "file ", "successfully."]
                if after_tool
                else ["Hello", ", ", "world", "!"]
            )
            chunks = []
            for i, piece in enumerate(pieces):
                chunks.append({
                    "id": f"fake-{i}",
                    "object": "chat.completion.chunk",
                    "model": "fake-e2e",
                    "choices": [{
                        "index": 0,
                        "delta": {"content": piece},
                        "finish_reason": None,
                    }],
                })
            chunks.append({
                "id": "fake-end",
                "object": "chat.completion.chunk",
                "model": "fake-e2e",
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            })

        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.15)

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _json_response(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 19999
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeLLMHandler)
    print(f"FakeLLM listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
