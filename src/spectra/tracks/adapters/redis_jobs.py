import asyncio
from dataclasses import dataclass, replace
from typing import Final

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.domain.errors import TracksError
from spectra.tracks.domain.track import TrackId

JOBS_STREAM: Final = "spectra:jobs"
WORKERS_GROUP: Final = "workers"

type Delivery = tuple[AnalysisJob, bytes]


class UnexpectedReplyError(TracksError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class JobStream:
    consumer: str
    key: str = JOBS_STREAM
    group: str = WORKERS_GROUP


class RedisJobQueue:
    def __init__(
        self,
        *,
        client: Redis,
        stream: JobStream,
        claim_after_s: float = 300.0,
        block_s: float = 1.0,
    ) -> None:
        self._client = client
        self._stream = stream
        self._claim_after_ms = milliseconds(claim_after_s)
        self._block_ms = milliseconds(block_s)
        self._closed = asyncio.Event()
        self._in_flight: dict[TrackId, bytes] = {}
        self._resumed_own = False

    async def ensure_group(self) -> None:
        try:
            await self._client.xgroup_create(
                self._stream.key, self._stream.group, id="0", mkstream=True
            )
        except ResponseError as error:
            if not str(error).startswith("BUSYGROUP"):
                raise

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except RedisError, OSError:
            return False

    async def enqueue(self, job: AnalysisJob) -> None:
        await self._client.xadd(self._stream.key, {"track_id": job.track_id.value})

    async def take(self) -> AnalysisJob | None:
        while not self._closed.is_set():
            delivery = (
                await self._resume_own() or await self._claim_stale() or await self._read_new()
            )
            if delivery is not None:
                job, message_id = delivery
                self._in_flight[job.track_id] = message_id
                return job
        return None

    async def done(self, job: AnalysisJob) -> None:
        message_id = self._in_flight.pop(job.track_id)
        await self._client.xack(self._stream.key, self._stream.group, message_id)
        await self._client.xdel(self._stream.key, message_id)

    async def close(self) -> list[AnalysisJob]:
        self._closed.set()
        return []

    async def _resume_own(self) -> Delivery | None:
        if self._resumed_own:
            return None
        reply = await self._client.xreadgroup(
            self._stream.group, self._stream.consumer, {self._stream.key: "0"}, count=1
        )
        match reply:
            case [[_, [entry, *_]], *_]:
                return await self._counted(delivery_of(entry))
            case [] | [[_, []], *_] | None:
                self._resumed_own = True
                return None
        raise UnexpectedReplyError(f"unexpected XREADGROUP reply {reply!r}")

    async def _counted(self, delivery: Delivery) -> Delivery:
        job, message_id = delivery
        pending = await self._client.xpending_range(
            self._stream.key, self._stream.group, min=message_id, max=message_id, count=1
        )
        match pending:
            case [{"times_delivered": int() as times_delivered}]:
                return replace(job, attempt=times_delivered), message_id
        return delivery

    async def _claim_stale(self) -> Delivery | None:
        reply = await self._client.xautoclaim(
            self._stream.key,
            self._stream.group,
            self._stream.consumer,
            min_idle_time=self._claim_after_ms,
            count=1,
        )
        match reply:
            case [_, [entry, *_], *_]:
                return await self._counted(delivery_of(entry))
            case [_, [], *_]:
                return None
        raise UnexpectedReplyError(f"unexpected XAUTOCLAIM reply {reply!r}")

    async def _read_new(self) -> Delivery | None:
        reply = await self._client.xreadgroup(
            self._stream.group,
            self._stream.consumer,
            {self._stream.key: ">"},
            count=1,
            block=self._block_ms,
        )
        match reply:
            case [[_, [entry, *_]], *_]:
                return delivery_of(entry)
            case [] | None:
                return None
        raise UnexpectedReplyError(f"unexpected XREADGROUP reply {reply!r}")


def delivery_of(entry: object) -> Delivery:
    match entry:
        case (bytes() as message_id, {b"track_id": bytes() as track_id}):
            return AnalysisJob(track_id=TrackId(track_id.decode())), message_id
    raise UnexpectedReplyError(f"unexpected stream entry {entry!r}")


def milliseconds(duration_s: float) -> int:
    return round(duration_s * 1000)
