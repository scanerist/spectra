import asyncio
import contextlib

import pytest

from spectra.analysis.domain.errors import UndecodableAudioError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.adapters.memory import InMemoryBlobStore, InMemoryJobQueue
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.application.worker import (
    KEEPS_CRASHING,
    MAX_ATTEMPTS,
    UPLOAD_GONE,
    AnalysisWorker,
)
from spectra.tracks.domain.blobs import timeline_key, upload_key
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    Ready,
    TrackId,
    TrackStatus,
)
from tests.fakes import FakeDecoder, FakeJobQueue, fake_timeline, memory_board
from tests.signals import kick_train, signal_of, silence
from tests.statuses import READY

TRACK = TrackId.of_content(b"track")


async def statuses_of(
    decoder: FakeDecoder, blobs: InMemoryBlobStore | None = None
) -> list[TrackStatus]:
    board = memory_board()
    store = blobs or InMemoryBlobStore()
    jobs = InMemoryJobQueue()
    worker = AnalysisWorker(
        decoder=decoder, board=board, blobs=store, jobs=jobs, encoder=fake_timeline
    )
    await board.record(TRACK, Analysing.at(AnalysisStage.DECODING))
    if blobs is None:
        await store.put(upload_key(TRACK), b"track")
    seen: list[TrackStatus] = []

    async def follow() -> None:
        seen.extend([status async for status in board.watch(TRACK)])
        await worker.close()

    async with asyncio.TaskGroup() as group:
        group.create_task(follow())
        group.create_task(worker.run())
        await jobs.enqueue(AnalysisJob(track_id=TRACK))
    return seen


@pytest.mark.anyio
async def test_worker_reports_every_stage_then_ready() -> None:
    seen = await statuses_of(FakeDecoder(signal=signal_of(kick_train(128.0, 12.0))))
    stages = [status.stage for status in seen if isinstance(status, Analysing)]
    assert stages == ["decoding", "spectrum", "tempo", "structure"]
    assert isinstance(seen[-1], Ready)
    assert seen[-1].summary.bpm == pytest.approx(128.0, abs=0.5)


@pytest.mark.anyio
async def test_undecodable_file_fails_as_undecodable() -> None:
    seen = await statuses_of(FakeDecoder(decode_error=UndecodableAudioError("lost sync")))
    assert seen[-1] == Failed(code=FailureCode.UNDECODABLE, message="lost sync")


@pytest.mark.anyio
async def test_silent_track_fails_as_analysis_failed() -> None:
    seen = await statuses_of(FakeDecoder(signal=signal_of(silence(12.0))))
    assert isinstance(seen[-1], Failed)
    assert seen[-1].code is FailureCode.ANALYSIS_FAILED


@pytest.mark.anyio
async def test_close_fails_queued_jobs_instead_of_running_them() -> None:
    board = memory_board()
    blobs = InMemoryBlobStore()
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    jobs = InMemoryJobQueue()
    worker = AnalysisWorker(
        decoder=decoder, board=board, blobs=blobs, jobs=jobs, encoder=fake_timeline
    )
    queued = [TrackId.of_content(name) for name in (b"one", b"two")]
    for track in queued:
        await board.record(track, Analysing.at(AnalysisStage.DECODING))
        await blobs.put(upload_key(track), track.value.encode())
        await jobs.enqueue(AnalysisJob(track_id=track))
    await worker.close()
    await worker.run()
    assert decoder.decoded == []
    assert all([isinstance(await board.current(track), Failed) for track in queued])
    assert all([await blobs.get(upload_key(track)) is None for track in queued])


@pytest.mark.anyio
async def test_unexpected_crash_fails_as_internal_and_keeps_the_worker_alive() -> None:
    seen = await statuses_of(FakeDecoder(decode_error=RuntimeError("disk on fire")))
    assert seen[-1] == Failed(code=FailureCode.INTERNAL, message="the analysis crashed")


@pytest.mark.anyio
async def test_upload_is_deleted_once_analysed() -> None:
    blobs = InMemoryBlobStore()
    await blobs.put(upload_key(TRACK), b"track")
    seen = await statuses_of(FakeDecoder(signal=signal_of(kick_train(128.0, 12.0))), blobs)
    assert isinstance(seen[-1], Ready)
    assert await blobs.get(upload_key(TRACK)) is None


@pytest.mark.anyio
async def test_upload_is_deleted_when_the_analysis_fails() -> None:
    blobs = InMemoryBlobStore()
    await blobs.put(upload_key(TRACK), b"track")
    seen = await statuses_of(FakeDecoder(decode_error=UndecodableAudioError("lost sync")), blobs)
    assert isinstance(seen[-1], Failed)
    assert await blobs.get(upload_key(TRACK)) is None


@pytest.mark.anyio
async def test_missing_upload_fails_the_track() -> None:
    seen = await statuses_of(FakeDecoder(), InMemoryBlobStore())
    assert seen[-1] == UPLOAD_GONE


@pytest.mark.anyio
async def test_timeline_is_stored_before_the_track_is_ready() -> None:
    blobs = InMemoryBlobStore()
    await blobs.put(upload_key(TRACK), b"track")
    await statuses_of(FakeDecoder(signal=signal_of(kick_train(128.0, 12.0))), blobs)
    timeline = await blobs.get(timeline_key(TRACK))
    assert timeline is not None
    assert timeline.startswith(b"timeline of ")


@pytest.mark.anyio
async def test_evicted_tracks_lose_their_timelines() -> None:
    board = memory_board(capacity=1)
    blobs = InMemoryBlobStore()
    jobs = InMemoryJobQueue()
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    worker = AnalysisWorker(
        decoder=decoder, board=board, blobs=blobs, jobs=jobs, encoder=fake_timeline
    )
    first, second = TrackId.of_content(b"first"), TrackId.of_content(b"second")
    for track in (first, second):
        await board.record(track, Analysing.at(AnalysisStage.DECODING))
        await blobs.put(upload_key(track), b"audio")
        await jobs.enqueue(AnalysisJob(track_id=track))

    async def stop_after_second() -> None:
        async for _ in board.watch(second):
            pass
        await worker.close()

    async with asyncio.TaskGroup() as group:
        group.create_task(stop_after_second())
        group.create_task(worker.run())
    assert await board.find(first) is None
    assert await blobs.get(timeline_key(first)) is None
    assert isinstance(await board.current(second), Ready)
    assert await blobs.get(timeline_key(second)) is not None


@pytest.mark.anyio
async def test_a_redelivered_job_for_a_settled_track_changes_nothing() -> None:
    board = memory_board()
    jobs = FakeJobQueue()
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    worker = AnalysisWorker(
        decoder=decoder, board=board, blobs=InMemoryBlobStore(), jobs=jobs, encoder=fake_timeline
    )
    await board.record(TRACK, READY)
    await jobs.enqueue(AnalysisJob(track_id=TRACK))
    await worker.run()
    assert decoder.decoded == []
    assert await board.current(TRACK) == READY
    assert jobs.finished == [AnalysisJob(track_id=TRACK)]


@pytest.mark.anyio
async def test_a_job_for_a_forgotten_track_drops_its_upload() -> None:
    blobs = InMemoryBlobStore()
    jobs = FakeJobQueue()
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    worker = AnalysisWorker(
        decoder=decoder, board=memory_board(), blobs=blobs, jobs=jobs, encoder=fake_timeline
    )
    await blobs.put(upload_key(TRACK), b"track")
    await jobs.enqueue(AnalysisJob(track_id=TRACK))
    await worker.run()
    assert decoder.decoded == []
    assert await blobs.get(upload_key(TRACK)) is None
    assert jobs.finished == [AnalysisJob(track_id=TRACK)]


class TimelineStoreGoesAway(InMemoryBlobStore):
    def __init__(self) -> None:
        super().__init__()
        self.failures_left = 1

    async def put(self, key: str, data: bytes) -> None:
        if key == timeline_key(TRACK) and self.failures_left:
            self.failures_left -= 1
            raise OSError("the store went away")
        await super().put(key, data)


@pytest.mark.anyio
async def test_a_job_interrupted_by_a_storage_error_can_be_retried() -> None:
    board = memory_board()
    blobs = TimelineStoreGoesAway()
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    await board.record(TRACK, Analysing.at(AnalysisStage.DECODING))
    await blobs.put(upload_key(TRACK), b"track")
    for _ in range(2):
        jobs = FakeJobQueue()
        await jobs.enqueue(AnalysisJob(track_id=TRACK))
        worker = AnalysisWorker(
            decoder=decoder, board=board, blobs=blobs, jobs=jobs, encoder=fake_timeline
        )
        with contextlib.suppress(OSError):
            await worker.run()
    assert isinstance(await board.current(TRACK), Ready)
    assert await blobs.get(upload_key(TRACK)) is None


@pytest.mark.anyio
async def test_a_job_that_keeps_stopping_the_worker_fails_the_track() -> None:
    board = memory_board()
    blobs = InMemoryBlobStore()
    jobs = FakeJobQueue()
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    worker = AnalysisWorker(
        decoder=decoder, board=board, blobs=blobs, jobs=jobs, encoder=fake_timeline
    )
    await board.record(TRACK, Analysing.at(AnalysisStage.DECODING))
    await blobs.put(upload_key(TRACK), b"track")
    job = AnalysisJob(track_id=TRACK, attempt=MAX_ATTEMPTS + 1)
    await jobs.enqueue(job)
    await worker.run()
    assert decoder.decoded == []
    assert await board.current(TRACK) == KEEPS_CRASHING
    assert await blobs.get(upload_key(TRACK)) is None
    assert jobs.finished == [job]
