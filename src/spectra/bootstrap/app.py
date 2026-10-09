import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import uvicorn
from fastapi import FastAPI

from spectra.bootstrap.hosted import consumer_name, open_hosted
from spectra.bootstrap.settings import HostedSettings, LogLevel, Mode, Settings
from spectra.bootstrap.tracks import (
    analysis_worker,
    hosted_parts,
    local_parts,
    track_service,
)
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.readiness import Readiness, install_readiness
from spectra.gateway.routes import create_router, install_track_service
from spectra.gateway.upload_limit import install_upload_limit

LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def create_app(settings: Settings, hosted: HostedSettings | None = None) -> FastAPI:
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if hosted is None:
            parts = local_parts(settings)
            install_track_service(app, track_service(parts, settings))
            worker = analysis_worker(parts)
            async with asyncio.TaskGroup() as group:
                group.create_task(worker.run())
                yield
                await worker.close()
        else:
            async with open_hosted(hosted, consumer=consumer_name()) as adapters:
                install_track_service(app, track_service(hosted_parts(adapters), settings))
                install_readiness(
                    app,
                    Readiness(
                        probes={
                            "postgres": adapters.store.ping,
                            "redis": adapters.jobs.ping,
                            "s3": adapters.blobs.ping,
                        }
                    ),
                )
                yield

    app = FastAPI(title="spectra engine", lifespan=lifespan)
    app.include_router(create_router())
    install_error_handlers(app)
    install_upload_limit(app, max_upload_bytes=settings.max_upload_bytes)
    return app


def configure_logging(level: LogLevel) -> None:
    logging.basicConfig(level=level.value, format=LOG_FORMAT)


def hosted_settings(settings: Settings) -> HostedSettings | None:
    match settings.mode:
        case Mode.LOCAL:
            return None
        case Mode.HOSTED:
            return HostedSettings.from_environment()


def run() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings, hosted_settings(settings)),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
