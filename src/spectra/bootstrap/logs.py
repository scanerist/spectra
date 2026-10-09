import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Final, override

from spectra.bootstrap.settings import LogFormat, LogLevel

TEXT_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"
RECORD_ATTRIBUTES: Final = frozenset(
    {
        *vars(logging.LogRecord("", 0, "", 0, "", None, None)),
        "message",
        "asctime",
        "taskName",
        "color_message",
    }
)
UVICORN_LOGGERS: Final = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry |= {
            name: value for name, value in vars(record).items() if name not in RECORD_ATTRIBUTES
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def logging_config(level: LogLevel, log_format: LogFormat) -> dict[str, object]:
    formatter: dict[str, object] = (
        {"()": JsonFormatter} if log_format is LogFormat.JSON else {"format": TEXT_FORMAT}
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"spectra": formatter},
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "formatter": "spectra",
                "stream": "ext://sys.stderr",
            }
        },
        "root": {"level": level.value, "handlers": ["stderr"]},
        "loggers": {name: {"handlers": [], "propagate": True} for name in UVICORN_LOGGERS},
    }


def configure_logging(level: LogLevel, log_format: LogFormat) -> None:
    logging.config.dictConfig(logging_config(level, log_format))
