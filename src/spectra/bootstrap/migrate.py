import asyncio
import logging

from spectra.bootstrap.app import configure_logging
from spectra.bootstrap.hosted import consumer_name, open_hosted, prepare_storage
from spectra.bootstrap.settings import HostedSettings, Settings

logger = logging.getLogger(__name__)


async def migrate(settings: HostedSettings) -> None:
    async with open_hosted(settings, consumer=consumer_name()) as adapters:
        await prepare_storage(adapters)
    logger.info("postgres, redis and s3 are ready")


def main() -> None:
    configure_logging(Settings().log_level)
    asyncio.run(migrate(HostedSettings.from_environment()))
