import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import uvicorn
from fastapi import FastAPI

from spectra.analysis.adapters.synthetic_groove import SyntheticGroove
from spectra.analysis.domain.tempo import Tempo
from spectra.bootstrap.settings import LogLevel, Settings
from spectra.gateway.handlers import PromptEchoHandler
from spectra.gateway.routes import create_router, install_session_dependencies
from spectra.gateway.session import SessionDependencies
from spectra.gateway.wire.messages import DirectorLog
from spectra.shared.clock import MonotonicClock

logger = logging.getLogger(__name__)

SYNTHETIC_SEED: Final = 0
LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        install_session_dependencies(app, wire_session_dependencies(settings))
        logger.info(
            "streaming a synthetic groove at %g BPM, %g frames per second",
            settings.synthetic_bpm,
            settings.frame_rate_hz,
        )
        yield

    app = FastAPI(title="spectra engine", lifespan=lifespan)
    app.include_router(create_router())
    return app


def wire_session_dependencies(settings: Settings) -> SessionDependencies:
    clock = MonotonicClock()
    tempo = Tempo(bpm=settings.synthetic_bpm)
    source = SyntheticGroove(clock=clock, tempo=tempo, seed=SYNTHETIC_SEED)
    return SessionDependencies(
        source=source,
        handler=PromptEchoHandler(source=source),
        clock=clock,
        frame_rate_hz=settings.frame_rate_hz,
        greeting=DirectorLog(bar=0, text=f"engine connected · fake source {tempo.bpm:g} BPM"),
    )


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
