import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from spectra.analysis.domain.track_analysis import AnalysisStage
from spectra.tracks.adapters.memory import InMemoryTrackStore
from spectra.tracks.adapters.redis_progress import RedisProgressFeed
from spectra.tracks.application.status_board import StatusBoard
from spectra.tracks.domain.track import Analysing, TrackStatus
from tests.statuses import ANALYSING, FAILED, READY, track

REDIS_URL = os.environ.get("SPECTRA_TEST_REDIS_URL")
WAIT_S = 5.0

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(REDIS_URL is None, reason="SPECTRA_TEST_REDIS_URL is not set"),
]


@pytest.fixture
async def client() -> AsyncIterator[Redis]:
    assert REDIS_URL is not None
    client = Redis.from_url(REDIS_URL)
    yield client
    await client.aclose()


@pytest.fixture
def feed(client: Redis) -> RedisProgressFeed:
    return RedisProgressFeed(client=client, prefix=f"spectra:test:{uuid.uuid4().hex}:")


async def next_status(updates: AsyncIterator[TrackStatus]) -> TrackStatus:
    async with asyncio.timeout(WAIT_S):
        return await anext(updates)


async def test_a_published_status_reaches_a_subscriber(feed: RedisProgressFeed) -> None:
    async with feed.subscribe(track("a")) as updates:
        await feed.publish(track("a"), READY)
        assert await next_status(updates) == READY


async def test_statuses_arrive_in_publishing_order(feed: RedisProgressFeed) -> None:
    async with feed.subscribe(track("a")) as updates:
        for status in (ANALYSING, FAILED):
            await feed.publish(track("a"), status)
        assert [await next_status(updates), await next_status(updates)] == [ANALYSING, FAILED]


async def test_a_subscriber_hears_only_its_own_track(feed: RedisProgressFeed) -> None:
    async with feed.subscribe(track("b")) as updates:
        await feed.publish(track("a"), FAILED)
        await feed.publish(track("b"), READY)
        assert await next_status(updates) == READY


async def test_publishing_without_subscribers_succeeds(feed: RedisProgressFeed) -> None:
    await feed.publish(track("a"), READY)


async def test_leaving_unsubscribes_from_the_track(client: Redis) -> None:
    prefix = f"spectra:test:{uuid.uuid4().hex}:"
    feed = RedisProgressFeed(client=client, prefix=prefix)
    channel = f"{prefix}{track('a').value}"
    async with feed.subscribe(track("a")):
        assert await client.pubsub_numsub(channel) == [(channel.encode(), 1)]
    assert await client.pubsub_numsub(channel) == [(channel.encode(), 0)]


async def test_a_board_watches_a_track_through_redis(feed: RedisProgressFeed) -> None:
    board = StatusBoard(store=InMemoryTrackStore(capacity=8), feed=feed)
    await board.record(track("a"), Analysing.at(AnalysisStage.DECODING))
    seen: list[TrackStatus] = []

    async def follow() -> None:
        async with asyncio.timeout(WAIT_S):
            seen.extend([status async for status in board.watch(track("a"))])

    async with asyncio.TaskGroup() as group:
        group.create_task(follow())
        await asyncio.sleep(0.1)
        await board.record(track("a"), ANALYSING)
        await board.record(track("a"), READY)
    assert seen == [Analysing.at(AnalysisStage.DECODING), ANALYSING, READY]
