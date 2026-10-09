import json

import pytest
from starlette.types import Message, Receive, Scope, Send

from spectra.gateway.upload_limit import UploadLimit

LIMIT_BYTES = 1_000
CHUNK = b"x" * 100


class ChunkedClient:
    def __init__(self, *, chunks: int) -> None:
        self.chunks = chunks
        self.pulled = 0
        self.sent: list[Message] = []

    async def receive(self) -> Message:
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


def post_scope(content_length: int | None = None) -> Scope:
    headers = [] if content_length is None else [(b"content-length", str(content_length).encode())]
    return {"type": "http", "method": "POST", "path": "/tracks", "headers": headers}


@pytest.mark.anyio
async def test_body_under_the_limit_reaches_the_app() -> None:
    client = ChunkedClient(chunks=5)
    await UploadLimit(reading_app, max_body_bytes=LIMIT_BYTES)(
        post_scope(), client.receive, client.send
    )
    assert client.status == 202
    assert client.pulled == 5


@pytest.mark.anyio
async def test_chunked_body_stops_being_read_once_over_the_limit() -> None:
    client = ChunkedClient(chunks=1_000)
    await UploadLimit(reading_app, max_body_bytes=LIMIT_BYTES)(
        post_scope(), client.receive, client.send
    )
    assert client.status == 413
    assert client.body["error"] == "file_too_large"
    assert client.pulled == LIMIT_BYTES // len(CHUNK) + 1


@pytest.mark.anyio
async def test_declared_oversized_body_is_refused_without_reading() -> None:
    client = ChunkedClient(chunks=1_000)
    await UploadLimit(reading_app, max_body_bytes=LIMIT_BYTES)(
        post_scope(content_length=LIMIT_BYTES + 1), client.receive, client.send
    )
    assert client.status == 413
    assert client.pulled == 0


@pytest.mark.anyio
async def test_get_requests_pass_through_untouched() -> None:
    client = ChunkedClient(chunks=1)
    scope = {**post_scope(content_length=10 * LIMIT_BYTES), "method": "GET"}
    await UploadLimit(reading_app, max_body_bytes=LIMIT_BYTES)(scope, client.receive, client.send)
    assert client.status == 202
