import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from types_boto3_s3 import S3Client

MISSING_BUCKET_CODES: Final = frozenset({"404", "NoSuchBucket"})


@dataclass(frozen=True, slots=True, kw_only=True)
class S3Endpoint:
    url: str
    region: str
    access_key: str
    secret_key: str = field(repr=False)


def s3_client(endpoint: S3Endpoint) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=endpoint.url,
        region_name=endpoint.region,
        aws_access_key_id=endpoint.access_key,
        aws_secret_access_key=endpoint.secret_key,
        config=Config(
            s3={"addressing_style": "path"},
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )


class S3BlobStore:
    def __init__(self, *, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket)

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._client.put_object, Bucket=self._bucket, Key=key, Body=data)

    async def get(self, key: str) -> bytes | None:
        return await asyncio.to_thread(self._get, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    def _get(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey:
            return None
        return response["Body"].read()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") not in MISSING_BUCKET_CODES:
                raise
            self._create_bucket()

    def _create_bucket(self) -> None:
        try:
            self._client.create_bucket(Bucket=self._bucket)
        except self._client.exceptions.BucketAlreadyOwnedByYou:
            return
