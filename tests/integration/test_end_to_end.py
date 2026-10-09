import struct
import time
from typing import Final

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spectra.bootstrap.app import create_app
from spectra.bootstrap.settings import Settings
from tests.audio_files import encoded
from tests.signals import SAMPLE_RATE_HZ, kick_train

POLL_INTERVAL_S: Final = 0.05
POLL_LIMIT_S: Final = 30.0


def wait_until_ready(client: TestClient, track_id: str) -> dict[str, object]:
    deadline = time.monotonic() + POLL_LIMIT_S
    while time.monotonic() < deadline:
        response = client.get(f"/tracks/{track_id}")
        if response.status_code != 409:
            assert response.status_code == 200, response.json()
            body: dict[str, object] = response.json()
            return body
        time.sleep(POLL_INTERVAL_S)
    pytest.fail("the analysis did not finish in time")


def test_uploaded_track_is_analysed_and_served_as_a_timeline() -> None:
    stereo = np.stack([kick_train(128.0, 16.0)] * 2, axis=1)
    data = encoded(stereo, SAMPLE_RATE_HZ, "FLAC")
    with TestClient(create_app(Settings())) as client:
        created = client.post("/tracks", files={"file": ("kicks.flac", data, "audio/flac")})
        assert created.status_code == 202
        track_id = created.json()["track_id"]
        info = wait_until_ready(client, track_id)
        timeline = client.get(f"/tracks/{track_id}/timeline").content
    assert info["bpm"] == pytest.approx(128.0, abs=0.5)
    assert info["duration_s"] == pytest.approx(16.0, abs=0.01)
    version, frame_rate_hz, frames, bars = struct.unpack_from("<IfII", timeline, 0)
    assert (version, frame_rate_hz) == (1, 44_100 / 512)
    assert len(timeline) == 16 + 264 * bars + 69 * frames


def test_same_file_uploaded_twice_is_one_track() -> None:
    data = encoded(kick_train(128.0, 10.0), SAMPLE_RATE_HZ, "WAV")
    with TestClient(create_app(Settings())) as client:
        first = client.post("/tracks", files={"file": ("a.wav", data, "audio/wav")}).json()
        wait_until_ready(client, first["track_id"])
        second = client.post("/tracks", files={"file": ("b.wav", data, "audio/wav")}).json()
        assert first == second
        assert client.get(f"/tracks/{second['track_id']}").status_code == 200
