"""Integration tests for data sovereignty system API."""

from starlette.testclient import TestClient


def test_export_requires_confirm(client: TestClient):
    r = client.post("/api/system/export", json={})
    assert r.status_code == 400
    assert "EXPORT_ALL_DATA" in r.json()["detail"]


def test_export_with_confirm(client: TestClient):
    r = client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    )
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    data = r.json()
    assert data["format"] == "snapshot"
    assert "event_log" in data


def test_export_stream_matches_snapshot_wire_format(client: TestClient):
    """Streamed plaintext export must parse to the same schema as snapshot()."""
    from app.core.runtime.kernel_instance import kernel

    kernel.emit_event(
        "NotificationCreated",
        "notification",
        "exp_stream_1",
        payload={"title": "stream-me"},
    )
    streamed = client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    ).json()
    snap = kernel.snapshot()
    assert streamed["format"] == snap["format"]
    assert streamed["counts"]["event_log"] == snap["counts"]["event_log"]
    assert [e["id"] for e in streamed["event_log"]] == [e["id"] for e in snap["event_log"]]
    assert len(streamed["conversations"]) == len(snap["conversations"])
    assert len(streamed["messages"]) == len(snap["messages"])


def test_import_read_only_validate(client: TestClient):
    export = client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    ).json()
    r = client.post(
        "/api/system/import",
        json={"data": export, "read_only": True},
    )
    assert r.status_code == 200


def test_import_write_requires_confirm(authed_client: TestClient):
    export = authed_client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    ).json()
    r = authed_client.post(
        "/api/system/import",
        json={"data": export, "read_only": False},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 400
    assert "DESTROY_AND_IMPORT" in r.json()["detail"]


def test_import_write_without_auth_token_allowed_with_confirm(client: TestClient, monkeypatch):
    """When AUTH_TOKEN is unset, confirm code alone gates write import."""
    seen: dict[str, object] = {}

    def fake_import(snapshot, read_only=True):
        seen["read_only"] = read_only
        return {"status": "imported", "read_only": read_only}

    monkeypatch.setattr("app.api.system.kernel.restore", fake_import)
    r = client.post(
        "/api/system/import",
        json={"data": {}, "read_only": False, "confirm": "DESTROY_AND_IMPORT"},
    )
    assert r.status_code == 200
    assert seen["read_only"] is False


def test_import_write_with_confirm(authed_client: TestClient, monkeypatch):
    export = authed_client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    ).json()
    seen: dict[str, object] = {}

    def fake_import(snapshot, read_only=True):
        seen["read_only"] = read_only
        seen["snapshot"] = snapshot
        return {"status": "imported", "read_only": read_only}

    monkeypatch.setattr("app.api.system.kernel.restore", fake_import)
    r = authed_client.post(
        "/api/system/import",
        json={
            "data": export,
            "read_only": False,
            "confirm": "DESTROY_AND_IMPORT",
        },
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 200
    assert seen["read_only"] is False
    assert seen["snapshot"] == export


def test_destroy_requires_confirm(authed_client: TestClient):
    r = authed_client.request(
        "DELETE",
        "/api/system/data",
        json={"confirm": "WRONG"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 400
    assert "DESTROY_ALL_DATA" in r.json()["detail"]


def test_destroy_without_auth_token_allowed_with_confirm(client: TestClient, monkeypatch):
    """When AUTH_TOKEN is unset, confirm code alone gates destroy."""
    monkeypatch.setattr(
        "app.api.system.kernel.erase",
        lambda: {"status": "destroyed", "message": "test"},
    )
    r = client.request(
        "DELETE",
        "/api/system/data",
        json={"confirm": "DESTROY_ALL_DATA"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "destroyed"


def test_destroy_success_with_confirm(authed_client: TestClient, monkeypatch):
    monkeypatch.setattr(
        "app.api.system.kernel.erase",
        lambda: {"status": "destroyed", "message": "test"},
    )
    r = authed_client.request(
        "DELETE",
        "/api/system/data",
        json={"confirm": "DESTROY_ALL_DATA"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "destroyed"


def test_health_includes_startup_diagnostics(client: TestClient):
    r = client.get("/api/system/health")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "personal-ai-runtime"
    startup = data["startup"]
    assert startup is not None
    assert startup["status"] in ("ok", "degraded")
    storage = startup["checks"]["storage"]
    assert storage["data_dir_exists"] is True
    assert "data_dir" not in storage
    assert "warnings" not in startup
    assert "warning_count" in startup


def test_health_full_startup_with_auth(authed_client: TestClient):
    r = authed_client.get(
        "/api/system/health",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 200
    startup = r.json()["startup"]
    assert startup is not None
    assert "warnings" in startup
    assert "data_dir" in startup["checks"]["storage"]


# --- Encrypted export/import confirm-code enforcement ---

def test_encrypted_export_requires_confirm(client: TestClient):
    r = client.post(
        "/api/system/export/encrypted",
        json={"password": "longpassword"},
    )
    assert r.status_code == 400
    assert "EXPORT_ALL_DATA" in r.json()["detail"]


def test_encrypted_import_requires_confirm(authed_client: TestClient):
    r = authed_client.post(
        "/api/system/import/encrypted",
        json={"data": "blob", "password": "longpassword"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 400
    assert "DESTROY_AND_IMPORT" in r.json()["detail"]


def test_encrypted_import_wrong_confirm_rejected(authed_client: TestClient):
    r = authed_client.post(
        "/api/system/import/encrypted",
        json={
            "data": "blob",
            "password": "longpassword",
            "confirm": "WRONG_CODE",
        },
        headers={"Authorization": "Bearer test-secret"},
    )
    assert r.status_code == 400
    assert "DESTROY_AND_IMPORT" in r.json()["detail"]


def test_destructive_ops_rejected_by_middleware_when_auth_configured(authed_client: TestClient):
    """When AUTH_TOKEN is set, missing Bearer is rejected before the handler."""
    from app.core.rate_limit import reset_rate_limits

    r = authed_client.request(
        "DELETE",
        "/api/system/data",
        json={"confirm": "DESTROY_ALL_DATA"},
    )
    assert r.status_code == 401
    reset_rate_limits()
    r2 = authed_client.post(
        "/api/system/import",
        json={"data": {}, "read_only": False, "confirm": "DESTROY_AND_IMPORT"},
    )
    assert r2.status_code == 401
    reset_rate_limits()
    r3 = authed_client.post(
        "/api/system/import/encrypted",
        json={"data": "blob", "password": "longpassword", "confirm": "DESTROY_AND_IMPORT"},
    )
    assert r3.status_code == 401
