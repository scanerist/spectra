import asyncio
import json

import pytest
from starlette.types import Message, Receive, Scope, Send

from spectra.gateway.upload_limit import UploadLimit, UploadPace
from tests.fakes import FakeClock

LIMIT_BYTES = 1_000
CHUNK = b"x" * 100
PACE = UploadPace(min_bytes_per_s=100.0, grace_s=2.0, idle_s=5.0, max_s=60.0)


class ChunkedClient:
    def __init__(self, *, chunks: int, clock: FakeClock | None = None, gap_s: float = 0.0) -> None:
        self.chunks = chunks
        self.pulled = 0
        self.sent: list[Message] = []
        self.clock = clock or FakeClock()
        self.gap_s = gap_s

    async def receive(self) -> Message:
        self.clock.advance(self.gap_s)
        self.pulled += 1
        more = self.pulled < self.chunks
        return {"type": "http.request", "body": CHUNK, "more_body": more}

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    @property
    def status(self) -> int:
        return int(self.sent[0]["status"])

    @property
    def body(self) -> dict[str, str]:
        payload: dict[str, str] = json.loads(self.sent[1]["body"])
        return payload


async def reading_app(_scope: Scope, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if message["type"] == "http.disconnect" or not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 202, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


def guarded(client: ChunkedClient) -> UploadLimit:
    return UploadLimit(reading_app, max_body_bytes=LIMIT_BYTES, pace=PACE, clock=client.clock)


def post_scope(content_length: int | None = None) -> Scope:
    headers = [] if content_length is None else [(b"content-length", str(content_length).encode())]
    return {"type": "http", "method": "POST", "path": "/tracks", "headers": headers}


@pytest.mark.anyio
async def test_body_under_the_limit_reaches_the_app() -> None:
    client = ChunkedClient(chunks=5)
    await guarded(client)(post_scope(), client.receive, client.send)
    assert client.status == 202
    assert client.pulled == 5


@pytest.mark.anyio
async def test_chunked_body_stops_being_read_once_over_the_limit() -> None:
    client = ChunkedClient(chunks=1_000)
    await guarded(client)(post_scope(), client.receive, client.send)
    assert client.status == 413
    assert client.body["error"] == "file_too_large"
    assert client.pulled == LIMIT_BYTES // len(CHUNK) + 1


@pytest.mark.anyio
async def test_declared_oversized_body_is_refused_without_reading() -> None:
    client = ChunkedClient(chunks=1_000)
    await guarded(client)(post_scope(content_length=LIMIT_BYTES + 1), client.receive, client.send)
    assert client.status == 413
    assert client.pulled == 0


@pytest.mark.anyio
async def test_get_requests_pass_through_untouched() -> None:
    client = ChunkedClient(chunks=1)
    scope = {**post_scope(content_length=10 * LIMIT_BYTES), "method": "GET"}
    await guarded(client)(scope, client.receive, client.send)
    assert client.status == 202


@pytest.mark.anyio
async def test_a_body_arriving_at_the_minimum_pace_reaches_the_app() -> None:
    client = ChunkedClient(chunks=10, gap_s=1.0)
    await guarded(client)(post_scope(), client.receive, client.send)
    assert client.status == 202


@pytest.mark.anyio
async def test_a_body_arriving_too_slowly_is_dropped_as_no_file() -> None:
    client = ChunkedClient(chunks=10, gap_s=1.5)
    await guarded(client)(post_scope(), client.receive, client.send)
    assert client.status == 400
    assert client.body["error"] == "no_file"
    assert client.pulled < 10


class SilentClient(ChunkedClient):
    async def receive(self) -> Message:
        self.pulled += 1
        if self.pulled > 1:
            await asyncio.Event().wait()
        return {"type": "http.request", "body": CHUNK, "more_body": True}


@pytest.mark.anyio
async def test_a_body_that_stops_arriving_is_dropped_after_the_idle_time() -> None:
    client = SilentClient(chunks=10)
    limit = UploadLimit(
        reading_app,
        max_body_bytes=LIMIT_BYTES,
        pace=UploadPace(min_bytes_per_s=1.0, grace_s=60.0, idle_s=0.05, max_s=60.0),
        clock=client.clock,
    )
    async with asyncio.timeout(5.0):
        await limit(post_scope(), client.receive, client.send)
    assert client.status == 400


@pytest.mark.anyio
async def test_a_body_still_arriving_after_the_upload_deadline_is_dropped() -> None:
    client = ChunkedClient(chunks=10, gap_s=1.0)
    limit = UploadLimit(
        reading_app,
        max_body_bytes=LIMIT_BYTES,
        pace=UploadPace(min_bytes_per_s=1.0, grace_s=1.0, idle_s=5.0, max_s=5.0),
        clock=client.clock,
    )
    await limit(post_scope(), client.receive, client.send)
    assert client.status == 400
    assert client.pulled == 6
