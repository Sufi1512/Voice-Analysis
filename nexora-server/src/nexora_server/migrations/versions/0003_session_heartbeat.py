"""session heartbeat (lost-call sweeper), index on sessions.ended_at

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f("ix_sessions_ended_at"), ["ended_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_ended_at"))
        batch_op.drop_column("heartbeat_at")
