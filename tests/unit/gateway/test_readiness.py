import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from spectra.gateway.errors import install_error_handlers
from spectra.gateway.readiness import Readiness, install_readiness
from spectra.gateway.routes import create_router


async def answers() -> bool:
    return True


async def stays_silent() -> bool:
    return False


async def hanging() -> bool:
    await asyncio.sleep(60.0)
    return True


def client_with(readiness: Readiness | None) -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    install_error_handlers(app)
    if readiness is not None:
        install_readiness(app, readiness)
    return TestClient(app)


def test_an_engine_without_stores_is_ready() -> None:
    response = client_with(None).get("/ready")
    assert (response.status_code, response.json()) == (200, {"ok": True})


def test_an_engine_whose_stores_answer_is_ready() -> None:
    readiness = Readiness(probes={"postgres": answers, "redis": answers})
    response = client_with(readiness).get("/ready")
    assert (response.status_code, response.json()) == (200, {"ok": True})


def test_a_silent_store_makes_the_engine_unavailable() -> None:
    probes = {"postgres": answers, "s3": stays_silent, "redis": stays_silent}
    response = client_with(Readiness(probes=probes)).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"error": "unavailable", "message": "not responding: redis, s3"}


def test_a_hanging_store_counts_as_silent() -> None:
    readiness = Readiness(probes={"postgres": hanging}, timeout_s=0.05)
    response = client_with(readiness).get("/ready")
    assert response.status_code == 503
    assert response.json()["message"] == "not responding: postgres"
