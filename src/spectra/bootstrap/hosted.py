import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from redis.asyncio import BlockingConnectionPool, Redis
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from spectra.bootstrap.settings import HostedSettings, PostgresSettings, RedisSettings
from spectra.tracks.adapters.postgres import PostgresTrackStore, upgrade_schema
from spectra.tracks.adapters.redis_jobs import JobStream, RedisJobQueue
from spectra.tracks.adapters.redis_progress import SUBSCRIBE_TIMEOUT_S, RedisProgressFeed
from spectra.tracks.adapters.s3 import S3BlobStore, S3Endpoint, s3_client

PUBLISH_CONNECTIONS: Final = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class HostedAdapters:
    engine: AsyncEngine
    redis: Redis
    events: Redis
    store: PostgresTrackStore
    feed: RedisProgressFeed
    blobs: S3BlobStore
    jobs: RedisJobQueue


@asynccontextmanager
async def open_hosted(
    settings: HostedSettings, *, consumer: str, max_subscriptions: int = 0
) -> AsyncIterator[HostedAdapters]:
    engine = create_async_engine(postgres_url(settings.postgres), pool_pre_ping=True)
    redis = redis_client(settings.redis)
    events = events_client(settings.redis, max_subscriptions=max_subscriptions)
    s3 = s3_client(
        S3Endpoint(
            url=settings.s3.url,
            region=settings.s3.region,
            access_key=settings.s3.access_key,
            secret_key=settings.s3.secret_key.get_secret_value(),
        )
    )
    try:
        yield HostedAdapters(
            engine=engine,
            redis=redis,
            events=events,
            store=PostgresTrackStore(engine=engine),
            feed=RedisProgressFeed(client=events),
            blobs=S3BlobStore(client=s3, bucket=settings.s3.bucket),
            jobs=RedisJobQueue(client=redis, stream=JobStream(consumer=consumer)),
        )
    finally:
        s3.close()
        await events.aclose()
        await redis.aclose()
        await engine.dispose()


async def prepare_storage(adapters: HostedAdapters) -> None:
    await upgrade_schema(adapters.engine)
    await adapters.blobs.ensure_bucket()
    await adapters.jobs.ensure_group()


def postgres_url(settings: PostgresSettings) -> URL:
    return URL.create(
        "postgresql+asyncpg",
        username=settings.user,
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


def redis_client(settings: RedisSettings) -> Redis:
    password = None if settings.password is None else settings.password.get_secret_value()
    return Redis(host=settings.host, port=settings.port, db=settings.database, password=password)


def events_client(settings: RedisSettings, *, max_subscriptions: int) -> Redis:
    password = None if settings.password is None else settings.password.get_secret_value()
    pool = BlockingConnectionPool(
        host=settings.host,
        port=settings.port,
        db=settings.database,
        password=password,
        max_connections=max_subscriptions + PUBLISH_CONNECTIONS,
        timeout=SUBSCRIBE_TIMEOUT_S,
    )
    return Redis.from_pool(pool)


def consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"
