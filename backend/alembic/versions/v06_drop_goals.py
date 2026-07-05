"""Drop the legacy goals table (v1.0 Phase 4).

All goal rows are now projected into work_items (work_type='goal') via the
WorkItemCreated projector. All goal readers were migrated in Phase 3b to read
from work_items, and the fallback path was removed in this phase.

The goals table and its Goal* event types are retired. The work_items table
serves as the single unification point for tasks, actions, and goals.

Revision ID: v06_drop_goals
Create Date: 2026-07-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v06_drop_goals"
down_revision: Union[str, None] = "v05_work_items_goal_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("goals")


def downgrade() -> None:
    # Re-creating the goals table from scratch (best-effort).
    op.execute(
        """CREATE TABLE goals (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            progress REAL DEFAULT 0,
            importance REAL DEFAULT 0.5,
            urgency REAL DEFAULT 0.5,
            deadline TEXT,
            parent_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_activity_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
