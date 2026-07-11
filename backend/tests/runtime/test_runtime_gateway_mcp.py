"""Tests for the Runtime Gateway MCP server (Phase 3.2 dogfood).

Verifies the stdio JSON-RPC protocol handling and that tools dispatch
correctly to the HTTP @public endpoints (mocked).
"""

import io
import json

from mcp_servers.runtime_gateway import server


class TestMcpProtocol:
    def test_initialize(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        resp = server._handle(req)
        assert resp["id"] == 1
        assert resp["result"]["serverInfo"]["name"] == "personal-ai-runtime"
        assert "tools" in resp["result"]["capabilities"]

    def test_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        resp = server._handle(req)
        names = [t["name"] for t in resp["result"]["tools"]]
        assert "recall" in names
        assert "store_memory" in names

    def test_unknown_method_returns_error(self):
        req = {"jsonrpc": "2.0", "id": 3, "method": "nonexistent"}
        resp = server._handle(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_notification_no_response(self):
        req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = server._handle(req)
        assert resp == {}


class TestToolRecall:
    def test_recall_combines_memory_and_knowledge(self, monkeypatch):
        responses = iter([
            [{"id": "m1", "content": "User likes Rust"}],  # memory search
            {"results": [{"content": "Rust ownership guide", "metadata": {"source_file": "rust.md"}}], "total": 1},
        ])

        def fake_http(method, path, body=None):
            return next(responses)

        monkeypatch.setattr(server, "_http", fake_http)
        output = server.tool_recall("Rust")
        assert "User likes Rust" in output
        assert "rust.md" in output

    def test_recall_handles_empty(self, monkeypatch):
        monkeypatch.setattr(server, "_http", lambda *a, **k: [] if "memory" in a[1] else {"results": []})
        output = server.tool_recall("nothing")
        assert "未找到" in output


class TestToolStoreMemory:
    def test_store_returns_id(self, monkeypatch):
        monkeypatch.setattr(server, "_http", lambda *a, **k: {"id": "mem-123", "status": "ok"})
        output = server.tool_store_memory("I prefer dark mode")
        assert "mem-123" in output
        assert "dark mode" in output

    def test_store_handles_error(self, monkeypatch):
        monkeypatch.setattr(server, "_http", lambda *a, **k: {"error": "unauthorized"})
        output = server.tool_store_memory("test")
        assert "存储失败" in output


class TestMainLoop:
    def test_main_processes_stdin_lines(self, monkeypatch, capsys):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            "",  # empty line should be skipped
        ]
        monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines) + "\n"))
        server.main()
        captured = capsys.readouterr()
        responses = [json.loads(l) for l in captured.out.strip().split("\n") if l]
        assert len(responses) == 2
        assert responses[0]["result"]["serverInfo"]["name"] == "personal-ai-runtime"
        assert responses[1]["result"]["tools"]
