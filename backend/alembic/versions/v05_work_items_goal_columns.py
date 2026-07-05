"""Add goal-unification columns to work_items (v1.0 Phase 1, additive).

Pre-v1.0: goals table held Eisenhower-matrix fields (progress/importance/
urgency/deadline) plus parent_id (self-FK tree) and last_activity_at.
v1.0 merges Goal into Work as work_type='goal'. This migration adds the
goal-specific columns to work_items so subsequent phases can dual-write
and migrate readers without breaking the rebuild invariant.

This migration is purely additive — existing work_items rows get sane
defaults and continue to behave identically. No reader is changed yet.

Revision ID: v05_work_items_goal_columns
Create Date: 2026-07-05
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v05_work_items_goal_columns"
down_revision: Union[str, None] = "v04_memory_index_repairs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite's batch_alter_table lets us add columns with defaults to an
    # existing table. Each ADD COLUMN must include a server_default so the
    # existing rows get a value (NOT NULL without default would fail).
    with op.batch_alter_table("work_items") as batch_op:
        batch_op.add_column(
            sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        )
        batch_op.add_column(
            sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        )
        batch_op.add_column(
            sa.Column("urgency", sa.Float(), nullable=False, server_default="0.5"),
        )
        batch_op.add_column(sa.Column("deadline", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_activity_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_items") as batch_op:
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("deadline")
        batch_op.drop_column("urgency")
        batch_op.drop_column("importance")
        batch_op.drop_column("progress")
