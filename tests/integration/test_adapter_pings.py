import boto3
import pytest
from botocore.config import Config
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from sqlalchemy.ext.asyncio import create_async_engine

from spectra.tracks.adapters.postgres import PostgresTrackStore
from spectra.tracks.adapters.redis_jobs import JobStream, RedisJobQueue
from spectra.tracks.adapters.s3 import S3BlobStore

CLOSED_PORT = 9

pytestmark = pytest.mark.anyio


async def test_an_unreachable_postgres_does_not_answer() -> None:
    engine = create_async_engine(f"postgresql+asyncpg://spectra:x@127.0.0.1:{CLOSED_PORT}/spectra")
    try:
        assert not await PostgresTrackStore(engine=engine).ping()
    finally:
        await engine.dispose()


async def test_an_unreachable_redis_does_not_answer() -> None:
    client = Redis(host="127.0.0.1", port=CLOSED_PORT, retry=Retry(NoBackoff(), retries=0))
    try:
        queue = RedisJobQueue(client=client, stream=JobStream(consumer="test"))
        assert not await queue.ping()
    finally:
        await client.aclose()


async def test_an_unreachable_s3_does_not_answer() -> None:
    client = boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{CLOSED_PORT}",
        region_name="us-east-1",
        aws_access_key_id="spectra",
        aws_secret_access_key="secret",
        config=Config(retries={"total_max_attempts": 1}),
    )
    try:
        assert not await S3BlobStore(client=client, bucket="spectra").ping()
    finally:
        client.close()
