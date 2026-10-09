import asyncio

import pytest

from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.domain.errors import TrackNotFoundError
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, TrackId, TrackStatus
from tests.fakes import memory_board

TRACK = TrackId.of_content(b"a")
FAILED = Failed(code=FailureCode.ANALYSIS_FAILED, message="no")


@pytest.mark.anyio
async def test_unknown_track_is_not_found() -> None:
    board = memory_board()
    assert await board.find(TRACK) is None
    with pytest.raises(TrackNotFoundError):
        await board.current(TRACK)


@pytest.mark.anyio
async def test_record_then_current_returns_the_latest() -> None:
    board = memory_board()
    await board.record(TRACK, Analysing.at(AnalysisStage.DECODING))
    await board.record(TRACK, FAILED)
    assert await board.current(TRACK) == FAILED
    assert await board.analysing_count() == 0


@pytest.mark.anyio
async def test_watch_yields_the_current_status_then_changes_until_final() -> None:
    board = memory_board()
    await board.record(TRACK, Analysing.at(AnalysisStage.DECODING))
    seen: list[TrackStatus] = []

    async def follow() -> None:
        seen.extend([status async for status in board.watch(TRACK)])

    async with asyncio.TaskGroup() as group:
        group.create_task(follow())
        await asyncio.sleep(0)
        await board.record(TRACK, Analysing.at(AnalysisStage.SPECTRUM))
        await board.record(TRACK, FAILED)
    assert seen == [
        Analysing.at(AnalysisStage.DECODING),
        Analysing.at(AnalysisStage.SPECTRUM),
        FAILED,
    ]


@pytest.mark.anyio
async def test_watch_of_a_finished_track_yields_once() -> None:
    board = memory_board()
    await board.record(TRACK, FAILED)
    assert [status async for status in board.watch(TRACK)] == [FAILED]


@pytest.mark.anyio
async def test_watch_of_an_unknown_track_is_not_found() -> None:
    with pytest.raises(TrackNotFoundError):
        async for _ in memory_board().watch(TRACK):
            pass
