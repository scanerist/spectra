import asyncio
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from spectra.shared.clock import Clock
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.domain.quota import QuotaDecision, UploadQuotaPolicy, UploadSource
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

    async def delete(self, track_id: TrackId) -> None:
        self._statuses.pop(track_id, None)

    async def analysing_count(self) -> int:
        return sum(not is_final(status) for status in self._statuses.values())

    async def evict_settled(self, *, keep: TrackId) -> list[TrackId]:
        settled = [key for key, value in self._statuses.items() if is_final(value) and key != keep]
        evicted = settled[: max(len(self._statuses) - self._capacity, 0)]
        for track_id in evicted:
            del self._statuses[track_id]
        return evicted


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


class InMemoryBlobStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self._blobs[key] = data

    async def get(self, key: str) -> bytes | None:
        return self._blobs.get(key)

    async def delete(self, key: str) -> None:
        self._blobs.pop(key, None)


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._jobs: asyncio.Queue[AnalysisJob | None] = asyncio.Queue()

    async def enqueue(self, job: AnalysisJob) -> None:
        self._jobs.put_nowait(job)

    async def take(self) -> AnalysisJob | None:
        return await self._jobs.get()

    async def done(self, job: AnalysisJob) -> None:
        pass

    async def close(self) -> list[AnalysisJob]:
        pending: list[AnalysisJob] = []
        while not self._jobs.empty():
            job = self._jobs.get_nowait()
            if job is not None:
                pending.append(job)
        self._jobs.put_nowait(None)
        return pending


class InMemoryUploadQuota:
    def __init__(self, *, policy: UploadQuotaPolicy, clock: Clock) -> None:
        self._policy = policy
        self._clock = clock
        self._uploads_s: dict[str, deque[float]] = {}

    async def spend(self, source: UploadSource) -> QuotaDecision:
        now_s = self._clock.now_s()
        scopes = self._policy.scopes(source)
        logs = [self._recent(scope.key, now_s) for scope in scopes]
        full = [
            log[len(log) - scope.limit]
            for scope, log in zip(scopes, logs, strict=True)
            if len(log) >= scope.limit
        ]
        decision = self._policy.decide(blocking_uploads_s=full, now_s=now_s)
        if decision.allowed:
            for log in logs:
                log.append(now_s)
        return decision

    async def refund(self, source: UploadSource) -> None:
        own, *shared = [
            self._recent(scope.key, self._clock.now_s()) for scope in self._policy.scopes(source)
        ]
        if not own:
            return
        upload_s = own.pop()
        for log in shared:
            log.remove(upload_s)

    def _recent(self, key: str, now_s: float) -> deque[float]:
        log = self._uploads_s.setdefault(key, deque())
        while log and log[0] <= now_s - self._policy.window_s:
            log.popleft()
        return log
