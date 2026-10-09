import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Self

from prometheus_client import CollectorRegistry, Counter, Gauge

from spectra.bootstrap.hosted import HostedAdapters, consumer_name, open_hosted
from spectra.bootstrap.logs import configure_logging
from spectra.bootstrap.metrics import serving_metrics
from spectra.bootstrap.settings import HostedSettings, Settings
from spectra.bootstrap.tracks import analysis_worker, hosted_parts
from spectra.tracks.application.janitor import Janitor

logger = logging.getLogger(__name__)

DAY_S: Final = 86_400.0
PENDING_REFRESH_S: Final = 15.0


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerMetrics:
    expired: Counter
    pending: Gauge

    @classmethod
    def on(cls, registry: CollectorRegistry) -> Self:
        return cls(
            expired=Counter(
                "spectra_tracks_expired",
                "Tracks removed after going unseen for the retention period",
                registry=registry,
            ),
            pending=Gauge(
                "spectra_analyses_pending",
                "Tracks queued or being analysed by any worker",
                registry=registry,
            ),
        )


async def serve(settings: Settings, hosted: HostedSettings, *, stop: asyncio.Event) -> None:
    registry = CollectorRegistry()
    metrics = WorkerMetrics.on(registry)
    with serving_metrics(registry, port=settings.metrics_port):
        async with open_hosted(hosted, consumer=consumer_name()) as adapters:
            await serve_on(adapters, settings, registry=registry, metrics=metrics, stop=stop)


async def serve_on(
    adapters: HostedAdapters,
    settings: Settings,
    *,
    registry: CollectorRegistry,
    metrics: WorkerMetrics,
    stop: asyncio.Event,
) -> None:
    parts = hosted_parts(adapters, settings)
    worker = analysis_worker(parts, registry)
    janitor = Janitor(
        expiry=adapters.store,
        blobs=parts.blobs,
        retention_s=settings.retention_days * DAY_S,
    )

    async def sweep() -> None:
        metrics.expired.inc(await janitor.sweep())

    async def count_pending() -> None:
        metrics.pending.set(await parts.board.analysing_count())

    logger.info("worker started")
    async with asyncio.TaskGroup() as group:
        group.create_task(worker.run())
        group.create_task(every(settings.sweep_interval_s, sweep, stop=stop))
        group.create_task(every(PENDING_REFRESH_S, count_pending, stop=stop))
        await stop.wait()
        await worker.close()
    logger.info("worker stopped")


async def every(
    interval_s: float, action: Callable[[], Awaitable[None]], *, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        await action()
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(interval_s):
                await stop.wait()


async def serve_until_signalled(settings: Settings, hosted: HostedSettings) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, stop.set)
    await serve(settings, hosted, stop=stop)


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format)
    asyncio.run(serve_until_signalled(settings, HostedSettings.from_environment()))
