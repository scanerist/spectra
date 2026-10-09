import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.gateway.routes import create_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    return TestClient(app)


def test_health_reports_protocol_version_one(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "protocol": 1}


def test_websocket_stream_is_gone(client: TestClient) -> None:
    assert client.get("/ws").status_code == 404
