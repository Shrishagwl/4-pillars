from fastapi.testclient import TestClient

from engine.config import Settings
from engine.main import create_app


def test_health_answers_ok():
    client = TestClient(create_app(Settings(log_json=False)))
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
