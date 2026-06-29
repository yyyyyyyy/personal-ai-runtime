"""Integration tests for Knowledge Base API."""
import io

from starlette.testclient import TestClient


def test_list_empty_documents(client: TestClient):
    r = client.get("/api/knowledge/documents")
    assert r.status_code == 200
    data = r.json()
    assert "documents" in data


def test_search_empty(client: TestClient):
    r = client.post("/api/knowledge/search?query=test&n_results=3", content="")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data


def test_upload_txt(client: TestClient):
    r = client.post("/api/knowledge/upload", files={
        "file": ("test.txt", io.BytesIO(b"Hello world, this is a test document for knowledge base."), "text/plain"),
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["document"]["filename"] == "test.txt"
    assert data["document"]["chunks"] >= 1


def test_upload_and_list(client: TestClient):
    client.post("/api/knowledge/upload", files={
        "file": ("doc_a.md", io.BytesIO(b"# Title\nSome content here."), "text/markdown"),
    })
    client.post("/api/knowledge/upload", files={
        "file": ("doc_b.json", io.BytesIO(b'{"key":"value"}'), "application/json"),
    })
    r = client.get("/api/knowledge/documents")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2


def test_delete_document(client: TestClient):
    r = client.post("/api/knowledge/upload", files={
        "file": ("to_delete.txt", io.BytesIO(b"Delete me"), "text/plain"),
    })
    doc_id = r.json()["document"]["id"]
    r = client.delete(f"/api/knowledge/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_delete_nonexistent(client: TestClient):
    r = client.delete("/api/knowledge/documents/nonexistent-id")
    assert r.status_code == 404


def test_upload_empty_file(client: TestClient):
    r = client.post("/api/knowledge/upload", files={
        "file": ("empty.txt", io.BytesIO(b""), "text/plain"),
    })
    assert r.status_code == 400


def test_upload_invalid_extension(client: TestClient):
    r = client.post("/api/knowledge/upload", files={
        "file": ("image.png", io.BytesIO(b"fake"), "image/png"),
    })
    assert r.status_code == 400


def test_search_with_results(client: TestClient):
    client.post("/api/knowledge/upload", files={
        "file": ("search_test.txt", io.BytesIO(b"Machine learning is a subset of artificial intelligence."), "text/plain"),
    })
    r = client.post("/api/knowledge/search?query=machine+learning&n_results=3", content="")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
