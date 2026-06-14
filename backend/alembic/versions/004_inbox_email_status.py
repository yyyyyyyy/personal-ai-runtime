"""Add status column to inbox_emails for read/handled tracking.

Revision ID: 004
Revises: 003
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("inbox_emails") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        )


def downgrade() -> None:
    with op.batch_alter_table("inbox_emails") as batch_op:
        batch_op.drop_column("status")
