"""Tests for MCP mesh configuration helpers."""

import app.config as config_module
from app.config import reset_settings
from app.core.harness.mcp_config import (
    ExternalMCPServerConfig,
    external_tool_id,
    load_external_server_configs,
    mcp_external_enabled,
    normalize_tool_name,
    parse_builtin_tools_enabled,
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
        needs_user_patterns=["create_*", "push_*"],
        ingestion_tools=["search_code"],
        ingestion_patterns=["*_search"],
    )
    assert cfg.tool_needs_user("create_issue")
    assert cfg.tool_needs_user("push_branch")
    assert not cfg.tool_needs_user("search_code")
    # Substring must not match — only fnmatch / exact.
    assert not cfg.tool_needs_user("recreate_issue")
    assert cfg.tool_is_ingestion("search_code")
    assert cfg.tool_is_ingestion("code_search")
    assert not cfg.tool_is_ingestion("list_repos")


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


def test_builtin_tools_enabled_filter(monkeypatch, tmp_path):
    reset_settings()
    monkeypatch.setattr(config_module.settings, "mcp_external_enabled", True)
    monkeypatch.setattr(config_module.settings, "builtin_tools_enabled", "context7,tavily")
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


def test_parse_builtin_tools_enabled_wildcard(monkeypatch):
    reset_settings()
    monkeypatch.setattr(config_module.settings, "builtin_tools_enabled", "*")
    assert parse_builtin_tools_enabled() is None


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


def test_invalid_policy_default_skips_server(monkeypatch, tmp_path):
    """Typo in policy_default must fail closed (skip), not open the server."""
    from app.core.harness.mcp_config import clear_mcp_config_cache

    reset_settings()
    clear_mcp_config_cache()
    monkeypatch.setattr(config_module.settings, "mcp_external_enabled", True)
    monkeypatch.setattr(config_module.settings, "builtin_tools_enabled", "*")
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        """{
          "external_servers": [
            {
              "name": "bad",
              "command": "npx",
              "args": [],
              "policy_default": "not_a_real_policy"
            },
            {
              "name": "good",
              "command": "npx",
              "args": [],
              "policy_default": "needs_user"
            }
          ]
        }""",
        encoding="utf-8",
    )
    configs = load_external_server_configs(config_path)
    assert [c.name for c in configs] == ["good"]
    assert configs[0].policy_default == "needs_user"


def test_mcp_config_mtime_cache(monkeypatch, tmp_path):
    """Unchanged mtime reuses parsed JSON; rewrite + touch reloads."""
    import json
    import time

    from app.core.harness.mcp_config import clear_mcp_config_cache, load_mcp_config

    clear_mcp_config_cache()
    config_path = tmp_path / "mcp_config.json"
    config_path.write_text(
        json.dumps({"external_servers": [{"name": "a", "command": "npx", "args": []}]}),
        encoding="utf-8",
    )
    first = load_mcp_config(config_path)
    second = load_mcp_config(config_path)
    assert first is second  # same cached object

    time.sleep(0.02)
    config_path.write_text(
        json.dumps({"external_servers": [{"name": "b", "command": "npx", "args": []}]}),
        encoding="utf-8",
    )
    third = load_mcp_config(config_path)
    assert third is not first
    assert third["external_servers"][0]["name"] == "b"


def test_has_required_credentials_skips_resolve_env(monkeypatch):
    """Credential check must not depend on building a full subprocess env."""
    from app.core.harness.mcp_config import ExternalMCPServerConfig

    reset_settings()
    monkeypatch.setattr(config_module.settings, "github_personal_access_token", "")
    cfg = ExternalMCPServerConfig(
        name="github",
        command="npx",
        args=[],
        required_env=["GITHUB_PERSONAL_ACCESS_TOKEN"],
    )
    assert not cfg.has_required_credentials()
    monkeypatch.setattr(config_module.settings, "github_personal_access_token", "ghp_x")
    assert cfg.has_required_credentials()
