"""add purpose to llm_calls

Revision ID: b1c2d3e4f5a6
Revises: a09635d81cdf
Create Date: 2026-07-17 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a09635d81cdf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_calls ADD COLUMN purpose TEXT DEFAULT 'chat';")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_calls_purpose ON llm_calls (purpose);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_llm_calls_purpose;")
    op.execute("ALTER TABLE llm_calls DROP COLUMN purpose;")
