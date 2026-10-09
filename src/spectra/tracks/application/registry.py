import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator

from spectra.tracks.domain.errors import TrackNotFoundError
from spectra.tracks.domain.track import TrackId, TrackStatus, is_final


class TrackRegistry:
    def __init__(self, *, capacity: int) -> None:
        self._capacity = capacity
        self._statuses: OrderedDict[TrackId, TrackStatus] = OrderedDict()
        self._watchers: dict[TrackId, set[asyncio.Queue[TrackStatus]]] = {}

    def status(self, track_id: TrackId) -> TrackStatus:
        status = self._statuses.get(track_id)
        if status is None:
            raise TrackNotFoundError(f"track {track_id.value} is unknown or was evicted")
        self._statuses.move_to_end(track_id)
        return status

    def find(self, track_id: TrackId) -> TrackStatus | None:
        try:
            return self.status(track_id)
        except TrackNotFoundError:
            return None

    def analysing_count(self) -> int:
        return sum(not is_final(status) for status in self._statuses.values())

    def put(self, track_id: TrackId, status: TrackStatus) -> None:
        self._statuses[track_id] = status
        self._statuses.move_to_end(track_id)
        for queue in self._watchers.get(track_id, set()):
            queue.put_nowait(status)
        self._evict(keep=track_id)

    async def watch(self, track_id: TrackId) -> AsyncIterator[TrackStatus]:
        status = self.status(track_id)
        queue: asyncio.Queue[TrackStatus] = asyncio.Queue()
        self._watchers.setdefault(track_id, set()).add(queue)
        try:
            yield status
            while not is_final(status):
                status = await queue.get()
                yield status
        finally:
            self._unwatch(track_id, queue)

    def _unwatch(self, track_id: TrackId, queue: asyncio.Queue[TrackStatus]) -> None:
        watchers = self._watchers.get(track_id, set())
        watchers.discard(queue)
        if not watchers:
            self._watchers.pop(track_id, None)

    def _evict(self, *, keep: TrackId) -> None:
        settled = [key for key, value in self._statuses.items() if is_final(value) and key != keep]
        excess = len(self._statuses) - self._capacity
        for track_id in settled[: max(excess, 0)]:
            del self._statuses[track_id]
