import asyncio

import pytest

from spectra.analysis.domain.errors import UndecodableAudioError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.adapters.memory import InMemoryBlobStore, InMemoryJobQueue
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.application.worker import UPLOAD_GONE, AnalysisWorker
from spectra.tracks.domain.blobs import upload_key
from spectra.tracks.domain.track import (
    Analysing,
    Failed,
    FailureCode,
    Ready,
    TrackId,
    TrackStatus,
)
from tests.fakes import FakeDecoder, memory_board
from tests.signals import kick_train, signal_of, silence

TRACK = TrackId.of_content(b"track")


async def statuses_of(
    decoder: FakeDecoder, blobs: InMemoryBlobStore | None = None
) -> list[TrackStatus]:
    board = memory_board()
    store = blobs or InMemoryBlobStore()
    jobs = InMemoryJobQueue()
    worker = AnalysisWorker(decoder=decoder, board=board, blobs=store, jobs=jobs)
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
    assert seen[-1].analysis.grid.tempo.bpm == pytest.approx(128.0, abs=0.5)


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
    worker = AnalysisWorker(decoder=decoder, board=board, blobs=blobs, jobs=jobs)
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
