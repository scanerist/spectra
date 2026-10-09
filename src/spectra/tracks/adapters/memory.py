import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from spectra.tracks.domain.track import TrackId, TrackStatus, is_final


class InMemoryTrackStore:
    def __init__(self, *, capacity: int) -> None:
        self._capacity = capacity
        self._statuses: OrderedDict[TrackId, TrackStatus] = OrderedDict()

    async def find(self, track_id: TrackId) -> TrackStatus | None:
        status = self._statuses.get(track_id)
        if status is not None:
            self._statuses.move_to_end(track_id)
        return status

    async def save(self, track_id: TrackId, status: TrackStatus) -> None:
        self._statuses[track_id] = status
        self._statuses.move_to_end(track_id)
        self._evict(keep=track_id)

    async def analysing_count(self) -> int:
        return sum(not is_final(status) for status in self._statuses.values())

    def _evict(self, *, keep: TrackId) -> None:
        settled = [key for key, value in self._statuses.items() if is_final(value) and key != keep]
        excess = len(self._statuses) - self._capacity
        for track_id in settled[: max(excess, 0)]:
            del self._statuses[track_id]


class InMemoryProgressFeed:
    def __init__(self) -> None:
        self._subscribers: dict[TrackId, set[asyncio.Queue[TrackStatus]]] = {}

    async def publish(self, track_id: TrackId, status: TrackStatus) -> None:
        for queue in self._subscribers.get(track_id, set()):
            queue.put_nowait(status)

    @asynccontextmanager
    async def subscribe(self, track_id: TrackId) -> AsyncIterator[AsyncIterator[TrackStatus]]:
        queue: asyncio.Queue[TrackStatus] = asyncio.Queue()
        self._subscribers.setdefault(track_id, set()).add(queue)
        try:
            yield drain(queue)
        finally:
            subscribers = self._subscribers.get(track_id, set())
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(track_id, None)


async def drain(queue: asyncio.Queue[TrackStatus]) -> AsyncIterator[TrackStatus]:
    while True:
        yield await queue.get()
