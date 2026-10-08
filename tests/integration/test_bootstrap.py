import pytest
import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from spectra.bootstrap import app as bootstrap_app
from spectra.bootstrap.settings import LogLevel, Settings


def test_settings_defaults_match_stage_zero() -> None:
    settings = Settings()
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)
    assert settings.frame_rate_hz == 60.0
    assert settings.synthetic_bpm == 128.0
    assert settings.log_level is LogLevel.INFO


def test_settings_read_the_spectra_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECTRA_HOST", "192.168.1.20")
    monkeypatch.setenv("SPECTRA_PORT", "9001")
    monkeypatch.setenv("SPECTRA_FRAME_RATE_HZ", "30")
    monkeypatch.setenv("SPECTRA_SYNTHETIC_BPM", "174")
    monkeypatch.setenv("SPECTRA_LOG_LEVEL", "debug")
    settings = Settings()
    assert (settings.host, settings.port) == ("192.168.1.20", 9001)
    assert settings.frame_rate_hz == 30.0
    assert settings.synthetic_bpm == 174.0
    assert settings.log_level is LogLevel.DEBUG


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SPECTRA_PORT", "0"),
        ("SPECTRA_FRAME_RATE_HZ", "0"),
        ("SPECTRA_FRAME_RATE_HZ", "inf"),
        ("SPECTRA_SYNTHETIC_BPM", "1000"),
        ("SPECTRA_LOG_LEVEL", "chatty"),
    ],
    ids=["port-zero", "frame-rate-zero", "frame-rate-inf", "bpm-too-fast", "log-level-unknown"],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        Settings()


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
