import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from spectra.tracks.adapters.redis_quota import RedisUploadQuota
from spectra.tracks.domain.quota import UploadQuotaPolicy

REDIS_URL = os.environ.get("SPECTRA_TEST_REDIS_URL")

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


def quota(client: Redis, *, uploads: int, window_s: float) -> RedisUploadQuota:
    return RedisUploadQuota(
        client=client,
        policy=UploadQuotaPolicy(uploads=uploads, window_s=window_s),
        prefix=f"spectra:test:{uuid.uuid4().hex}:",
    )


async def test_uploads_over_the_quota_are_refused_until_the_window_ends(client: Redis) -> None:
    hourly = quota(client, uploads=2, window_s=3_600.0)
    decisions = [await hourly.spend("1.2.3.4") for _ in range(3)]
    assert [decision.allowed for decision in decisions] == [True, True, False]
    assert 0.0 < decisions[-1].retry_after_s <= 3_600.0


async def test_each_client_has_its_own_quota(client: Redis) -> None:
    single = quota(client, uploads=1, window_s=3_600.0)
    assert (await single.spend("1.2.3.4")).allowed
    assert (await single.spend("5.6.7.8")).allowed
    assert not (await single.spend("1.2.3.4")).allowed


async def test_the_quota_starts_over_in_the_next_window(client: Redis) -> None:
    short = quota(client, uploads=1, window_s=1.0)
    await short.spend("1.2.3.4")
    refused = await short.spend("1.2.3.4")
    assert not refused.allowed
    await asyncio.sleep(refused.retry_after_s + 0.05)
    assert (await short.spend("1.2.3.4")).allowed


async def test_counters_expire_with_their_window(client: Redis) -> None:
    prefix = f"spectra:test:{uuid.uuid4().hex}:"
    policy = UploadQuotaPolicy(uploads=5, window_s=3_600.0)
    await RedisUploadQuota(client=client, policy=policy, prefix=prefix).spend("1.2.3.4")
    keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
    assert len(keys) == 1
    assert 0 < await client.ttl(keys[0]) <= 3_600


async def test_a_refunded_upload_frees_its_place(client: Redis) -> None:
    single = quota(client, uploads=1, window_s=3_600.0)
    await single.spend("1.2.3.4")
    await single.refund("1.2.3.4")
    assert (await single.spend("1.2.3.4")).allowed
    assert not (await single.spend("1.2.3.4")).allowed


async def test_a_refund_without_uploads_changes_nothing(client: Redis) -> None:
    single = quota(client, uploads=1, window_s=3_600.0)
    await single.refund("1.2.3.4")
    assert (await single.spend("1.2.3.4")).allowed
    assert not (await single.spend("1.2.3.4")).allowed
