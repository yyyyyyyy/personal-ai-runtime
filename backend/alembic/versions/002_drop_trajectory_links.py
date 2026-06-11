"""Drop legacy trajectory_links table (experimental layer removed).

Revision ID: 002
Revises: 001
Create Date: 2026-06-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_trajectory_links_trajectory")
    op.drop_table("trajectory_links")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "trajectory_links",
        sa.Column("link_id", sa.Text(), primary_key=True),
        sa.Column("trajectory_id", sa.Text(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("claim_status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("rationale", sa.Text()),
        sa.Column("actor", sa.Text(), nullable=False, server_default="system"),
        sa.Column("linked_at_seq", sa.Integer()),
        sa.Column("linked_at", sa.Text()),
        sa.Column("updated_at", sa.Text()),
    )
    op.create_index(
        "idx_trajectory_links_trajectory",
        "trajectory_links",
        ["trajectory_id", "linked_at_seq"],
    )
