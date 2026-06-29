"""Tests for MCP mesh configuration helpers."""

import app.config as config_module
from app.config import reset_settings
from app.core.harness.mcp_config import (
    ExternalMCPServerConfig,
    external_tool_id,
    load_external_server_configs,
    mcp_external_enabled,
    normalize_tool_name,
    parse_mcp_servers_enabled,
)


def test_normalize_tool_name():
    assert normalize_tool_name("query-docs") == "query_docs"
    assert normalize_tool_name("API-post-search") == "API_post_search"


def test_external_tool_id():
    assert external_tool_id("context7", "query-docs") == "context7_query_docs"


def test_server_policy_patterns():
    cfg = ExternalMCPServerConfig(
        name="github",
        command="npx",
        args=[],
        needs_user_patterns=["create_", "push_"],
        ingestion_tools=["search_code"],
    )
    assert cfg.tool_needs_user("create_issue")
    assert not cfg.tool_needs_user("search_code")
    assert cfg.tool_is_ingestion("search_code")


def test_enabled_tools_filter():
    cfg = ExternalMCPServerConfig(
        name="brave",
        command="npx",
        args=[],
        enabled_tools=["brave_web_search"],
    )
    assert cfg.should_expose_tool("brave_web_search")
    assert not cfg.should_expose_tool("brave_news_search")


def test_external_servers_disabled_by_settings(monkeypatch):
    reset_settings()
    monkeypatch.setattr(config_module.settings, "mcp_external_enabled", False)
    assert load_external_server_configs() == []


def test_mcp_servers_enabled_filter(monkeypatch, tmp_path):
    reset_settings()
    monkeypatch.setattr(config_module.settings, "mcp_external_enabled", True)
    monkeypatch.setattr(config_module.settings, "mcp_servers_enabled", "context7,tavily")
    assert mcp_external_enabled() is True
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        """{
          "external_servers": [
            {"name": "context7", "command": "npx", "args": []},
            {"name": "playwright", "command": "npx", "args": []}
          ]
        }""",
        encoding="utf-8",
    )
    configs = load_external_server_configs(config_path)
    assert [c.name for c in configs] == ["context7"]


def test_parse_mcp_servers_enabled_wildcard(monkeypatch):
    reset_settings()
    monkeypatch.setattr(config_module.settings, "mcp_servers_enabled", "*")
    assert parse_mcp_servers_enabled() is None


def test_github_requires_token(monkeypatch, tmp_path):
    reset_settings()
    monkeypatch.setattr(config_module.settings, "mcp_external_enabled", True)
    monkeypatch.setattr(config_module.settings, "github_personal_access_token", "")
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        """{
          "external_servers": [{
            "name": "github",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "required_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"]
          }]
        }""",
        encoding="utf-8",
    )
    configs = load_external_server_configs(config_path)
    assert len(configs) == 1
    assert not configs[0].is_available()

    monkeypatch.setattr(config_module.settings, "github_personal_access_token", "ghp_test")
    assert configs[0].is_available()
    assert configs[0].resolve_env()["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_test"
