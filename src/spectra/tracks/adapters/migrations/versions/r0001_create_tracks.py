from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision: str | None = None


def timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "tracks",
        sa.Column("track_id", sa.String(16), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("status", JSONB(), nullable=False),
        timestamp("created_at"),
        timestamp("updated_at"),
        timestamp("last_seen_at"),
        sa.CheckConstraint("state IN ('analysing', 'ready', 'failed')", name="ck_tracks_state"),
    )
    op.create_index("ix_tracks_last_seen_at", "tracks", ["last_seen_at"])
    op.create_index(
        "ix_tracks_analysing",
        "tracks",
        ["state"],
        postgresql_where=sa.text("state = 'analysing'"),
    )


def downgrade() -> None:
    op.drop_table("tracks")
