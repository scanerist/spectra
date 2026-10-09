import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from spectra.bootstrap import app as bootstrap_app
from spectra.bootstrap.settings import LogLevel, Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)
    assert settings.log_level is LogLevel.INFO
    assert settings.max_upload_bytes == 256 * 1024 * 1024
    assert settings.max_tracks == 8


def test_settings_read_the_spectra_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECTRA_HOST", "192.168.1.20")
    monkeypatch.setenv("SPECTRA_PORT", "9001")
    monkeypatch.setenv("SPECTRA_LOG_LEVEL", "debug")
    monkeypatch.setenv("SPECTRA_MAX_UPLOAD_BYTES", "1000")
    monkeypatch.setenv("SPECTRA_MAX_TRACKS", "2")
    settings = Settings()
    assert (settings.host, settings.port) == ("192.168.1.20", 9001)
    assert settings.log_level is LogLevel.DEBUG
    assert (settings.max_upload_bytes, settings.max_tracks) == (1000, 2)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SPECTRA_PORT", "0"),
        ("SPECTRA_PORT", "70000"),
        ("SPECTRA_LOG_LEVEL", "chatty"),
        ("SPECTRA_MAX_UPLOAD_BYTES", "0"),
        ("SPECTRA_MAX_TRACKS", "0"),
    ],
    ids=["port-zero", "port-too-high", "log-level-unknown", "no-upload", "no-tracks"],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        Settings()


def test_created_app_serves_health() -> None:
    client = TestClient(bootstrap_app.create_app(Settings()))
    assert client.get("/health").json() == {"ok": True, "protocol": 1}


def test_run_serves_the_app_with_configured_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served: dict[str, object] = {}

    def fake_uvicorn_run(app: FastAPI, *, host: str, port: int, log_level: str) -> None:
        served.update(app=app, host=host, port=port, log_level=log_level)

    monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)
    monkeypatch.setenv("SPECTRA_PORT", "9002")
    bootstrap_app.run()
    assert isinstance(served["app"], FastAPI)
    assert (served["host"], served["port"], served["log_level"]) == ("127.0.0.1", 9002, "info")
