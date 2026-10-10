import asyncio
from typing import Final

from spectra.analysis.application.ports import AudioFormat, AudioProbe
from spectra.analysis.domain.signal import AudioSignal
from spectra.analysis.domain.track_analysis import TrackAnalysis
from spectra.tracks.adapters.memory import InMemoryProgressFeed, InMemoryTrackStore
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.quota import QuotaDecision, UploadSource
from spectra.tracks.domain.track import TrackId, TrackStatus


class FakeClock:
    def __init__(self, start_s: float = 0.0) -> None:
        self._now_s = start_s
        self.sleeps_s: list[float] = []

    def now_s(self) -> float:
        return self._now_s

    def set_now_s(self, now_s: float) -> None:
        self._now_s = now_s

    def advance(self, duration_s: float) -> None:
        self._now_s += duration_s

    async def sleep(self, duration_s: float) -> None:
        self.sleeps_s.append(duration_s)
        self._now_s += duration_s
        await asyncio.sleep(0)


def probe_of(
    *, duration_s: float = 180.0, sample_rate_hz: int = 44_100, channel_count: int = 2
) -> AudioProbe:
    return AudioProbe(
        audio_format=AudioFormat.WAV,
        duration_s=duration_s,
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
    )


DEFAULT_PROBE: Final = probe_of()


class FakeDecoder:
    def __init__(
        self,
        *,
        signal: AudioSignal | None = None,
        probe_error: Exception | None = None,
        decode_error: Exception | None = None,
        probe_result: AudioProbe = DEFAULT_PROBE,
    ) -> None:
        self._signal = signal
        self._probe_result = probe_result
        self._probe_error = probe_error
        self._decode_error = decode_error
        self.probed: list[bytes] = []
        self.decoded: list[bytes] = []

    def probe(self, data: bytes) -> AudioProbe:
        self.probed.append(data)
        if self._probe_error is not None:
            raise self._probe_error
        return self._probe_result

    def decode(self, data: bytes) -> AudioSignal:
        self.decoded.append(data)
        if self._decode_error is not None:
            raise self._decode_error
        if self._signal is None:
            raise AssertionError("FakeDecoder has no signal to return")
        return self._signal


class FakeJobQueue:
    def __init__(self, *, enqueue_error: Exception | None = None) -> None:
        self.jobs: list[AnalysisJob] = []
        self.finished: list[AnalysisJob] = []
        self.enqueue_error = enqueue_error

    async def enqueue(self, job: AnalysisJob) -> None:
        if self.enqueue_error is not None:
            raise self.enqueue_error
        self.jobs.append(job)

    async def take(self) -> AnalysisJob | None:
        return self.jobs.pop(0) if self.jobs else None

    async def done(self, job: AnalysisJob) -> None:
        self.finished.append(job)

    async def close(self) -> list[AnalysisJob]:
        return []


class FakeTrackExpiry:
    def __init__(self, store: InMemoryTrackStore, *, unseen_s: dict[TrackId, float]) -> None:
        self._store = store
        self._unseen_s = unseen_s
        self.limits: list[int] = []

    async def expire_unseen(self, *, unseen_for_s: float, limit: int) -> list[TrackId]:
        self.limits.append(limit)
        oldest_first = sorted(self._unseen_s.items(), key=lambda item: -item[1])
        stale = [
            track_id
            for track_id, unseen_s in oldest_first
            if unseen_s > unseen_for_s and await self._store.find(track_id) is not None
        ][:limit]
        for track_id in stale:
            await self._store.delete(track_id)
        return stale


def memory_board(*, capacity: int = 8) -> StatusBoard:
    return StatusBoard(store=InMemoryTrackStore(capacity=capacity), feed=InMemoryProgressFeed())


def record_now(board: StatusBoard, track_id: TrackId, status: TrackStatus) -> None:
    asyncio.run(board.record(track_id, status))


def fake_timeline(analysis: TrackAnalysis) -> bytes:
    return f"timeline of {analysis.frame_count} frames".encode()


class UnlimitedQuota:
    def __init__(self) -> None:
        self.clients: list[UploadSource] = []
        self.refunds: list[UploadSource] = []

    async def refund(self, source: UploadSource) -> None:
        self.refunds.append(source)

    async def spend(self, source: UploadSource) -> QuotaDecision:
        self.clients.append(source)
        return QuotaDecision(allowed=True, retry_after_s=0.0)


class ExhaustedQuota:
    def __init__(self, *, retry_after_s: float) -> None:
        self._retry_after_s = retry_after_s

        self.clients: list[UploadSource] = []

    async def spend(self, source: UploadSource) -> QuotaDecision:
        self.clients.append(source)
        return QuotaDecision(allowed=False, retry_after_s=self._retry_after_s)

    async def refund(self, source: UploadSource) -> None:
        pass


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, TrackId, TrackStatus | None]] = []

    def started(self, track_id: TrackId) -> None:
        self.events.append(("started", track_id, None))

    def finished(self, track_id: TrackId, outcome: TrackStatus) -> None:
        self.events.append(("finished", track_id, outcome))
