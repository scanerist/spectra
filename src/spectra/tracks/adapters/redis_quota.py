import math
import uuid
from typing import Final

from redis.asyncio import Redis

from spectra.tracks.domain.quota import QuotaDecision, UploadQuotaPolicy, UploadSource

QUOTA_PREFIX: Final = "spectra:quota:"
SPEND_SCRIPT: Final = """
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local full = {}
for index, key in ipairs(KEYS) do
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
    if redis.call('ZCARD', key) >= tonumber(ARGV[3 + index]) then
        table.insert(full, redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')[2])
    end
end
if #full > 0 then
    return full
end
for _, key in ipairs(KEYS) do
    redis.call('ZADD', key, now_ms, ARGV[3])
    redis.call('PEXPIRE', key, window_ms)
end
return full
"""
REFUND_SCRIPT: Final = """
local latest = redis.call('ZPOPMAX', KEYS[1])
if #latest == 0 then
    return 0
end
for index = 2, #KEYS do
    redis.call('ZREM', KEYS[index], latest[1])
end
return 1
"""


class RedisUploadQuota:
    def __init__(
        self, *, client: Redis, policy: UploadQuotaPolicy, prefix: str = QUOTA_PREFIX
    ) -> None:
        self._redis = client
        self._policy = policy
        self._prefix = prefix
        self._spend = client.register_script(SPEND_SCRIPT)
        self._refund = client.register_script(REFUND_SCRIPT)

    async def spend(self, source: UploadSource) -> QuotaDecision:
        now_ms = await self._now_ms()
        scopes = self._policy.scopes(source)
        full_ms = await self._spend(
            keys=[self._key(scope.key) for scope in scopes],
            args=[
                now_ms,
                math.ceil(self._policy.window_s * 1_000),
                f"{now_ms}:{uuid.uuid4().hex}",
                *[scope.limit for scope in scopes],
            ],
        )
        oldest_s = [float(oldest_ms) / 1_000 for oldest_ms in full_ms]
        return self._policy.decide(oldest_in_full_scopes_s=oldest_s, now_s=now_ms / 1_000)

    async def refund(self, source: UploadSource) -> None:
        await self._refund(keys=[self._key(scope.key) for scope in self._policy.scopes(source)])

    async def _now_ms(self) -> int:
        seconds, microseconds = await self._redis.time()
        return seconds * 1_000 + microseconds // 1_000

    def _key(self, scope_key: str) -> str:
        return f"{self._prefix}{scope_key}"
