import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from spectra.gateway.errors import install_error_handlers
from spectra.gateway.request_metrics import install_request_metrics
from spectra.gateway.routes import create_router
from spectra.gateway.upload_limit import install_upload_limit
from tests.fakes import FakeClock


@pytest.fixture
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture
def client(registry: CollectorRegistry) -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    install_error_handlers(app)
    install_upload_limit(app, max_upload_bytes=10)
    install_request_metrics(app, registry=registry, clock=FakeClock())
    return TestClient(app, raise_server_exceptions=False)


def requests(registry: CollectorRegistry, method: str, route: str, status: str) -> float | None:
    labels = {"method": method, "route": route, "status": status}
    return registry.get_sample_value("spectra_http_requests_total", labels)


def test_requests_are_counted_by_route_template(
    client: TestClient, registry: CollectorRegistry
) -> None:
    client.get("/health")
    client.get("/health")
    client.get("/tracks/0123456789abcdef")
    assert requests(registry, "GET", "/health", "200") == 2.0
    assert requests(registry, "GET", "/tracks/{track_id}", "500") == 1.0


def test_unknown_paths_share_one_label(client: TestClient, registry: CollectorRegistry) -> None:
    client.get("/wp-admin")
    client.get("/.env")
    assert requests(registry, "GET", "unmatched", "404") == 2.0


def test_refused_uploads_are_counted_with_their_status(
    client: TestClient, registry: CollectorRegistry
) -> None:
    client.post("/tracks", content=b"x" * 200_000)
    assert requests(registry, "POST", "unmatched", "413") == 1.0


def test_request_time_is_recorded(client: TestClient, registry: CollectorRegistry) -> None:
    client.get("/health")
    labels = {"method": "GET", "route": "/health"}
    assert registry.get_sample_value("spectra_http_request_duration_seconds_count", labels) == 1.0
