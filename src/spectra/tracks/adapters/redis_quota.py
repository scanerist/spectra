import math
from typing import Final

from redis.asyncio import Redis

from spectra.tracks.domain.quota import QuotaDecision, UploadQuotaPolicy

QUOTA_PREFIX: Final = "spectra:quota:"
REFUND_SCRIPT: Final = """
if tonumber(redis.call('GET', KEYS[1]) or '0') > 0 then
    return redis.call('DECR', KEYS[1])
end
return 0
"""


class RedisUploadQuota:
    def __init__(
        self, *, client: Redis, policy: UploadQuotaPolicy, prefix: str = QUOTA_PREFIX
    ) -> None:
        self._redis = client
        self._policy = policy
        self._prefix = prefix
        self._refund = client.register_script(REFUND_SCRIPT)

    async def spend(self, client: str) -> QuotaDecision:
        now_s = await self._now_s()
        key = self._key(client, self._policy.window_of(now_s))
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, math.ceil(self._policy.window_s), nx=True)
            used, _ = await pipeline.execute()
        return self._policy.decide(used=int(used), now_s=now_s)

    async def refund(self, client: str, *, window: int) -> None:
        await self._refund(keys=[self._key(client, window)])

    async def _now_s(self) -> float:
        seconds, microseconds = await self._redis.time()
        return seconds + microseconds / 1_000_000

    def _key(self, client: str, window: int) -> str:
        return f"{self._prefix}{window}:{client}"
