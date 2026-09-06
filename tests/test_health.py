"""
Health and System Tests
=======================
"""

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Verifies GET /health returns 200 and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_root_overview(client: TestClient):
    """Verifies GET / returns service information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "endpoints" in data
    assert "/v1/tables" in data["endpoints"]["create_table"]
