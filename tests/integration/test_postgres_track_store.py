import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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
from spectra.tracks.domain.track import Failed, FailureCode, TrackId, TrackStatus
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


async def backdate(engine: AsyncEngine, track_id: TrackId, seen_at: datetime = LONG_AGO) -> None:
    statement = (
        update_rows(TRACKS).where(TRACKS.c.track_id == track_id.value).values(last_seen_at=seen_at)
    )
    async with engine.begin() as connection:
        await connection.execute(statement)


async def stall(engine: AsyncEngine, track_id: TrackId, updated_at: datetime) -> None:
    statement = (
        update_rows(TRACKS).where(TRACKS.c.track_id == track_id.value).values(updated_at=updated_at)
    )
    async with engine.begin() as connection:
        await connection.execute(statement)


def downgrade_to_base(connection: Connection) -> None:
    command.downgrade(alembic_config(connection), "base")


async def test_a_running_postgres_answers(store: PostgresTrackStore) -> None:
    assert await store.ping()


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


async def test_finding_a_recently_seen_track_writes_nothing(
    engine: AsyncEngine, store: PostgresTrackStore
) -> None:
    await store.save(track("a"), READY)
    recently = datetime.now(UTC) - timedelta(minutes=10)
    await backdate(engine, track("a"), recently)
    assert await store.find(track("a")) == READY
    assert await last_seen_at(engine, track("a")) == recently


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


async def test_only_tracks_unseen_for_long_enough_expire(
    engine: AsyncEngine, store: PostgresTrackStore
) -> None:
    for name in ("old", "new"):
        await store.save(track(name), READY)
    await backdate(engine, track("old"), datetime.now(UTC) - timedelta(days=31))
    await backdate(engine, track("new"), datetime.now(UTC) - timedelta(days=29))
    month_s = timedelta(days=30).total_seconds()
    assert await store.expire_unseen(unseen_for_s=month_s, limit=10) == [track("old")]
    assert await store.find(track("old")) is None
    assert await store.find(track("new")) == READY


async def test_the_oldest_tracks_expire_first_up_to_the_limit(
    engine: AsyncEngine, store: PostgresTrackStore
) -> None:
    for days, name in enumerate(("a", "b", "c"), start=40):
        await store.save(track(name), READY)
        await backdate(engine, track(name), datetime.now(UTC) - timedelta(days=days))
    expired = await store.expire_unseen(unseen_for_s=timedelta(days=30).total_seconds(), limit=2)
    assert set(expired) == {track("c"), track("b")}
    assert await store.find(track("a")) == READY


async def test_only_analyses_without_news_for_long_enough_are_abandoned(
    engine: AsyncEngine, store: PostgresTrackStore
) -> None:
    abandoned = Failed(code=FailureCode.INTERNAL, message="abandoned")
    for name, status in (("stalled", ANALYSING), ("running", ANALYSING), ("ready", READY)):
        await store.save(track(name), status)
    long_ago = datetime.now(UTC) - timedelta(hours=3)
    await stall(engine, track("stalled"), long_ago)
    await stall(engine, track("ready"), long_ago)
    hours_2_s = timedelta(hours=2).total_seconds()
    assert await store.abandon_stalled(stalled_for_s=hours_2_s, status=abandoned) == [
        track("stalled")
    ]
    assert await store.find(track("stalled")) == abandoned
    assert await store.find(track("running")) == ANALYSING
    assert await store.find(track("ready")) == READY
    assert await store.analysing_count() == 1
