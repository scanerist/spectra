from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from spectra.analysis.domain.track_analysis import TrackAnalysis
from spectra.tracks.domain.quota import QuotaDecision, UploadSource
from spectra.tracks.domain.track import TrackId, TrackStatus

type TimelineEncoder = Callable[[TrackAnalysis], bytes]


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisJob:
    track_id: TrackId
    attempt: int = 1


class JobQueue(Protocol):
    async def enqueue(self, job: AnalysisJob) -> None: ...

    async def take(self) -> AnalysisJob | None: ...

    async def done(self, job: AnalysisJob) -> None: ...

    async def close(self) -> list[AnalysisJob]: ...


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes | None: ...

    async def delete(self, key: str) -> None: ...


class TrackStore(Protocol):
    async def find(self, track_id: TrackId) -> TrackStatus | None: ...

    async def save(self, track_id: TrackId, status: TrackStatus) -> None: ...

    async def delete(self, track_id: TrackId) -> None: ...

    async def analysing_count(self) -> int: ...

    async def evict_settled(self, *, keep: TrackId) -> list[TrackId]: ...


class AnalysisObserver(Protocol):
    def started(self, track_id: TrackId) -> None: ...

    def finished(self, track_id: TrackId, outcome: TrackStatus) -> None: ...


class UploadQuota(Protocol):
    async def spend(self, source: UploadSource) -> QuotaDecision: ...

    async def refund(self, source: UploadSource) -> None: ...


class TrackExpiry(Protocol):
    async def expire_unseen(self, *, unseen_for_s: float, limit: int) -> list[TrackId]: ...

    async def abandon_stalled(
        self, *, stalled_for_s: float, status: TrackStatus
    ) -> list[TrackId]: ...


class ProgressFeed(Protocol):
    async def publish(self, track_id: TrackId, status: TrackStatus) -> None: ...

    def subscribe(
        self, track_id: TrackId
    ) -> AbstractAsyncContextManager[AsyncIterator[TrackStatus]]: ...
