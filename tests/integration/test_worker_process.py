import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spectra.bootstrap.app import create_app
from spectra.bootstrap.hosted import open_hosted
from spectra.bootstrap.migrate import migrate
from spectra.bootstrap.settings import HostedSettings, Settings
from spectra.bootstrap.worker import serve
from spectra.tracks.domain.blobs import timeline_key
from tests.audio_files import encoded
from tests.hosted import hosted_test_settings, requires_services, wipe_services
from tests.signals import SAMPLE_RATE_HZ, kick_train
from tests.statuses import READY, track

pytestmark = [pytest.mark.anyio, requires_services]

WAIT_S = 30.0
POLL_S = 0.05


@pytest.fixture
async def hosted() -> AsyncIterator[HostedSettings]:
    settings = hosted_test_settings(bucket=f"spectra-test-{uuid.uuid4().hex[:12]}")
    await wipe_services(settings)
    await migrate(settings)
    yield settings
    await wipe_services(settings)


async def eventually(check: Callable[[], Awaitable[bool]]) -> None:
    async with asyncio.timeout(WAIT_S):
        while True:
            if await check():
                return
            await asyncio.sleep(POLL_S)


async def test_a_worker_analyses_what_the_api_accepted(hosted: HostedSettings) -> None:
    stereo = np.stack([kick_train(128.0, 12.0)] * 2, axis=1)
    data = encoded(stereo, SAMPLE_RATE_HZ, "FLAC")
    stop = asyncio.Event()
    async with asyncio.TaskGroup() as group:
        group.create_task(serve(Settings(), hosted, stop=stop))
        with TestClient(create_app(Settings(), hosted)) as client:
            created = client.post("/tracks", files={"file": ("kicks.flac", data, "audio/flac")})
            track_id = created.json()["track_id"]

            async def is_ready() -> bool:
                status_code: int = client.get(f"/tracks/{track_id}").status_code
                return status_code == 200

            await eventually(is_ready)
            info = client.get(f"/tracks/{track_id}").json()
            timeline = client.get(f"/tracks/{track_id}/timeline")
        stop.set()
    assert info["bpm"] == pytest.approx(128.0, abs=0.5)
    assert timeline.status_code == 200


async def test_a_worker_removes_tracks_past_retention(hosted: HostedSettings) -> None:
    async with open_hosted(hosted, consumer="test") as adapters:
        await adapters.store.save(track("old"), READY)
        await adapters.blobs.put(timeline_key(track("old")), b"timeline")
        settings = Settings(retention_days=1e-6, sweep_interval_s=POLL_S)
        stop = asyncio.Event()

        async def is_removed() -> bool:
            return await adapters.blobs.get(timeline_key(track("old"))) is None

        async with asyncio.TaskGroup() as group:
            group.create_task(serve(settings, hosted, stop=stop))
            await eventually(is_removed)
            stop.set()
        assert await adapters.store.find(track("old")) is None


async def test_a_stopped_worker_exits_promptly(hosted: HostedSettings) -> None:
    stop = asyncio.Event()
    stop.set()
    async with asyncio.timeout(5.0):
        await serve(Settings(), hosted, stop=stop)
