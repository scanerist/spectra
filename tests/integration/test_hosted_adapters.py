import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack

import pytest

from spectra.bootstrap.hosted import open_hosted
from spectra.bootstrap.settings import HostedSettings
from spectra.tracks.application.ports import AnalysisJob
from tests.hosted import hosted_test_settings, requires_services, wipe_services
from tests.statuses import READY, track

pytestmark = [pytest.mark.anyio, requires_services]

MAX_SUBSCRIPTIONS = 3


@pytest.fixture
async def hosted() -> AsyncIterator[HostedSettings]:
    settings = hosted_test_settings(bucket=f"spectra-test-{uuid.uuid4().hex[:12]}")
    await wipe_services(settings)
    yield settings
    await wipe_services(settings)


async def test_holding_every_subscription_leaves_the_job_queue_working(
    hosted: HostedSettings,
) -> None:
    async with (
        open_hosted(hosted, consumer="test", max_subscriptions=MAX_SUBSCRIPTIONS) as adapters,
        AsyncExitStack() as subscriptions,
    ):
        await adapters.jobs.ensure_group()
        for index in range(MAX_SUBSCRIPTIONS):
            await subscriptions.enter_async_context(adapters.feed.subscribe(track(str(index))))
        assert adapters.redis.connection_pool is not adapters.events.connection_pool
        assert await adapters.jobs.ping()
        await adapters.jobs.enqueue(AnalysisJob(track_id=track("0")))
        await adapters.feed.publish(track("0"), READY)
