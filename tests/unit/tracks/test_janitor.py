import pytest

from spectra.tracks.adapters.memory import (
    InMemoryBlobStore,
    InMemoryProgressFeed,
    InMemoryTrackStore,
)
from spectra.tracks.application.janitor import ABANDONED, SWEEP_BATCH_SIZE, Janitor
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.blobs import timeline_key, upload_key
from spectra.tracks.domain.track import TrackId
from tests.fakes import FakeTrackExpiry
from tests.statuses import ANALYSING, READY, track

DAY_S = 86_400.0
RETENTION_S = 30 * DAY_S
HOUR_S = 3_600.0
STALLED_AFTER_S = 2 * HOUR_S


async def janitor_for(
    unseen_s: dict[TrackId, float], *, capacity: int = 8
) -> tuple[Janitor, StatusBoard, InMemoryBlobStore, FakeTrackExpiry]:
    store = InMemoryTrackStore(capacity=capacity)
    board = StatusBoard(store=store, feed=InMemoryProgressFeed())
    blobs = InMemoryBlobStore()
    for track_id in unseen_s:
        await board.record(track_id, READY)
        await blobs.put(timeline_key(track_id), b"timeline")
        await blobs.put(upload_key(track_id), b"upload")
    expiry = FakeTrackExpiry(store, unseen_s=unseen_s)
    janitor = Janitor(
        expiry=expiry,
        feed=InMemoryProgressFeed(),
        blobs=blobs,
        retention_s=RETENTION_S,
        stalled_after_s=STALLED_AFTER_S,
    )
    return janitor, board, blobs, expiry


@pytest.mark.anyio
async def test_a_track_unseen_past_retention_is_removed_with_its_blobs() -> None:
    janitor, board, blobs, _ = await janitor_for({track("old"): 31 * DAY_S})
    assert await janitor.sweep() == 1
    assert await board.find(track("old")) is None
    assert await blobs.get(timeline_key(track("old"))) is None
    assert await blobs.get(upload_key(track("old"))) is None


@pytest.mark.anyio
async def test_a_recently_seen_track_is_kept() -> None:
    janitor, board, blobs, _ = await janitor_for({track("new"): 29 * DAY_S})
    assert await janitor.sweep() == 0
    assert await board.find(track("new")) == READY
    assert await blobs.get(timeline_key(track("new"))) == b"timeline"


@pytest.mark.anyio
async def test_sweeping_continues_past_one_batch() -> None:
    unseen_s = {track(f"old-{index}"): 40 * DAY_S for index in range(SWEEP_BATCH_SIZE + 3)}
    janitor, _, _, expiry = await janitor_for(unseen_s, capacity=len(unseen_s))
    assert await janitor.sweep() == SWEEP_BATCH_SIZE + 3
    assert expiry.limits == [SWEEP_BATCH_SIZE] * 3


@pytest.mark.anyio
async def test_an_analysis_without_news_for_too_long_is_abandoned_and_announced() -> None:
    store = InMemoryTrackStore(capacity=8)
    feed = InMemoryProgressFeed()
    board = StatusBoard(store=store, feed=feed)
    blobs = InMemoryBlobStore()
    for name in ("stalled", "running"):
        await board.record(track(name), ANALYSING)
        await blobs.put(upload_key(track(name)), b"upload")
    expiry = FakeTrackExpiry(
        store,
        unseen_s={},
        stalled_s={track("stalled"): 3 * HOUR_S, track("running"): HOUR_S},
    )
    janitor = Janitor(
        expiry=expiry,
        feed=feed,
        blobs=blobs,
        retention_s=RETENTION_S,
        stalled_after_s=STALLED_AFTER_S,
    )
    async with feed.subscribe(track("stalled")) as updates:
        assert await janitor.abandon() == 1
        assert await anext(updates) == ABANDONED
    assert await board.find(track("stalled")) == ABANDONED
    assert await blobs.get(upload_key(track("stalled"))) is None
    assert await board.find(track("running")) == ANALYSING
    assert await blobs.get(upload_key(track("running"))) == b"upload"
