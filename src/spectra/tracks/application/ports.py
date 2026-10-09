from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from spectra.tracks.domain.track import TrackId, TrackStatus


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class AnalysisJob:
    track_id: TrackId
    data: bytes


class JobQueue(Protocol):
    def enqueue(self, job: AnalysisJob) -> None: ...


class TrackStore(Protocol):
    async def find(self, track_id: TrackId) -> TrackStatus | None: ...

    async def save(self, track_id: TrackId, status: TrackStatus) -> None: ...

    async def analysing_count(self) -> int: ...


class ProgressFeed(Protocol):
    async def publish(self, track_id: TrackId, status: TrackStatus) -> None: ...

    def subscribe(
        self, track_id: TrackId
    ) -> AbstractAsyncContextManager[AsyncIterator[TrackStatus]]: ...
