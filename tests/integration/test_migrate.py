import uuid
from collections.abc import AsyncIterator

import pytest

from spectra.bootstrap.hosted import open_hosted
from spectra.bootstrap.migrate import migrate
from spectra.bootstrap.settings import HostedSettings
from spectra.tracks.application.ports import AnalysisJob
from tests.hosted import hosted_test_settings, requires_services, wipe_services
from tests.statuses import READY, track

pytestmark = [pytest.mark.anyio, requires_services]


@pytest.fixture
async def settings() -> AsyncIterator[HostedSettings]:
    settings = hosted_test_settings(bucket=f"spectra-test-{uuid.uuid4().hex[:12]}")
    await wipe_services(settings)
    yield settings
    await wipe_services(settings)


async def test_migrating_prepares_every_store(settings: HostedSettings) -> None:
    await migrate(settings)
    async with open_hosted(settings, consumer="test") as adapters:
        await adapters.store.save(track("a"), READY)
        await adapters.blobs.put("timelines/a", b"timeline")
        await adapters.jobs.enqueue(AnalysisJob(track_id=track("a")))
        assert await adapters.store.find(track("a")) == READY
        assert await adapters.blobs.get("timelines/a") == b"timeline"
        assert await adapters.jobs.take() == AnalysisJob(track_id=track("a"))


async def test_migrating_again_keeps_what_is_stored(settings: HostedSettings) -> None:
    await migrate(settings)
    async with open_hosted(settings, consumer="test") as adapters:
        await adapters.store.save(track("a"), READY)
        await adapters.blobs.put("timelines/a", b"timeline")
    await migrate(settings)
    async with open_hosted(settings, consumer="test") as adapters:
        assert await adapters.store.find(track("a")) == READY
        assert await adapters.blobs.get("timelines/a") == b"timeline"
