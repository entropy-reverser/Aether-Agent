"""Tests for app.api.wiki_routes — HTTP layer over the wiki store.

Uses a temp-directory-backed store so tests don't touch the real wiki dir.
The singleton is replaced per-test via direct attribute assignment.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.core.wiki as wiki_pkg
from app.core.wiki import Fact, WikiStore
from app.core.wiki.backends import LocalFilesystemBackend
from app.main import app


def _install_tmp_store(tmp_path, monkeypatch) -> WikiStore:
    """Point the wiki singleton at a fresh temp-dir store."""
    store = WikiStore(LocalFilesystemBackend(tmp_path / "wiki"))
    store.init()
    monkeypatch.setattr(wiki_pkg, "wiki_store", store)
    return store


def _post_fact(subject: str, predicate: str, obj: str) -> None:
    """Shorthand POST helper to keep test lines under the length limit."""
    client.post(
        "/api/wiki/facts",
        json={"subject": subject, "predicate": predicate, "object": obj},
    )


client = TestClient(app)


def test_list_facts_empty(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.get("/api/wiki/facts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_fact_then_list(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.post(
        "/api/wiki/facts",
        json={"subject": "user", "predicate": "name", "object": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["object"] == "Alice"
    assert body["source"] == "manual"
    assert body["id"]

    listing = client.get("/api/wiki/facts").json()
    assert len(listing) == 1
    assert listing[0]["object"] == "Alice"


def test_add_fact_with_tags(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.post(
        "/api/wiki/facts",
        json={
            "subject": "user",
            "predicate": "prefers",
            "object": "vim",
            "tags": ["editor"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["tags"] == ["editor"]


def test_add_fact_rejects_empty_subject(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.post(
        "/api/wiki/facts",
        json={"subject": "", "predicate": "name", "object": "Alice"},
    )
    assert resp.status_code == 422


def test_add_fact_is_idempotent(monkeypatch, tmp_path):
    """Adding the same fact twice stores it once."""
    _install_tmp_store(tmp_path, monkeypatch)
    payload = {"subject": "user", "predicate": "name", "object": "Alice"}
    client.post("/api/wiki/facts", json=payload)
    client.post("/api/wiki/facts", json=payload)
    assert len(client.get("/api/wiki/facts").json()) == 1


def test_list_facts_filter_by_subject(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    _post_fact("user", "name", "Alice")
    _post_fact("project", "uses", "python")
    assert len(client.get("/api/wiki/facts?subject=user").json()) == 1
    assert len(client.get("/api/wiki/facts").json()) == 2


def test_query_returns_relevant_fact(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    _post_fact("user", "uses", "python")
    resp = client.get("/api/wiki/query", params={"q": "python"})
    assert resp.status_code == 200
    hits = resp.json()
    assert hits
    assert hits[0]["fact"]["object"] == "python"
    assert hits[0]["score"] == 1.0


def test_query_no_match_returns_empty(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    _post_fact("user", "uses", "python")
    resp = client.get("/api/wiki/query", params={"q": "quantum"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_query_rejects_empty_q(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.get("/api/wiki/query", params={"q": ""})
    assert resp.status_code == 422


def test_extract_from_turns_stores_facts(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.post(
        "/api/wiki/extract",
        json={"turns": ["my name is Alice", "I use python"]},
    )
    assert resp.status_code == 200
    objects = {f["object"] for f in resp.json()}
    assert "Alice" in objects
    # Stored facts appear in listing.
    listed = {f["object"] for f in client.get("/api/wiki/facts").json()}
    assert "Alice" in listed


def test_extract_rejects_empty_turns(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    resp = client.post("/api/wiki/extract", json={"turns": []})
    assert resp.status_code == 422


def test_rebuild(monkeypatch, tmp_path):
    store = _install_tmp_store(tmp_path, monkeypatch)
    store.add_fact(Fact(subject="user", predicate="name", object="Alice"))
    resp = client.post("/api/wiki/rebuild")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rebuilt"
    assert resp.json()["fact_count"] == 1


def test_export_returns_documents(monkeypatch, tmp_path):
    _install_tmp_store(tmp_path, monkeypatch)
    client.post("/api/wiki/facts", json={"subject": "user", "predicate": "name", "object": "Alice"})
    resp = client.get("/api/wiki/export")
    assert resp.status_code == 200
    exported = resp.json()
    assert "user" in exported
    assert "Alice" in exported["user"]
