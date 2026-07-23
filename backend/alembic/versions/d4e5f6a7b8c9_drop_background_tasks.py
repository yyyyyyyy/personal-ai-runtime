"""drop background_tasks; clear legacy plan_resumes kind=background (INV-W5)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-23 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS background_tasks;")
    op.execute("DELETE FROM plan_resumes WHERE kind = 'background';")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS background_tasks (
            id TEXT PRIMARY KEY,
            user_request TEXT NOT NULL,
            plan_json TEXT,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        );
        """
    )
