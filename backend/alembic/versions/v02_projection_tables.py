"""Add timer_events, policy_events, grant_events projection tables and messages.sources column.

These tables were previously created at runtime via schema_init.apply_projection_ddl()
because they were added after the initial Alembic baseline was frozen. This migration
brings them into the Alembic lineage so schema_init's runtime DDL path becomes a no-op
for production databases.

Revision ID: v02_projection_tables
Create Date: 2026-06-30
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v02_projection_tables"
down_revision: Union[str, None] = "initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── timer_events ──────────────────────────────────────────────────────

    op.create_table(
        "timer_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("handler_name", sa.Text(), nullable=False),
        sa.Column("schedule_type", sa.Text(), nullable=False, server_default="cron"),
        sa.Column("cron_expr", sa.Text(), nullable=False, server_default=""),
        sa.Column("delay_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fire_at", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("fired_at", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("idx_timer_events_status", "timer_events", ["status", "fire_at"])

    # ── policy_events ─────────────────────────────────────────────────────

    op.create_table(
        "policy_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("capability", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False, server_default="low"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_policy_events_capability", "policy_events", ["capability"])
    op.create_index("idx_policy_events_status", "policy_events", ["status"])

    # ── grant_events ──────────────────────────────────────────────────────

    op.create_table(
        "grant_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("principal_id", sa.Text(), nullable=False),
        sa.Column("capability", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("idx_grant_events_principal", "grant_events", ["principal_id"])
    op.create_index("idx_grant_events_capability", "grant_events", ["principal_id", "capability"])

    # ── messages.sources column ───────────────────────────────────────────

    op.execute("ALTER TABLE messages ADD COLUMN sources TEXT")


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN easily, so we recreate messages table
    # without sources column — but for a non-prod migration revert we accept the
    # limitation and just drop the new tables.
    op.drop_index("idx_grant_events_capability", table_name="grant_events")
    op.drop_index("idx_grant_events_principal", table_name="grant_events")
    op.drop_table("grant_events")
    op.drop_index("idx_policy_events_status", table_name="policy_events")
    op.drop_index("idx_policy_events_capability", table_name="policy_events")
    op.drop_table("policy_events")
    op.drop_index("idx_timer_events_status", table_name="timer_events")
    op.drop_table("timer_events")
    # messages.sources column removal is not supported in-place by SQLite 3.x.
    # Downgrade is non-production; leave the column for simplicity.
