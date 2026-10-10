import http.client
import io
import json
import logging
import math
import sys
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from typing import Final
from urllib.parse import urlsplit

import numpy as np
import soundfile

from spectra.bootstrap.settings import Settings
from spectra.gateway.protocol import PROTOCOL_VERSION
from spectra.gateway.timeline_codec import HEADER, timeline_length

logger = logging.getLogger(__name__)

SAMPLE_RATE_HZ: Final = 44_100
SMOKE_BPM: Final = 120.0
SMOKE_DURATION_S: Final = 12.0
KICK_LENGTH_S: Final = 0.25
KICK_FREQ_HZ: Final = 55.0
KICK_DECAY_S: Final = 0.06
BPM_TOLERANCE: Final = 1.0
REQUEST_TIMEOUT_S: Final = 60.0


class SmokeTestError(Exception):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class SmokeReport:
    track_id: str
    bpm: float
    frame_count: int
    bar_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Reply:
    status: int
    body: bytes


def kick_track() -> bytes:
    times_s = np.arange(round(KICK_LENGTH_S * SAMPLE_RATE_HZ)) / SAMPLE_RATE_HZ
    hit = np.sin(2.0 * math.pi * KICK_FREQ_HZ * times_s) * np.exp(-times_s / KICK_DECAY_S)
    samples = np.zeros(round(SMOKE_DURATION_S * SAMPLE_RATE_HZ))
    beat_samples = round(60.0 / SMOKE_BPM * SAMPLE_RATE_HZ)
    for start in range(0, samples.size - hit.size, beat_samples):
        samples[start : start + hit.size] += 0.5 * hit
    buffer = io.BytesIO()
    soundfile.write(buffer, samples.astype(np.float32), SAMPLE_RATE_HZ, format="FLAC")
    return buffer.getvalue()


def multipart(data: bytes, *, boundary: str) -> bytes:
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="smoke.flac"\r\n'
        "Content-Type: audio/flac\r\n\r\n"
    )
    return head.encode() + data + f"\r\n--{boundary}--\r\n".encode()


class Client:
    def __init__(self, base_url: str) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or parts.hostname is None:
            raise SmokeTestError(f"expected an http(s) base url, got {base_url!r}")
        self._https = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port

    def request(
        self, method: str, path: str, *, body: bytes | None = None, content_type: str = ""
    ) -> Reply:
        connection = self._connect()
        try:
            headers = {"Content-Type": content_type} if content_type else {}
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return Reply(status=response.status, body=response.read())
        finally:
            connection.close()

    def _connect(self) -> http.client.HTTPConnection:
        if self._https:
            return http.client.HTTPSConnection(self._host, self._port, timeout=REQUEST_TIMEOUT_S)
        return http.client.HTTPConnection(self._host, self._port, timeout=REQUEST_TIMEOUT_S)


def expect(reply: Reply, status: HTTPStatus, step: str) -> bytes:
    if reply.status != status:
        raise SmokeTestError(f"{step}: expected {status.value}, got {reply.status} {reply.body!r}")
    return reply.body


def last_event(stream: str) -> tuple[str, str]:
    events = [
        dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        for block in stream.replace("\r\n", "\n").split("\n\n")
    ]
    finished = [event for event in events if event.get("event") in {"ready", "failed"}]
    if not finished:
        raise SmokeTestError("the event stream ended without ready or failed")
    return finished[-1]["event"], finished[-1]["data"]


def run_smoke_test(base_url: str) -> SmokeReport:
    client = Client(base_url)
    expect(client.request("GET", "/health"), HTTPStatus.OK, "health")
    boundary = uuid.uuid4().hex
    created = client.request(
        "POST",
        "/tracks",
        body=multipart(kick_track(), boundary=boundary),
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    track_id = str(json.loads(expect(created, HTTPStatus.ACCEPTED, "upload"))["track_id"])
    stream = expect(client.request("GET", f"/tracks/{track_id}/events"), HTTPStatus.OK, "events")
    name, data = last_event(stream.decode())
    if name != "ready":
        raise SmokeTestError(f"the analysis failed: {data}")
    info = json.loads(expect(client.request("GET", f"/tracks/{track_id}"), HTTPStatus.OK, "track"))
    bpm = float(info["bpm"])
    if abs(bpm - SMOKE_BPM) > BPM_TOLERANCE:
        raise SmokeTestError(f"expected about {SMOKE_BPM:g} BPM, got {bpm:.2f}")
    timeline = expect(
        client.request("GET", f"/tracks/{track_id}/timeline"), HTTPStatus.OK, "timeline"
    )
    return SmokeReport(track_id=track_id, bpm=bpm, **timeline_counts(timeline))


def timeline_counts(timeline: bytes) -> dict[str, int]:
    version, _, frame_count, bar_count = HEADER.unpack_from(timeline)
    expected_bytes = timeline_length(frame_count=frame_count, bar_count=bar_count)
    if version != PROTOCOL_VERSION or len(timeline) != expected_bytes:
        raise SmokeTestError(f"malformed timeline: version {version}, {len(timeline)} bytes")
    return {"frame_count": frame_count, "bar_count": bar_count}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    base_url = sys.argv[1] if len(sys.argv) > 1 else f"http://127.0.0.1:{Settings().port}"
    try:
        report = run_smoke_test(base_url)
    except (SmokeTestError, OSError) as error:
        sys.exit(f"smoke test against {base_url} failed: {error}")
    logger.info(
        "smoke test passed: track %s, %.2f BPM, %d frames, %d bars",
        report.track_id,
        report.bpm,
        report.frame_count,
        report.bar_count,
    )
