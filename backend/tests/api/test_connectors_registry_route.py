"""Regression: static connector routes must beat /{connector_name}."""


def test_connectors_registry_not_captured_as_connector_name(client):
    """GET /api/connectors/registry must hit list_registry, not get_connector."""
    r = client.get("/api/connectors/registry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "servers" in body
    assert "total" in body
    assert "detail" not in body or "not found" not in str(body.get("detail", "")).lower()


def test_connectors_named_lookup_still_works(client):
    r = client.get("/api/connectors/mail")
    assert r.status_code == 200
    assert r.json()["name"] == "mail"
