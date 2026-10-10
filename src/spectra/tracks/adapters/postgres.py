from datetime import timedelta
from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    Connection,
    DateTime,
    Interval,
    MetaData,
    String,
    Table,
    func,
    literal,
    select,
)
from sqlalchemy import delete as delete_rows
from sqlalchemy import update as update_rows
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from spectra.tracks.adapters.status_records import (
    StatusState,
    state_of,
    status_document,
    status_from_document,
)
from spectra.tracks.domain.track import TrackId, TrackStatus

SEEN_RESOLUTION: Final = timedelta(hours=1)

MIGRATIONS: Final = "spectra.tracks.adapters:migrations"
METADATA: Final = MetaData()
TRACKS: Final = Table(
    "tracks",
    METADATA,
    Column("track_id", String(16), primary_key=True),
    Column("state", String(16), nullable=False),
    Column("status", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class PostgresTrackStore:
    def __init__(self, *, engine: AsyncEngine) -> None:
        self._engine = engine

    async def ping(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(select(1))
        except SQLAlchemyError, OSError:
            return False
        return True

    async def find(self, track_id: TrackId) -> TrackStatus | None:
        stale_before = func.now() - literal(SEEN_RESOLUTION, Interval())
        lookup = select(TRACKS.c.status, TRACKS.c.last_seen_at < stale_before).where(
            TRACKS.c.track_id == track_id.value
        )
        touch = (
            update_rows(TRACKS)
            .where(TRACKS.c.track_id == track_id.value)
            .values(last_seen_at=func.now())
        )
        async with self._engine.begin() as connection:
            row = (await connection.execute(lookup)).one_or_none()
            if row is None:
                return None
            document, stale = row
            if stale:
                await connection.execute(touch)
        return status_from_document(document)

    async def save(self, track_id: TrackId, status: TrackStatus) -> None:
        values = {"state": state_of(status).value, "status": status_document(status)}
        statement = (
            insert(TRACKS)
            .values(track_id=track_id.value, **values)
            .on_conflict_do_update(
                index_elements=[TRACKS.c.track_id],
                set_={**values, "updated_at": func.now(), "last_seen_at": func.now()},
            )
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def delete(self, track_id: TrackId) -> None:
        statement = delete_rows(TRACKS).where(TRACKS.c.track_id == track_id.value)
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def analysing_count(self) -> int:
        statement = (
            select(func.count())
            .select_from(TRACKS)
            .where(TRACKS.c.state == StatusState.ANALYSING.value)
        )
        async with self._engine.connect() as connection:
            return (await connection.execute(statement)).scalar_one()

    async def evict_settled(self, *, keep: TrackId) -> list[TrackId]:  # noqa: ARG002
        return []

    async def expire_unseen(self, *, unseen_for_s: float, limit: int) -> list[TrackId]:
        cutoff = func.now() - literal(timedelta(seconds=unseen_for_s), Interval())
        oldest = (
            select(TRACKS.c.track_id)
            .where(TRACKS.c.last_seen_at < cutoff)
            .order_by(TRACKS.c.last_seen_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        statement = (
            delete_rows(TRACKS)
            .where(TRACKS.c.track_id.in_(oldest.scalar_subquery()))
            .where(TRACKS.c.last_seen_at < cutoff)
            .returning(TRACKS.c.track_id)
        )
        async with self._engine.begin() as connection:
            rows = (await connection.execute(statement)).scalars().all()
        return [TrackId(track_id) for track_id in rows]


def alembic_config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    config.attributes["connection"] = connection
    return config


def upgrade_to_head(connection: Connection) -> None:
    command.upgrade(alembic_config(connection), "head")


async def upgrade_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(upgrade_to_head)
