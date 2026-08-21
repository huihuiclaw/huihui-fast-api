"""Tests for health endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """Health endpoint returns 200 and ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_ready() -> None:
    """Ready endpoint returns 200 with app metadata."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["app"] == "huihui-fast-api"


def test_root() -> None:
    """Root endpoint returns a greeting."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data["message"].lower()