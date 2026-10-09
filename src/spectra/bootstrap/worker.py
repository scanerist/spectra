import asyncio
import contextlib
import logging
import signal
from typing import Final

from spectra.bootstrap.app import configure_logging
from spectra.bootstrap.hosted import consumer_name, open_hosted
from spectra.bootstrap.settings import HostedSettings, Settings
from spectra.bootstrap.tracks import analysis_worker, hosted_parts
from spectra.tracks.application.janitor import Janitor

logger = logging.getLogger(__name__)

DAY_S: Final = 86_400.0


async def serve(settings: Settings, hosted: HostedSettings, *, stop: asyncio.Event) -> None:
    async with open_hosted(hosted, consumer=consumer_name()) as adapters:
        parts = hosted_parts(adapters)
        worker = analysis_worker(parts)
        janitor = Janitor(
            expiry=adapters.store,
            board=parts.board,
            blobs=parts.blobs,
            retention_s=settings.retention_days * DAY_S,
        )
        logger.info("worker started")
        async with asyncio.TaskGroup() as group:
            group.create_task(worker.run())
            group.create_task(sweep_until(stop, janitor, interval_s=settings.sweep_interval_s))
            await stop.wait()
            await worker.close()
        logger.info("worker stopped")


async def sweep_until(stop: asyncio.Event, janitor: Janitor, *, interval_s: float) -> None:
    while not stop.is_set():
        await janitor.sweep()
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
    configure_logging(settings.log_level)
    asyncio.run(serve_until_signalled(settings, HostedSettings.from_environment()))
