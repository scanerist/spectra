import asyncio

import pytest

from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.application.registry import TrackRegistry
from spectra.tracks.domain.errors import TrackNotFoundError
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, TrackId, TrackStatus


def track(name: str) -> TrackId:
    return TrackId.of_content(name.encode())


def failed(message: str = "no") -> Failed:
    return Failed(code=FailureCode.ANALYSIS_FAILED, message=message)


def test_unknown_track_is_not_found() -> None:
    with pytest.raises(TrackNotFoundError):
        TrackRegistry(capacity=2).status(track("a"))


def test_put_then_status_returns_the_latest() -> None:
    registry = TrackRegistry(capacity=2)
    registry.put(track("a"), Analysing.at(AnalysisStage.DECODING))
    registry.put(track("a"), failed())
    assert registry.status(track("a")) == failed()


def test_registry_evicts_the_least_recently_used_finished_track() -> None:
    registry = TrackRegistry(capacity=2)
    registry.put(track("a"), failed("a"))
    registry.put(track("b"), failed("b"))
    registry.status(track("a"))
    registry.put(track("c"), failed("c"))
    assert registry.find(track("b")) is None
    assert registry.find(track("a")) == failed("a")
    assert registry.find(track("c")) == failed("c")


def test_registry_never_evicts_a_running_analysis() -> None:
    registry = TrackRegistry(capacity=1)
    registry.put(track("a"), Analysing.at(AnalysisStage.TEMPO))
    registry.put(track("b"), Analysing.at(AnalysisStage.DECODING))
    assert registry.find(track("a")) is not None
    assert registry.find(track("b")) is not None


def test_a_track_that_just_settled_survives_eviction() -> None:
    registry = TrackRegistry(capacity=2)
    for name in "abc":
        registry.put(track(name), Analysing.at(AnalysisStage.TEMPO))
    registry.put(track("a"), failed("a"))
    assert registry.find(track("a")) == failed("a")
    assert registry.analysing_count() == 2


@pytest.mark.anyio
async def test_watch_yields_the_current_status_then_changes_until_final() -> None:
    registry = TrackRegistry(capacity=4)
    registry.put(track("a"), Analysing.at(AnalysisStage.DECODING))
    seen: list[TrackStatus] = []

    async def follow() -> None:
        seen.extend([status async for status in registry.watch(track("a"))])

    async with asyncio.TaskGroup() as group:
        group.create_task(follow())
        await asyncio.sleep(0)
        registry.put(track("a"), Analysing.at(AnalysisStage.SPECTRUM))
        registry.put(track("a"), failed())
    assert seen == [
        Analysing.at(AnalysisStage.DECODING),
        Analysing.at(AnalysisStage.SPECTRUM),
        failed(),
    ]


@pytest.mark.anyio
async def test_watch_of_a_finished_track_yields_once() -> None:
    registry = TrackRegistry(capacity=4)
    registry.put(track("a"), failed())
    assert [status async for status in registry.watch(track("a"))] == [failed()]


@pytest.mark.anyio
async def test_watch_of_an_unknown_track_is_not_found() -> None:
    with pytest.raises(TrackNotFoundError):
        async for _ in TrackRegistry(capacity=1).watch(track("a")):
            pass
