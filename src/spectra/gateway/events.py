import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import aclosing
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel

from spectra.gateway.errors import FAILURE_CODES
from spectra.gateway.schemas import ErrorBody, ProgressBody, track_info
from spectra.gateway.slots import Slot, Slots
from spectra.tracks.domain.track import Analysing, Failed, Ready, TrackId, TrackStatus

EVENT_STREAM_MEDIA_TYPE: Final = "text/event-stream"
EVENT_STREAM_HEADERS: Final[Mapping[str, str]] = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class EventStreams:
    slots: Slots
    lifetime_s: float


def sse_event(name: str, payload: BaseModel) -> str:
    return f"event: {name}\ndata: {payload.model_dump_json()}\n\n"


def status_event(track_id: TrackId, status: TrackStatus) -> str:
    match status:
        case Analysing(stage=stage, progress=progress):
            return sse_event("progress", ProgressBody(stage=stage.value, progress=progress))
        case Ready(summary=summary):
            return sse_event("ready", track_info(track_id, summary))
        case Failed(code=code, message=message):
            return sse_event("failed", ErrorBody(error=FAILURE_CODES[code].value, message=message))


async def status_events(
    track_id: TrackId, statuses: AsyncIterator[TrackStatus]
) -> AsyncIterator[str]:
    async for status in statuses:
        yield status_event(track_id, status)


async def until_deadline(
    statuses: AsyncGenerator[TrackStatus], *, lifetime_s: float
) -> AsyncGenerator[TrackStatus]:
    deadline_s = asyncio.get_running_loop().time() + lifetime_s
    async with aclosing(statuses):
        while True:
            try:
                async with asyncio.timeout_at(deadline_s):
                    status = await anext(statuses)
            except StopAsyncIteration, TimeoutError:
                return
            yield status


async def holding(slot: Slot, events: AsyncIterator[str]) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield event
    finally:
        slot.release()
