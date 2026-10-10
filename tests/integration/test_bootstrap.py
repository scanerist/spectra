import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from spectra.bootstrap import app as bootstrap_app
from spectra.bootstrap.hosted import postgres_url
from spectra.bootstrap.logs import logging_config
from spectra.bootstrap.settings import (
    HostedSettings,
    LogFormat,
    LogLevel,
    Mode,
    PostgresSettings,
    S3Settings,
    Settings,
)


def test_settings_defaults() -> None:
    settings = Settings()
    assert (settings.host, settings.port) == ("127.0.0.1", 8000)
    assert settings.log_level is LogLevel.INFO
    assert settings.max_upload_bytes == 256 * 1024 * 1024
    assert settings.max_tracks == 8
    assert settings.max_duration_s == 1_800.0
    assert settings.max_decoded_samples == 1_800 * 96_000 * 2
    assert settings.max_pending_analyses == 4
    assert settings.max_concurrent_uploads == 2
    assert (settings.uploads_per_hour, settings.network_uploads_per_hour) == (20, 60)
    assert settings.total_uploads_per_hour == 600
    assert settings.max_event_streams == 64
    assert settings.max_timeline_downloads == 16
    assert settings.max_event_streams_per_client == 4
    assert settings.event_stream_lifetime_s == 300.0
    assert settings.mode is Mode.LOCAL


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
        ("SPECTRA_MAX_DURATION_S", "0"),
    ],
    ids=[
        "port-zero",
        "port-too-high",
        "log-level-unknown",
        "no-upload",
        "no-tracks",
        "no-duration",
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        Settings()


HOSTED_ENVIRONMENT = {
    "SPECTRA_POSTGRES_HOST": "postgres",
    "SPECTRA_POSTGRES_PASSWORD": "p@ss:w/rd",
    "SPECTRA_REDIS_HOST": "redis",
    "SPECTRA_REDIS_PASSWORD": "redis-secret",
    "SPECTRA_S3_URL": "http://s3:7070",
    "SPECTRA_S3_ACCESS_KEY": "spectra",
    "SPECTRA_S3_SECRET_KEY": "s3-secret",
}


def set_hosted_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in HOSTED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def test_hosted_settings_read_every_service(monkeypatch: pytest.MonkeyPatch) -> None:
    set_hosted_environment(monkeypatch)
    settings = HostedSettings.from_environment()
    assert (settings.postgres.host, settings.postgres.port) == ("postgres", 5432)
    assert (settings.postgres.database, settings.postgres.user) == ("spectra", "spectra")
    assert (settings.redis.host, settings.redis.port, settings.redis.database) == ("redis", 6379, 0)
    assert (settings.s3.url, settings.s3.bucket) == ("http://s3:7070", "spectra")


def test_hosted_settings_keep_secrets_out_of_their_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    set_hosted_environment(monkeypatch)
    shown = repr(HostedSettings.from_environment())
    assert all(secret not in shown for secret in ("p@ss:w/rd", "redis-secret", "s3-secret"))


@pytest.mark.parametrize(
    "variable",
    ["SPECTRA_POSTGRES_PASSWORD", "SPECTRA_REDIS_HOST", "SPECTRA_S3_SECRET_KEY"],
    ids=["postgres-password", "redis-host", "s3-secret"],
)
def test_hosted_settings_require_each_connection(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    set_hosted_environment(monkeypatch)
    monkeypatch.delenv(variable)
    with pytest.raises(ValidationError):
        HostedSettings.from_environment()


def test_a_settings_error_does_not_show_the_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    set_hosted_environment(monkeypatch)
    monkeypatch.delenv("SPECTRA_POSTGRES_HOST")
    monkeypatch.delenv("SPECTRA_S3_URL")
    for settings in (PostgresSettings, S3Settings):
        with pytest.raises(ValidationError) as error:
            settings()
        shown = str(error.value)
        assert all(secret not in shown for secret in ("p@ss:w/rd", "s3-secret"))


def test_postgres_url_escapes_the_password(monkeypatch: pytest.MonkeyPatch) -> None:
    set_hosted_environment(monkeypatch)
    url = postgres_url(HostedSettings.from_environment().postgres)
    assert url.render_as_string(hide_password=False) == (
        "postgresql+asyncpg://spectra:p%40ss%3Aw%2Frd@postgres:5432/spectra"
    )


def test_local_mode_needs_no_hosted_settings() -> None:
    assert bootstrap_app.hosted_settings(Settings()) is None


def test_hosted_mode_reads_the_hosted_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    set_hosted_environment(monkeypatch)
    monkeypatch.setenv("SPECTRA_MODE", "hosted")
    hosted = bootstrap_app.hosted_settings(Settings())
    assert hosted is not None
    assert hosted.postgres.host == "postgres"


def test_hosted_mode_refuses_to_start_without_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECTRA_MODE", "hosted")
    with pytest.raises(ValidationError):
        bootstrap_app.hosted_settings(Settings())


def test_created_app_serves_health() -> None:
    client = TestClient(bootstrap_app.create_app(Settings()))
    assert client.get("/health").json() == {"ok": True, "protocol": 1}


@pytest.mark.parametrize(
    "path", ["/docs", "/redoc", "/openapi.json"], ids=["docs", "redoc", "schema"]
)
def test_created_app_does_not_publish_its_schema(path: str) -> None:
    client = TestClient(bootstrap_app.create_app(Settings()))
    assert client.get(path).status_code == 404


def test_run_serves_the_app_with_configured_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served: dict[str, object] = {}

    def fake_uvicorn_run(app: FastAPI, **options: object) -> None:
        served.update(app=app, **options)

    monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)
    monkeypatch.setenv("SPECTRA_PORT", "9002")
    bootstrap_app.run()
    assert isinstance(served["app"], FastAPI)
    assert (served["host"], served["port"], served["log_level"]) == ("127.0.0.1", 9002, "info")
    assert (served["proxy_headers"], served["forwarded_allow_ips"]) == (True, "127.0.0.1")
    assert served["log_config"] == logging_config(LogLevel.INFO, LogFormat.TEXT)


def test_a_local_app_can_start_twice() -> None:
    app = bootstrap_app.create_app(Settings())
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
