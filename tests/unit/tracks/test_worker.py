import asyncio

import pytest

from spectra.analysis.domain.errors import UndecodableAudioError
from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.application.worker import AnalysisWorker
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


async def statuses_of(decoder: FakeDecoder) -> list[TrackStatus]:
    board = memory_board()
    worker = AnalysisWorker(decoder=decoder, board=board)
    await board.record(TRACK, Analysing.at(AnalysisStage.DECODING))
    seen: list[TrackStatus] = []

    async def follow() -> None:
        seen.extend([status async for status in board.watch(TRACK)])
        await worker.close()

    async with asyncio.TaskGroup() as group:
        group.create_task(follow())
        group.create_task(worker.run())
        worker.enqueue(AnalysisJob(track_id=TRACK, data=b"track"))
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
    decoder = FakeDecoder(signal=signal_of(kick_train(128.0, 12.0)))
    worker = AnalysisWorker(decoder=decoder, board=board)
    queued = [TrackId.of_content(name) for name in (b"one", b"two")]
    for track in queued:
        await board.record(track, Analysing.at(AnalysisStage.DECODING))
        worker.enqueue(AnalysisJob(track_id=track, data=track.value.encode()))
    await worker.close()
    await worker.run()
    assert decoder.decoded == []
    assert all([isinstance(await board.current(track), Failed) for track in queued])


@pytest.mark.anyio
async def test_unexpected_crash_fails_as_internal_and_keeps_the_worker_alive() -> None:
    seen = await statuses_of(FakeDecoder(decode_error=RuntimeError("disk on fire")))
    assert seen[-1] == Failed(code=FailureCode.INTERNAL, message="the analysis crashed")
