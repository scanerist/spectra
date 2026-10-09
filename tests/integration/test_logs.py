import json
import logging
from collections.abc import Iterator

import pytest

from spectra.bootstrap.logs import JsonFormatter, configure_logging, logging_config
from spectra.bootstrap.settings import LogFormat, LogLevel, Settings


@pytest.fixture
def restored_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    uvicorn_state = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    yield
    root.handlers[:], root.level = handlers, level
    for name, (logger_handlers, propagate) in uvicorn_state.items():
        logger = logging.getLogger(name)
        logger.handlers[:], logger.propagate = logger_handlers, propagate


def record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("spectra.test", logging.WARNING, __file__, 1, message, args, None)


def test_a_json_line_carries_level_logger_and_message() -> None:
    entry = json.loads(JsonFormatter().format(record("analysed %s", "9f2c41d07a3b55e1")))
    assert (entry["level"], entry["logger"]) == ("warning", "spectra.test")
    assert entry["message"] == "analysed 9f2c41d07a3b55e1"
    assert entry["time"].endswith("+00:00")


def test_a_json_line_keeps_extra_fields() -> None:
    line = record("analysed")
    line.duration_s = 1.25
    assert json.loads(JsonFormatter().format(line))["duration_s"] == 1.25


def test_a_json_line_carries_the_exception() -> None:
    error = ValueError("boom")
    line = logging.LogRecord(
        "spectra.test", logging.ERROR, __file__, 1, "failed", None, (ValueError, error, None)
    )
    entry = json.loads(JsonFormatter().format(line))
    assert "ValueError: boom" in entry["exception"]


@pytest.mark.usefixtures("restored_logging")
def test_json_logging_covers_uvicorn_access_lines(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(LogLevel.INFO, LogFormat.JSON)
    logging.getLogger("uvicorn.access").info('%s - "%s %s"', "1.2.3.4", "GET", "/health")
    entry = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert (entry["logger"], entry["message"]) == ("uvicorn.access", '1.2.3.4 - "GET /health"')


def test_text_is_the_default_log_format() -> None:
    config = logging_config(Settings().log_level, Settings().log_format)
    assert config["formatters"] == {
        "spectra": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}
    }
