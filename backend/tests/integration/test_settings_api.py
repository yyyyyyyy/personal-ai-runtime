"""Integration tests for settings API — paths not covered by api smoke."""

from fastapi.testclient import TestClient


def test_update_llm_settings_persists_generation_params(client: TestClient):
    r = client.put(
        "/api/settings/llm",
        json={
            "default_provider": "deepseek",
            "temperature": 0.5,
            "max_tokens": 2048,
            "providers": [
                {
                    "id": "deepseek",
                    "name": "DeepSeek",
                    "type": "openai_compatible",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                    "api_key": "test-key",
                    "enabled": True,
                }
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["temperature"] == 0.5
    assert body["config"]["max_tokens"] == 2048


def test_update_email_settings(client: TestClient):
    r = client.put(
        "/api/settings/email",
        json={
            "user": "test@gmail.com",
            "password": "app-pass",
            "imap_host": "imap.gmail.com",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 465,
        },
    )
    assert r.status_code == 200
    assert r.json()["config"]["user"] == "test@gmail.com"


def test_get_capability_policy(client: TestClient):
    r = client.get("/api/settings/capability-policy")
    assert r.status_code == 200
    data = r.json()
    assert "auto_allow" in data
    assert "needs_user" in data
    assert "forbidden" in data
    assert "read_file" in data["auto_allow"]
    assert "write_file" in data["needs_user"]
    assert "send_email" in data["needs_user"]
    assert "web_search" in data["external_ingestion"]
