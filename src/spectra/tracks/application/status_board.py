from collections.abc import AsyncGenerator

from spectra.tracks.application.ports import ProgressFeed, TrackStore
from spectra.tracks.domain.errors import TrackNotFoundError
from spectra.tracks.domain.track import TrackId, TrackStatus, is_final


class StatusBoard:
    def __init__(self, *, store: TrackStore, feed: ProgressFeed) -> None:
        self._store = store
        self._feed = feed

    async def find(self, track_id: TrackId) -> TrackStatus | None:
        return await self._store.find(track_id)

    async def current(self, track_id: TrackId) -> TrackStatus:
        status = await self._store.find(track_id)
        if status is None:
            raise TrackNotFoundError(f"track {track_id.value} is unknown or was evicted")
        return status

    async def analysing_count(self) -> int:
        return await self._store.analysing_count()

    async def forget(self, track_id: TrackId) -> None:
        await self._store.delete(track_id)

    async def evict_settled(self, *, keep: TrackId) -> list[TrackId]:
        return await self._store.evict_settled(keep=keep)

    async def record(self, track_id: TrackId, status: TrackStatus) -> None:
        await self._store.save(track_id, status)
        await self._feed.publish(track_id, status)

    async def watch(self, track_id: TrackId) -> AsyncGenerator[TrackStatus]:
        async with self._feed.subscribe(track_id) as updates:
            status = await self.current(track_id)
            yield status
            if is_final(status):
                return
            async for update in updates:
                yield update
                if is_final(update):
                    return
