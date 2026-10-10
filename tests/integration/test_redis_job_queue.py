import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from spectra.tracks.adapters.redis_jobs import JobStream, RedisJobQueue
from spectra.tracks.application.ports import AnalysisJob
from tests.statuses import track

REDIS_URL = os.environ.get("SPECTRA_TEST_REDIS_URL")
WAIT_S = 5.0

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(REDIS_URL is None, reason="SPECTRA_TEST_REDIS_URL is not set"),
]


def job(name: str) -> AnalysisJob:
    return AnalysisJob(track_id=track(name))


@pytest.fixture
def stream_key() -> str:
    return f"spectra:test:{uuid.uuid4().hex}:jobs"


@pytest.fixture
async def client(stream_key: str) -> AsyncIterator[Redis]:
    assert REDIS_URL is not None
    client = Redis.from_url(REDIS_URL)
    yield client
    await client.delete(stream_key)
    await client.aclose()


async def worker_queue(
    client: Redis, stream_key: str, consumer: str, *, claim_after_s: float = 300.0
) -> RedisJobQueue:
    queue = RedisJobQueue(
        client=client,
        stream=JobStream(key=stream_key, consumer=consumer),
        claim_after_s=claim_after_s,
        block_s=0.05,
    )
    await queue.ensure_group()
    return queue


async def take(queue: RedisJobQueue) -> AnalysisJob | None:
    async with asyncio.timeout(WAIT_S):
        return await queue.take()


async def test_a_running_redis_answers(client: Redis, stream_key: str) -> None:
    queue = await worker_queue(client, stream_key, "a")
    assert await queue.ping()


async def test_an_enqueued_job_is_taken(client: Redis, stream_key: str) -> None:
    queue = await worker_queue(client, stream_key, "a")
    await queue.enqueue(job("a"))
    assert await take(queue) == job("a")


async def test_jobs_are_taken_in_order(client: Redis, stream_key: str) -> None:
    queue = await worker_queue(client, stream_key, "a")
    for name in "abc":
        await queue.enqueue(job(name))
    assert [await take(queue) for _ in "abc"] == [job("a"), job("b"), job("c")]


async def test_closing_stops_a_waiting_take(client: Redis, stream_key: str) -> None:
    queue = await worker_queue(client, stream_key, "a")
    async with asyncio.TaskGroup() as group:
        waiting = group.create_task(take(queue))
        await asyncio.sleep(0.1)
        assert await queue.close() == []
    assert waiting.result() is None


async def test_closing_leaves_queued_jobs_for_the_next_worker(
    client: Redis, stream_key: str
) -> None:
    first = await worker_queue(client, stream_key, "a")
    await first.enqueue(job("a"))
    assert await first.close() == []
    second = await worker_queue(client, stream_key, "b")
    assert await take(second) == job("a")


async def test_a_finished_job_leaves_the_stream(client: Redis, stream_key: str) -> None:
    queue = await worker_queue(client, stream_key, "a")
    await queue.enqueue(job("a"))
    taken = await take(queue)
    assert taken is not None
    await queue.done(taken)
    assert await client.xlen(stream_key) == 0
    assert (await client.xpending(stream_key, "workers"))["pending"] == 0


async def test_a_job_left_by_a_crashed_worker_is_taken_again(
    client: Redis, stream_key: str
) -> None:
    crashed = await worker_queue(client, stream_key, "a")
    await crashed.enqueue(job("a"))
    assert await take(crashed) == job("a")
    survivor = await worker_queue(client, stream_key, "b", claim_after_s=0.1)
    assert await take(survivor) == AnalysisJob(track_id=track("a"), attempt=2)


async def test_every_redelivery_counts_as_another_attempt(client: Redis, stream_key: str) -> None:
    first = await worker_queue(client, stream_key, "a")
    await first.enqueue(job("a"))
    await take(first)
    for attempt, consumer in enumerate("bc", start=2):
        survivor = await worker_queue(client, stream_key, consumer, claim_after_s=0.05)
        taken = await take(survivor)
        assert taken is not None
        assert taken.attempt == attempt


async def test_a_restarted_worker_resumes_its_own_unfinished_job(
    client: Redis, stream_key: str
) -> None:
    before = await worker_queue(client, stream_key, "a")
    await before.enqueue(job("a"))
    await before.enqueue(job("b"))
    assert await take(before) == job("a")
    after = await worker_queue(client, stream_key, "a")
    resumed = await take(after)
    assert resumed is not None
    assert resumed.track_id == track("a")
    await after.done(resumed)
    assert await take(after) == job("b")


async def test_ensuring_the_group_again_keeps_queued_jobs(client: Redis, stream_key: str) -> None:
    queue = await worker_queue(client, stream_key, "a")
    await queue.enqueue(job("a"))
    await queue.ensure_group()
    assert await take(queue) == job("a")


async def take_until_all_taken(
    queue: RedisJobQueue, taken: list[AnalysisJob], *, total: int, workers: list[RedisJobQueue]
) -> None:
    while (next_job := await queue.take()) is not None:
        taken.append(next_job)
        if len(taken) == total:
            for worker in workers:
                await worker.close()


async def test_two_live_workers_never_take_the_same_job(client: Redis, stream_key: str) -> None:
    workers = [await worker_queue(client, stream_key, consumer) for consumer in "ab"]
    jobs = [job(f"track-{index}") for index in range(40)]
    for queued in jobs:
        await workers[0].enqueue(queued)
    taken: list[AnalysisJob] = []
    async with asyncio.timeout(WAIT_S), asyncio.TaskGroup() as group:
        for worker in workers:
            group.create_task(take_until_all_taken(worker, taken, total=len(jobs), workers=workers))
    assert sorted(taken, key=lambda taken_job: taken_job.track_id.value) == sorted(
        jobs, key=lambda queued: queued.track_id.value
    )
