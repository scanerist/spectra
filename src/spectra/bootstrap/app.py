import logging
from typing import Final

import uvicorn
from fastapi import FastAPI

from spectra.bootstrap.settings import LogLevel, Settings
from spectra.gateway.routes import create_router

LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title="spectra engine")
    app.include_router(create_router())
    return app


def configure_logging(level: LogLevel) -> None:
    logging.basicConfig(level=level.value, format=LOG_FORMAT)


def run() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
