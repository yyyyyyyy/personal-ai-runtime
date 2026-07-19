"""Tests for the Runtime Gateway MCP server (FastMCP + HTTP tools)."""

import asyncio
import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from mcp_servers.runtime_gateway import server
from mcp_servers.runtime_gateway.http_client import HttpResult, reset_base_url_cache
from mcp_servers.runtime_gateway.tools import ToolOutput, resolve_enabled_tools


class TestFastMcpProtocol:
    def test_list_tools_default_all(self):
        tools = asyncio.run(server.mcp.list_tools())
        names = {t.name for t in tools}
        assert names == {
            "recall",
            "store_memory",
            "list_pending_approvals",
            "recent_timeline",
        }

    def test_server_info_version(self):
        assert server.mcp.name == "personal-ai-runtime"
        assert server.mcp._mcp_server.version == server.GATEWAY_VERSION

    def test_call_tool_sets_error_via_exception(self, monkeypatch):
        monkeypatch.setattr(
            server,
            "tool_store_memory",
            lambda *a, **k: ToolOutput("fail", is_error=True),
        )
        with pytest.raises(ToolError, match="fail"):
            asyncio.run(server.mcp.call_tool("store_memory", {"content": "x"}))


class TestToolRecall:
    def test_recall_combines_memory_and_knowledge(self, monkeypatch):
        responses = iter([
            HttpResult(ok=True, data=[{"id": "m1", "content": "User likes Rust"}]),
            HttpResult(
                ok=True,
                data={
                    "results": [
                        {
                            "content": "Rust ownership guide",
                            "metadata": {"source_file": "rust.md"},
                        }
                    ],
                    "total": 1,
                },
            ),
        ])

        def fake_http(method, path, body=None):
            assert method == "GET"
            assert body is None
            return next(responses)

        monkeypatch.setattr("mcp_servers.runtime_gateway.tools.request", fake_http)
        output = server.tool_recall("Rust")
        assert not output.is_error
        assert "User likes Rust" in output.text
        assert "rust.md" in output.text

    def test_recall_uses_get_for_knowledge(self, monkeypatch):
        seen: list[tuple[str, str]] = []

        def fake_http(method, path, body=None):
            seen.append((method, path))
            if "memory" in path:
                return HttpResult(ok=True, data=[])
            return HttpResult(ok=True, data={"results": []})

        monkeypatch.setattr("mcp_servers.runtime_gateway.tools.request", fake_http)
        server.tool_recall("q")
        assert any(m == "GET" and path.startswith("/api/knowledge/search?") for m, path in seen)
        assert not any(m == "POST" for m, _ in seen)

    def test_recall_handles_empty(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda *a, **k: (
                HttpResult(ok=True, data=[])
                if "memory" in a[1]
                else HttpResult(ok=True, data={"results": []})
            ),
        )
        output = server.tool_recall("nothing")
        assert "未找到" in output.text
        assert not output.is_error

    def test_recall_wrapped_memory_payload(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda method, path, body=None: (
                HttpResult(ok=True, data={"items": [{"content": "wrapped"}]})
                if "memory" in path
                else HttpResult(ok=True, data={"results": []})
            ),
        )
        output = server.tool_recall("x")
        assert "wrapped" in output.text

    def test_recall_both_sources_fail_is_error(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda *a, **k: HttpResult(ok=False, status=401, error="HTTP 401"),
        )
        output = server.tool_recall("x")
        assert output.is_error
        assert "memory search error" in output.text
        assert "knowledge search error" in output.text

    def test_recall_rejects_empty_query(self):
        output = server.tool_recall("   ")
        assert output.is_error


class TestToolStoreMemory:
    def test_store_returns_id(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda *a, **k: HttpResult(ok=True, data={"id": "mem-123", "status": "ok"}),
        )
        output = server.tool_store_memory("I prefer dark mode")
        assert not output.is_error
        assert "mem-123" in output.text
        assert "dark mode" in output.text

    def test_store_handles_error(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda *a, **k: HttpResult(ok=False, status=401, error="HTTP 401"),
        )
        output = server.tool_store_memory("test")
        assert output.is_error
        assert "存储失败" in output.text
        assert "HTTP 401" in output.text

    def test_store_rejects_empty_content(self):
        output = server.tool_store_memory("  ")
        assert output.is_error


class TestApprovalsAndTimeline:
    def test_list_pending_approvals(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda *a, **k: HttpResult(
                ok=True,
                data=[
                    {
                        "id": "ap-1",
                        "action": "shell_exec",
                        "flow_label": "对话 (chat_1)",
                        "reason": "run ls",
                    }
                ],
            ),
        )
        output = server.tool_list_pending_approvals()
        assert not output.is_error
        assert "ap-1" in output.text
        assert "shell_exec" in output.text

    def test_recent_timeline(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_servers.runtime_gateway.tools.request",
            lambda *a, **k: HttpResult(
                ok=True,
                data={
                    "items": [
                        {
                            "ts": "2026-07-19T12:00:00+00:00",
                            "description": "AI 记住了新信息: likes tea",
                        }
                    ]
                },
            ),
        )
        output = server.tool_recent_timeline()
        assert not output.is_error
        assert "likes tea" in output.text


class TestBaseUrlValidation:
    def test_rejects_remote_by_default(self):
        with pytest.raises(ValueError, match="not local"):
            server._validate_base_url("https://evil.example/api")

    def test_allows_remote_with_flag(self, monkeypatch):
        monkeypatch.setenv("PAR_ALLOW_REMOTE", "1")
        assert (
            server._validate_base_url("https://example.com:8443")
            == "https://example.com:8443"
        )

    def test_import_does_not_pin_invalid_url(self, monkeypatch):
        # Lazy validation: bad env should not break import of http_client helpers.
        from mcp_servers.runtime_gateway import http_client as hc

        monkeypatch.setenv("PAR_ALLOW_REMOTE", "0")
        reset_base_url_cache()
        monkeypatch.setattr(hc, "_RAW_BASE_URL", "https://evil.example")
        with pytest.raises(ValueError, match="not local"):
            hc.get_base_url()
        reset_base_url_cache()


class TestToolWhitelist:
    def test_resolve_core(self):
        assert resolve_enabled_tools("core") == frozenset({"recall", "store_memory"})

    def test_resolve_all(self):
        assert "recent_timeline" in resolve_enabled_tools("all")

    def test_resolve_explicit(self):
        assert resolve_enabled_tools("recall,recent_timeline") == frozenset(
            {"recall", "recent_timeline"}
        )


class TestUnwrap:
    def test_unwrap_raises_on_error(self):
        with pytest.raises(ValueError, match="boom"):
            server._unwrap(ToolOutput("boom", is_error=True))

    def test_unwrap_returns_text(self):
        assert server._unwrap(ToolOutput("ok")) == "ok"


class TestLogging:
    def test_configure_logging_json(self, monkeypatch, capsys):
        monkeypatch.setenv("PAR_LOG_JSON", "1")
        server._configure_logging()
        server.logger.info("json-log-line")
        err = capsys.readouterr().err
        for line in err.splitlines():
            if "json-log-line" in line:
                payload = json.loads(line)
                assert payload["message"] == "json-log-line"
                assert payload["level"] == "INFO"
                return
        raise AssertionError(f"expected JSON log line, got: {err!r}")
