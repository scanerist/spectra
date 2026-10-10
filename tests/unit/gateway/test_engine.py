import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.gateway.engine import install_engine
from spectra.gateway.errors import GatewayNotConfiguredError
from spectra.gateway.routes import create_router
from tests.fakes import fake_engine


def app_with_router() -> FastAPI:
    app = FastAPI()
    app.include_router(create_router())
    return app


@pytest.mark.parametrize(
    "path",
    ["/ready", "/tracks/0123456789abcdef", "/tracks/0123456789abcdef/timeline"],
    ids=["ready", "track", "timeline"],
)
def test_a_route_without_an_installed_engine_is_not_configured(path: str) -> None:
    with pytest.raises(GatewayNotConfiguredError):
        TestClient(app_with_router()).get(path)


def test_an_installed_engine_serves_the_routes() -> None:
    app = app_with_router()
    install_engine(app, fake_engine())
    assert TestClient(app).get("/ready").status_code == 200
