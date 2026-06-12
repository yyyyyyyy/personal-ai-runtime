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
    data = r.json()
    assert data["version"]
    assert "event_log" in data


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


def test_import_write_requires_confirm(client: TestClient):
    export = client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    ).json()
    r = client.post(
        "/api/system/import",
        json={"data": export, "read_only": False},
    )
    assert r.status_code == 400
    assert "DESTROY_AND_IMPORT" in r.json()["detail"]


def test_import_write_with_confirm(client: TestClient, monkeypatch):
    export = client.post(
        "/api/system/export",
        json={"confirm": "EXPORT_ALL_DATA"},
    ).json()
    seen: dict[str, object] = {}

    def fake_import(snapshot, read_only=True):
        seen["read_only"] = read_only
        seen["snapshot"] = snapshot
        return {"status": "imported", "read_only": read_only}

    monkeypatch.setattr("app.api.system.digital_legacy.import_all", fake_import)
    r = client.post(
        "/api/system/import",
        json={
            "data": export,
            "read_only": False,
            "confirm": "DESTROY_AND_IMPORT",
        },
    )
    assert r.status_code == 200
    assert seen["read_only"] is False
    assert seen["snapshot"] == export


def test_destroy_requires_confirm(client: TestClient):
    r = client.request("DELETE", "/api/system/data", json={"confirm": "WRONG"})
    assert r.status_code == 400
    assert "DESTROY_ALL_DATA" in r.json()["detail"]


def test_destroy_success_with_confirm(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        "app.api.system.digital_legacy.destroy_all",
        lambda: {"status": "destroyed", "message": "test"},
    )
    r = client.request(
        "DELETE",
        "/api/system/data",
        json={"confirm": "DESTROY_ALL_DATA"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "destroyed"
