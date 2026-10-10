import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from spectra.tracks.adapters.redis_quota import RedisUploadQuota
from spectra.tracks.domain.quota import UploadQuotaPolicy, UploadSource

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


FIRST = UploadSource(address="1.2.3.4", network="1.2.3.4")
SECOND = UploadSource(address="5.6.7.8", network="5.6.7.8")
HOME = UploadSource(address="2001:db8:1:1::/64", network="2001:db8:1::/48")
NEIGHBOUR = UploadSource(address="2001:db8:1:2::/64", network="2001:db8:1::/48")


def quota(
    client: Redis,
    *,
    uploads: int,
    window_s: float,
    per_network: int = 100,
    total: int = 1_000,
) -> RedisUploadQuota:
    policy = UploadQuotaPolicy(
        per_address=uploads, per_network=per_network, total=total, window_s=window_s
    )
    return RedisUploadQuota(
        client=client, policy=policy, prefix=f"spectra:test:{uuid.uuid4().hex}:"
    )


async def test_uploads_over_the_quota_are_refused_until_the_window_ends(client: Redis) -> None:
    hourly = quota(client, uploads=2, window_s=3_600.0)
    decisions = [await hourly.spend(FIRST) for _ in range(3)]
    assert [decision.allowed for decision in decisions] == [True, True, False]
    assert 0.0 < decisions[-1].retry_after_s <= 3_600.0


async def test_each_client_has_its_own_quota(client: Redis) -> None:
    single = quota(client, uploads=1, window_s=3_600.0)
    assert (await single.spend(FIRST)).allowed
    assert (await single.spend(SECOND)).allowed
    assert not (await single.spend(FIRST)).allowed


async def test_the_window_slides_past_the_oldest_upload(client: Redis) -> None:
    short = quota(client, uploads=1, window_s=1.0)
    await short.spend(FIRST)
    refused = await short.spend(FIRST)
    assert not refused.allowed
    await asyncio.sleep(refused.retry_after_s + 0.05)
    assert (await short.spend(FIRST)).allowed


async def test_counters_expire_with_their_window(client: Redis) -> None:
    prefix = f"spectra:test:{uuid.uuid4().hex}:"
    policy = UploadQuotaPolicy(per_address=5, per_network=5, total=5, window_s=3_600.0)
    await RedisUploadQuota(client=client, policy=policy, prefix=prefix).spend(FIRST)
    keys = [key async for key in client.scan_iter(match=f"{prefix}*")]
    assert len(keys) == 3
    assert all([0 < await client.ttl(key) <= 3_600 for key in keys])


async def test_a_refunded_upload_frees_its_place(client: Redis) -> None:
    single = quota(client, uploads=1, window_s=3_600.0)
    await single.spend(FIRST)
    await single.refund(FIRST)
    assert (await single.spend(FIRST)).allowed
    assert not (await single.spend(FIRST)).allowed


async def test_a_refund_without_uploads_changes_nothing(client: Redis) -> None:
    single = quota(client, uploads=1, window_s=3_600.0)
    await single.refund(FIRST)
    assert (await single.spend(FIRST)).allowed
    assert not (await single.spend(FIRST)).allowed


async def test_addresses_of_one_network_share_its_quota(client: Redis) -> None:
    shared = quota(client, uploads=2, per_network=3, window_s=3_600.0)
    decisions = [await shared.spend(source) for source in (HOME, HOME, NEIGHBOUR, NEIGHBOUR)]
    assert [decision.allowed for decision in decisions] == [True, True, True, False]


async def test_everyone_shares_the_total_quota(client: Redis) -> None:
    shared = quota(client, uploads=2, total=2, window_s=3_600.0)
    decisions = [await shared.spend(source) for source in (FIRST, SECOND, HOME)]
    assert [decision.allowed for decision in decisions] == [True, True, False]


async def test_a_refused_upload_does_not_use_up_the_quota(client: Redis) -> None:
    short = quota(client, uploads=1, window_s=1.0)
    await short.spend(FIRST)
    refused = [await short.spend(FIRST) for _ in range(3)]
    assert not any(decision.allowed for decision in refused)
    await asyncio.sleep(max(decision.retry_after_s for decision in refused) + 0.05)
    assert (await short.spend(FIRST)).allowed


async def test_after_lowering_a_limit_the_wait_lasts_until_enough_uploads_leave(
    client: Redis,
) -> None:
    prefix = f"spectra:test:{uuid.uuid4().hex}:"

    def with_limit(uploads: int) -> RedisUploadQuota:
        policy = UploadQuotaPolicy(per_address=uploads, per_network=100, total=1_000, window_s=2.0)
        return RedisUploadQuota(client=client, policy=policy, prefix=prefix)

    generous = with_limit(3)
    await generous.spend(FIRST)
    await asyncio.sleep(0.5)
    await generous.spend(FIRST)
    await generous.spend(FIRST)
    refused = await with_limit(1).spend(FIRST)
    assert not refused.allowed
    assert refused.retry_after_s > 1.7
