from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app, base_url="http://127.0.0.1:8000").get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
