import math
from typing import Final

from redis.asyncio import Redis

from spectra.tracks.domain.quota import QuotaDecision, UploadQuotaPolicy

QUOTA_PREFIX: Final = "spectra:quota:"


class RedisUploadQuota:
    def __init__(
        self, *, client: Redis, policy: UploadQuotaPolicy, prefix: str = QUOTA_PREFIX
    ) -> None:
        self._redis = client
        self._policy = policy
        self._prefix = prefix

    async def spend(self, client: str) -> QuotaDecision:
        seconds, microseconds = await self._redis.time()
        now_s = seconds + microseconds / 1_000_000
        key = f"{self._prefix}{self._policy.window_of(now_s)}:{client}"
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, math.ceil(self._policy.window_s), nx=True)
            used, _ = await pipeline.execute()
        return self._policy.decide(used=int(used), now_s=now_s)
