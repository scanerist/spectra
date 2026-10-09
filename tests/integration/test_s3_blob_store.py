import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from moto import mock_aws

from spectra.tracks.adapters.s3 import S3BlobStore, S3Endpoint, s3_client

MOCK_ENDPOINT = S3Endpoint(
    url="https://s3.us-east-1.amazonaws.com",
    region="us-east-1",
    access_key="mock-access",
    secret_key="mock-secret",
)


def configured_endpoint() -> S3Endpoint | None:
    url = os.environ.get("SPECTRA_TEST_S3_URL")
    if url is None:
        return None
    return S3Endpoint(
        url=url,
        region=os.environ.get("SPECTRA_TEST_S3_REGION", "us-east-1"),
        access_key=os.environ["SPECTRA_TEST_S3_ACCESS_KEY"],
        secret_key=os.environ["SPECTRA_TEST_S3_SECRET_KEY"],
    )


@contextmanager
def s3_endpoint() -> Iterator[S3Endpoint]:
    endpoint = configured_endpoint()
    if endpoint is not None:
        yield endpoint
        return
    with mock_aws():
        yield MOCK_ENDPOINT


@pytest.fixture
def bucket() -> str:
    return f"spectra-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def store(bucket: str) -> Iterator[S3BlobStore]:
    with s3_endpoint() as endpoint:
        client = s3_client(endpoint)
        yield S3BlobStore(client=client, bucket=bucket)
        try:
            listing = client.list_objects_v2(Bucket=bucket)
        except client.exceptions.NoSuchBucket:
            return
        for item in listing.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=item["Key"])
        client.delete_bucket(Bucket=bucket)


@pytest.mark.anyio
async def test_a_stored_blob_reads_back(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    await store.put("uploads/a", b"track bytes")
    assert await store.get("uploads/a") == b"track bytes"


@pytest.mark.anyio
async def test_a_missing_blob_reads_as_none(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    assert await store.get("timelines/missing") is None


@pytest.mark.anyio
async def test_putting_a_blob_again_replaces_it(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    await store.put("timelines/a", b"old")
    await store.put("timelines/a", b"new")
    assert await store.get("timelines/a") == b"new"


@pytest.mark.anyio
async def test_a_deleted_blob_is_gone(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    await store.put("uploads/a", b"track bytes")
    await store.delete("uploads/a")
    assert await store.get("uploads/a") is None


@pytest.mark.anyio
async def test_deleting_a_missing_blob_succeeds(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    await store.delete("uploads/missing")
    assert await store.get("uploads/missing") is None


@pytest.mark.anyio
async def test_ensuring_the_bucket_twice_keeps_its_blobs(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    await store.put("timelines/a", b"timeline")
    await store.ensure_bucket()
    assert await store.get("timelines/a") == b"timeline"


@pytest.mark.anyio
async def test_an_existing_bucket_answers(store: S3BlobStore) -> None:
    await store.ensure_bucket()
    assert await store.ping()


@pytest.mark.anyio
async def test_a_missing_bucket_does_not_answer(store: S3BlobStore) -> None:
    assert not await store.ping()


def test_the_secret_key_stays_out_of_the_repr() -> None:
    assert "mock-secret" not in repr(MOCK_ENDPOINT)
