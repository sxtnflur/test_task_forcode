from fastapi.testclient import TestClient

from ..main import app

API_VERSION = "v2"


def test_ping():
    with TestClient(app) as client:
        response = client.get(f"/{API_VERSION}/ping")
        assert response.status_code == 200
        assert response.text == "pong"
