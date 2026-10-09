import uuid
from collections.abc import AsyncIterator

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spectra.bootstrap.app import create_app
from spectra.bootstrap.hosted import open_hosted
from spectra.bootstrap.migrate import migrate
from spectra.bootstrap.settings import HostedSettings, Settings
from spectra.tracks.adapters.redis_jobs import JOBS_STREAM
from spectra.tracks.domain.blobs import upload_key
from spectra.tracks.domain.track import TrackId
from tests.audio_files import encoded
from tests.hosted import hosted_test_settings, requires_services, wipe_services
from tests.signals import SAMPLE_RATE_HZ, kick_train

pytestmark = [pytest.mark.anyio, requires_services]


@pytest.fixture
async def hosted() -> AsyncIterator[HostedSettings]:
    settings = hosted_test_settings(bucket=f"spectra-test-{uuid.uuid4().hex[:12]}")
    await wipe_services(settings)
    await migrate(settings)
    yield settings
    await wipe_services(settings)


def kicks() -> bytes:
    stereo = np.stack([kick_train(128.0, 8.0)] * 2, axis=1)
    return encoded(stereo, SAMPLE_RATE_HZ, "FLAC")


async def test_an_upload_is_stored_and_queued_for_a_worker(hosted: HostedSettings) -> None:
    with TestClient(create_app(Settings(), hosted)) as client:
        created = client.post("/tracks", files={"file": ("kicks.flac", kicks(), "audio/flac")})
        assert created.status_code == 202
        track_id = created.json()["track_id"]
        pending = client.get(f"/tracks/{track_id}")
    assert pending.status_code == 409
    assert pending.json()["error"] == "not_ready"
    async with open_hosted(hosted, consumer="test") as adapters:
        assert await adapters.redis.xlen(JOBS_STREAM) == 1
        assert await adapters.blobs.get(upload_key(TrackId(track_id))) == kicks()


async def test_a_hosted_engine_is_ready_when_its_stores_answer(hosted: HostedSettings) -> None:
    with TestClient(create_app(Settings(), hosted)) as client:
        response = client.get("/ready")
    assert (response.status_code, response.json()) == (200, {"ok": True})


async def test_an_unknown_track_is_not_found(hosted: HostedSettings) -> None:
    with TestClient(create_app(Settings(), hosted)) as client:
        response = client.get("/tracks/0123456789abcdef")
    assert response.status_code == 404
    assert response.json()["error"] == "track_not_found"
