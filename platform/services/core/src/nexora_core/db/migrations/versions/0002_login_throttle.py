"""P1 C5: login throttle (failed sign-in counting and lockout).

One row per key (``email:<address>`` or ``ip:<address>``): failures in the current one-minute
window and, once the limit is reached, ``locked_until``. Global, like sessions.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP, ADMIN = "nexora_app", "nexora_admin"


def upgrade() -> None:
    op.execute(
        "CREATE TABLE login_throttle ("
        " key text PRIMARY KEY,"
        " window_started_at timestamptz NOT NULL,"
        " failures integer NOT NULL CHECK (failures >= 0),"
        " locked_until timestamptz)"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON login_throttle TO {APP}, {ADMIN}")


def downgrade() -> None:
    op.execute("DROP TABLE login_throttle")
