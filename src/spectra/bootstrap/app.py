import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from spectra.bootstrap.hosted import consumer_name, open_hosted
from spectra.bootstrap.logs import configure_logging, logging_config
from spectra.bootstrap.metrics import process_registry, serving_metrics
from spectra.bootstrap.settings import HostedSettings, Mode, Settings
from spectra.bootstrap.tracks import (
    analysis_observer,
    analysis_worker,
    hosted_parts,
    local_parts,
    track_service,
)
from spectra.gateway.errors import install_error_handlers
from spectra.gateway.readiness import Readiness, install_readiness
from spectra.gateway.request_metrics import install_request_metrics
from spectra.gateway.routes import (
    create_router,
    install_track_service,
    install_upload_admission,
)
from spectra.gateway.security_headers import install_security_headers
from spectra.gateway.upload_limit import install_upload_limit
from spectra.shared.clock import MonotonicClock
from spectra.tracks.application.admission import UploadAdmission


def create_app(settings: Settings, hosted: HostedSettings | None = None) -> FastAPI:
    configure_logging(settings.log_level, settings.log_format)
    registry = process_registry()
    observer = analysis_observer(registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with serving_metrics(registry, port=settings.metrics_port):
            async with serving_tracks(app):
                yield

    @asynccontextmanager
    async def serving_tracks(app: FastAPI) -> AsyncIterator[None]:
        if hosted is None:
            parts = local_parts(settings)
            install_track_service(app, track_service(parts, settings))
            install_upload_admission(app, UploadAdmission(quota=parts.quota))
            worker = analysis_worker(parts, observer)
            async with asyncio.TaskGroup() as group:
                group.create_task(worker.run())
                yield
                await worker.close()
        else:
            async with open_hosted(
                hosted, consumer=consumer_name(), max_subscriptions=settings.max_event_streams
            ) as adapters:
                hosted_tracks = hosted_parts(adapters, settings)
                install_track_service(app, track_service(hosted_tracks, settings))
                install_upload_admission(app, UploadAdmission(quota=hosted_tracks.quota))
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
    install_security_headers(app)
    install_request_metrics(app, registry=registry, clock=MonotonicClock())
    return app


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
        log_config=logging_config(settings.log_level, settings.log_format),
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
    )
