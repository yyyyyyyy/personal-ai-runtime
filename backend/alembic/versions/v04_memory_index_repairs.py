"""Add memory_index_repairs table for durable ChromaDB index reconciliation.

Pre-fix: failed ChromaDB index syncs were held in an in-process deque capped
at 1000 entries (kernel.py:_pending_memory_index_repairs). When the deque
overflowed or the process restarted, outstanding repairs were lost silently
and the affected memories became unrecallable until the next CI run of
verify_vector_consistency.py.

This migration introduces a durable APP_STORAGE table that the RuntimeLoop
maintenance worker drains every ~10s, with retry_count tracking and a
'failed_permanent' status for entries that exceed the retry budget.

Revision ID: v04_memory_index_repairs
Create Date: 2026-07-04
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v04_memory_index_repairs"
down_revision: Union[str, None] = "v03_notification_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_index_repairs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default="pending",
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_retry_at", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_memory_repairs_status",
        "memory_index_repairs",
        ["status", "retry_count"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_memory_repairs_status", table_name="memory_index_repairs")
    op.drop_table("memory_index_repairs")
