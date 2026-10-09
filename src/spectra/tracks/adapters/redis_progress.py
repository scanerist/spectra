from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from typing import Final

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from spectra.tracks.adapters.status_records import status_from_json, status_json
from spectra.tracks.domain.errors import TracksError
from spectra.tracks.domain.track import TrackId, TrackStatus

PROGRESS_PREFIX: Final = "spectra:progress:"
SUBSCRIBE_TIMEOUT_S: Final = 5.0


class SubscriptionError(TracksError):
    pass


class RedisProgressFeed:
    def __init__(self, *, client: Redis, prefix: str = PROGRESS_PREFIX) -> None:
        self._client = client
        self._prefix = prefix

    async def publish(self, track_id: TrackId, status: TrackStatus) -> None:
        await self._client.publish(self._channel(track_id), status_json(status))

    @asynccontextmanager
    async def subscribe(self, track_id: TrackId) -> AsyncIterator[AsyncIterator[TrackStatus]]:
        async with aclosing(self._client.pubsub()) as pubsub:
            await pubsub.subscribe(self._channel(track_id))
            await confirm_subscription(pubsub)
            yield statuses(pubsub)

    def _channel(self, track_id: TrackId) -> str:
        return f"{self._prefix}{track_id.value}"


async def confirm_subscription(pubsub: PubSub) -> None:
    message = await pubsub.get_message(timeout=SUBSCRIBE_TIMEOUT_S)
    match message:
        case {"type": "subscribe"}:
            return
    raise SubscriptionError(f"expected a subscribe confirmation, got {message!r}")


async def statuses(pubsub: PubSub) -> AsyncIterator[TrackStatus]:
    while True:
        match await pubsub.get_message(ignore_subscribe_messages=True, timeout=None):
            case {"type": "message", "data": bytes() as data}:
                yield status_from_json(data)
