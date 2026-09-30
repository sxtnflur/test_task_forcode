from fastapi.testclient import TestClient

from tests.conftest import API_VERSION


def test_ping(client: TestClient):
    response = client.get(f"/{API_VERSION}/ping")
    assert response.status_code == 200
    assert response.text == "pong"
