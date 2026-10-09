import pytest

from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.adapters.memory import (
    InMemoryBlobStore,
    InMemoryJobQueue,
    InMemoryProgressFeed,
    InMemoryTrackStore,
)
from spectra.tracks.application.ports import AnalysisJob
from spectra.tracks.domain.track import Analysing, Failed, FailureCode, TrackId


def track(name: str) -> TrackId:
    return TrackId.of_content(name.encode())


def failed(message: str = "no") -> Failed:
    return Failed(code=FailureCode.ANALYSIS_FAILED, message=message)


@pytest.mark.anyio
async def test_store_evicts_the_least_recently_used_finished_track() -> None:
    store = InMemoryTrackStore(capacity=2)
    await store.save(track("a"), failed("a"))
    await store.save(track("b"), failed("b"))
    await store.find(track("a"))
    await store.save(track("c"), failed("c"))
    assert await store.evict_settled(keep=track("c")) == [track("b")]
    assert await store.find(track("b")) is None
    assert await store.find(track("a")) == failed("a")
    assert await store.find(track("c")) == failed("c")


@pytest.mark.anyio
async def test_store_never_evicts_a_running_analysis() -> None:
    store = InMemoryTrackStore(capacity=1)
    await store.save(track("a"), Analysing.at(AnalysisStage.TEMPO))
    await store.save(track("b"), Analysing.at(AnalysisStage.DECODING))
    assert await store.evict_settled(keep=track("b")) == []
    assert await store.find(track("a")) is not None
    assert await store.find(track("b")) is not None
    assert await store.analysing_count() == 2


@pytest.mark.anyio
async def test_a_track_that_just_settled_survives_eviction() -> None:
    store = InMemoryTrackStore(capacity=2)
    for name in "abc":
        await store.save(track(name), Analysing.at(AnalysisStage.TEMPO))
    await store.save(track("a"), failed("a"))
    assert await store.evict_settled(keep=track("a")) == []
    assert await store.find(track("a")) == failed("a")
    assert await store.analysing_count() == 2


@pytest.mark.anyio
async def test_store_forgets_a_deleted_track() -> None:
    store = InMemoryTrackStore(capacity=2)
    await store.save(track("a"), failed("a"))
    await store.delete(track("a"))
    await store.delete(track("a"))
    assert await store.find(track("a")) is None


@pytest.mark.anyio
async def test_feed_delivers_to_subscribers_of_that_track_only() -> None:
    feed = InMemoryProgressFeed()
    async with feed.subscribe(track("a")) as updates:
        await feed.publish(track("b"), failed("b"))
        await feed.publish(track("a"), failed("a"))
        assert await anext(updates) == failed("a")


@pytest.mark.anyio
async def test_feed_forgets_subscribers_that_left() -> None:
    feed = InMemoryProgressFeed()
    async with feed.subscribe(track("a")):
        pass
    await feed.publish(track("a"), failed())
    async with feed.subscribe(track("a")) as updates:
        await feed.publish(track("a"), failed("later"))
        assert await anext(updates) == failed("later")


@pytest.mark.anyio
async def test_job_queue_hands_out_jobs_in_order() -> None:
    queue = InMemoryJobQueue()
    await queue.enqueue(AnalysisJob(track_id=track("a")))
    await queue.enqueue(AnalysisJob(track_id=track("b")))
    assert await queue.take() == AnalysisJob(track_id=track("a"))
    assert await queue.take() == AnalysisJob(track_id=track("b"))


@pytest.mark.anyio
async def test_closing_the_job_queue_returns_pending_jobs_and_ends_take() -> None:
    queue = InMemoryJobQueue()
    await queue.enqueue(AnalysisJob(track_id=track("a")))
    assert await queue.close() == [AnalysisJob(track_id=track("a"))]
    assert await queue.take() is None


@pytest.mark.anyio
async def test_blob_store_puts_gets_and_deletes() -> None:
    blobs = InMemoryBlobStore()
    await blobs.put("uploads/a", b"bytes")
    assert await blobs.get("uploads/a") == b"bytes"
    await blobs.delete("uploads/a")
    await blobs.delete("uploads/a")
    assert await blobs.get("uploads/a") is None
