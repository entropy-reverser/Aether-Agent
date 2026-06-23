"""Tests for app.api.routes — HTTP layer over the routing engine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_explain_returns_routing_decision():
    resp = client.post(
        "/api/routing/explain",
        json={"message": "translate this please"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] in (1, 2, 3)  # Tier IntEnum serializes as int
    assert body["model"]
    assert "signals" in body
    assert "audit_reasons" in body
    assert isinstance(body["overridden"], bool)


def test_explain_rejects_empty_message():
    resp = client.post("/api/routing/explain", json={"message": ""})
    assert resp.status_code == 422  # Pydantic validation


def test_explain_accepts_context_for_override():
    resp = client.post(
        "/api/routing/explain",
        json={
            "message": "fix this bug",
            "task_type": "coding",
            "project_phase": "implementation",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["tier"] in (1, 2, 3)


def test_feedback_endpoint_records():
    resp = client.post(
        "/api/routing/feedback",
        json={"message": "translate this", "positive": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "recorded"
