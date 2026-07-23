"""add plan_resumes app storage table

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-07-23 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_resumes (
            approval_id          TEXT PRIMARY KEY,
            kind                 TEXT NOT NULL,
            resume_from          INTEGER NOT NULL,
            previous_output_json TEXT,
            action_id            TEXT DEFAULT '',
            task_id              TEXT DEFAULT '',
            plan_json            TEXT DEFAULT '',
            created_at           TEXT NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plan_resumes;")
