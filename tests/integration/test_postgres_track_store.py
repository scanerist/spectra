import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import Connection, select, text
from sqlalchemy import update as update_rows
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from spectra.tracks.adapters.postgres import (
    TRACKS,
    PostgresTrackStore,
    alembic_config,
    upgrade_schema,
)
from spectra.tracks.domain.track import TrackId, TrackStatus
from tests.statuses import ANALYSING, EVERY_STATUS, FAILED, READY, track

DATABASE_URL = os.environ.get("SPECTRA_TEST_DATABASE_URL")
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(DATABASE_URL is None, reason="SPECTRA_TEST_DATABASE_URL is not set"),
]


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS tracks, alembic_version"))
    await upgrade_schema(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PostgresTrackStore:
    return PostgresTrackStore(engine=engine)


async def last_seen_at(engine: AsyncEngine, track_id: TrackId) -> datetime:
    statement = select(TRACKS.c.last_seen_at).where(TRACKS.c.track_id == track_id.value)
    async with engine.connect() as connection:
        seen_at: datetime = (await connection.execute(statement)).scalar_one()
    return seen_at


async def backdate(engine: AsyncEngine, track_id: TrackId) -> None:
    statement = (
        update_rows(TRACKS).where(TRACKS.c.track_id == track_id.value).values(last_seen_at=LONG_AGO)
    )
    async with engine.begin() as connection:
        await connection.execute(statement)


def downgrade_to_base(connection: Connection) -> None:
    command.downgrade(alembic_config(connection), "base")


async def test_an_unknown_track_is_not_found(store: PostgresTrackStore) -> None:
    assert await store.find(track("a")) is None


@pytest.mark.parametrize("status", EVERY_STATUS)
async def test_a_saved_status_reads_back(store: PostgresTrackStore, status: TrackStatus) -> None:
    await store.save(track("a"), status)
    assert await store.find(track("a")) == status


async def test_saving_again_replaces_the_status(store: PostgresTrackStore) -> None:
    await store.save(track("a"), ANALYSING)
    await store.save(track("a"), READY)
    assert await store.find(track("a")) == READY


async def test_a_deleted_track_is_forgotten(store: PostgresTrackStore) -> None:
    await store.save(track("a"), FAILED)
    await store.delete(track("a"))
    assert await store.find(track("a")) is None


async def test_only_running_analyses_are_counted(store: PostgresTrackStore) -> None:
    await store.save(track("a"), ANALYSING)
    await store.save(track("b"), ANALYSING)
    await store.save(track("c"), READY)
    await store.save(track("d"), FAILED)
    assert await store.analysing_count() == 2


async def test_settled_tracks_are_kept_until_they_expire(store: PostgresTrackStore) -> None:
    await store.save(track("a"), READY)
    await store.save(track("b"), FAILED)
    assert await store.evict_settled(keep=track("b")) == []
    assert await store.find(track("a")) == READY


async def test_finding_a_track_marks_it_as_seen(
    engine: AsyncEngine, store: PostgresTrackStore
) -> None:
    await store.save(track("a"), READY)
    await backdate(engine, track("a"))
    await store.find(track("a"))
    assert await last_seen_at(engine, track("a")) > LONG_AGO


async def test_upgrading_twice_keeps_the_tracks(
    engine: AsyncEngine, store: PostgresTrackStore
) -> None:
    await store.save(track("a"), READY)
    await upgrade_schema(engine)
    assert await store.find(track("a")) == READY


async def test_the_schema_downgrades_to_nothing(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(downgrade_to_base)
        tables = await connection.execute(text("SELECT to_regclass('tracks')"))
        assert tables.scalar_one() is None
