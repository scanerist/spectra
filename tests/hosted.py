import os
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import make_url, text

from spectra.bootstrap.hosted import open_hosted
from spectra.bootstrap.settings import HostedSettings, PostgresSettings, RedisSettings, S3Settings
from spectra.tracks.adapters.redis_jobs import JOBS_STREAM
from spectra.tracks.adapters.s3 import S3Endpoint, s3_client

if TYPE_CHECKING:
    from types_boto3_s3 import S3Client

SERVICE_VARIABLES = (
    "SPECTRA_TEST_DATABASE_URL",
    "SPECTRA_TEST_REDIS_URL",
    "SPECTRA_TEST_S3_URL",
    "SPECTRA_TEST_S3_ACCESS_KEY",
    "SPECTRA_TEST_S3_SECRET_KEY",
)

requires_services = pytest.mark.skipif(
    not all(os.environ.get(name) for name in SERVICE_VARIABLES),
    reason="set SPECTRA_TEST_DATABASE_URL, SPECTRA_TEST_REDIS_URL and SPECTRA_TEST_S3_*",
)


def hosted_test_settings(*, bucket: str) -> HostedSettings:
    database = make_url(os.environ["SPECTRA_TEST_DATABASE_URL"])
    redis = urlsplit(os.environ["SPECTRA_TEST_REDIS_URL"])
    return HostedSettings(
        postgres=PostgresSettings(
            host=database.host or "localhost",
            port=database.port or 5432,
            database=database.database or "postgres",
            user=database.username or "postgres",
            password=SecretStr(database.password or ""),
        ),
        redis=RedisSettings(
            host=redis.hostname or "localhost",
            port=redis.port or 6379,
            database=int(redis.path.lstrip("/") or "0"),
            password=None if redis.password is None else SecretStr(redis.password),
        ),
        s3=S3Settings(
            url=os.environ["SPECTRA_TEST_S3_URL"],
            region=os.environ.get("SPECTRA_TEST_S3_REGION", "us-east-1"),
            access_key=os.environ["SPECTRA_TEST_S3_ACCESS_KEY"],
            secret_key=SecretStr(os.environ["SPECTRA_TEST_S3_SECRET_KEY"]),
            bucket=bucket,
        ),
    )


async def wipe_services(settings: HostedSettings) -> None:
    async with open_hosted(settings, consumer="wipe") as adapters:
        async with adapters.engine.begin() as connection:
            await connection.execute(text("DROP TABLE IF EXISTS tracks, alembic_version"))
        await adapters.redis.delete(JOBS_STREAM)
    remove_bucket(settings)


def remove_bucket(settings: HostedSettings) -> None:
    client = s3_client(
        S3Endpoint(
            url=settings.s3.url,
            region=settings.s3.region,
            access_key=settings.s3.access_key,
            secret_key=settings.s3.secret_key.get_secret_value(),
        )
    )
    try:
        empty_and_delete(client, settings.s3.bucket)
    finally:
        client.close()


def empty_and_delete(client: S3Client, bucket: str) -> None:
    try:
        listing = client.list_objects_v2(Bucket=bucket)
    except client.exceptions.NoSuchBucket:
        return
    for item in listing.get("Contents", []):
        client.delete_object(Bucket=bucket, Key=item["Key"])
    client.delete_bucket(Bucket=bucket)
