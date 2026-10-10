import asyncio

import pytest
from starlette.types import Message, Scope

from spectra.gateway.held_response import HeldStreamingResponse
from spectra.gateway.slots import SlotLimits, Slots
from spectra.tracks.domain.quota import UploadSource

BODY = bytes(range(256)) * 1_000
SOURCE = UploadSource(address="203.0.113.1", network="203.0.113.1")
SCOPE: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}


def slots() -> Slots:
    return Slots(
        limits=SlotLimits(total=1, per_address=1, per_network=1, retry_after_s=1.0),
        name="timelines",
    )


async def never_disconnects() -> Message:
    await asyncio.Event().wait()
    return {"type": "http.disconnect"}


@pytest.mark.anyio
async def test_the_body_goes_out_in_chunks_and_the_slot_is_freed_after_the_last() -> None:
    timelines = slots()
    sent: list[Message] = []
    held_while_sending: list[int] = []

    async def send(message: Message) -> None:
        held_while_sending.append(timelines.held)
        sent.append(message)

    response = HeldStreamingResponse(
        timelines.take(SOURCE),
        content=BODY,
        media_type="application/octet-stream",
        headers={},
        deadline_s=5.0,
    )
    await response(SCOPE, never_disconnects, send)
    bodies = [message.get("body", b"") for message in sent[1:]]
    assert b"".join(bodies) == BODY
    assert len([body for body in bodies if body]) == 4
    assert (b"content-length", str(len(BODY)).encode()) in sent[0]["headers"]
    assert set(held_while_sending) == {1}
    assert timelines.held == 0


@pytest.mark.anyio
async def test_a_reader_that_stops_reading_loses_its_slot_at_the_deadline() -> None:
    timelines = slots()
    sent: list[Message] = []

    async def stalled(message: Message) -> None:
        sent.append(message)
        if len(sent) > 1:
            await asyncio.Event().wait()

    response = HeldStreamingResponse(
        timelines.take(SOURCE),
        content=BODY,
        media_type="application/octet-stream",
        headers={},
        deadline_s=0.05,
    )
    async with asyncio.timeout(5.0):
        await response(SCOPE, never_disconnects, stalled)
    assert timelines.held == 0
