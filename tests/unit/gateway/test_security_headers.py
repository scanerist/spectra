import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.gateway.errors import install_error_handlers
from spectra.gateway.routes import create_router
from spectra.gateway.security_headers import install_security_headers
from spectra.gateway.upload_limit import install_upload_limit

CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_router())
    install_error_handlers(app)
    install_upload_limit(app, max_upload_bytes=10)
    install_security_headers(app)
    return app


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/health"), ("GET", "/nowhere"), ("POST", "/tracks")],
    ids=["ok", "error", "refused-by-the-upload-limit"],
)
def test_every_response_forbids_sniffing_framing_and_referrers(
    app: FastAPI, method: str, path: str
) -> None:
    response = TestClient(app).request(method, path, content=b"x" * 200_000)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )


def test_plain_http_gets_no_strict_transport_security(app: FastAPI) -> None:
    response = TestClient(app, base_url="http://testserver").get("/health")
    assert "strict-transport-security" not in response.headers


def test_https_is_pinned_for_a_year(app: FastAPI) -> None:
    response = TestClient(app, base_url="https://testserver").get("/health")
    assert response.headers["strict-transport-security"] == "max-age=31536000"
