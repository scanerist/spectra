import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import uvicorn
from fastapi import FastAPI

from spectra.analysis.adapters.soundfile_decoder import SoundfileDecoder
from spectra.bootstrap.settings import LogLevel, Settings
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.routes import create_router, install_track_service
from spectra.gateway.upload_limit import install_upload_limit
from spectra.tracks.adapters.memory import (
    InMemoryBlobStore,
    InMemoryProgressFeed,
    InMemoryTrackStore,
)
from spectra.tracks.application.service import TrackService, UploadLimits
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.application.worker import AnalysisWorker

LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings.log_level)
    decoder = SoundfileDecoder()
    board = StatusBoard(
        store=InMemoryTrackStore(capacity=settings.max_tracks), feed=InMemoryProgressFeed()
    )
    blobs = InMemoryBlobStore()
    worker = AnalysisWorker(decoder=decoder, board=board, blobs=blobs)
    service = TrackService(
        decoder=decoder,
        board=board,
        blobs=blobs,
        jobs=worker,
        limits=UploadLimits(
            max_upload_bytes=settings.max_upload_bytes,
            max_duration_s=settings.max_duration_s,
            max_pending=settings.max_pending_analyses,
        ),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with asyncio.TaskGroup() as group:
            group.create_task(worker.run())
            yield
            await worker.close()

    app = FastAPI(title="spectra engine", lifespan=lifespan)
    app.include_router(create_router())
    install_error_handlers(app)
    install_track_service(app, service)
    install_upload_limit(app, max_upload_bytes=settings.max_upload_bytes)
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
