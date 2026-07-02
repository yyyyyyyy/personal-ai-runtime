"""Add related_id, related_type, notification_type columns to notifications.

Fixes FACT-37: _smart_notification_check emitted these fields in the event
payload, but the projector discarded them and the schema had no columns for
them, so the dedup query (related_id=? AND notification_type=?) silently
failed — stagnant-goal notifications were duplicated on every loop tick.

Revision ID: v03_notification_dedup
Create Date: 2026-07-01
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v03_notification_dedup"
down_revision: Union[str, None] = "v02_projection_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("related_id", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("related_type", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("notification_type", sa.Text(), nullable=True))
    # Support the dedup query: one stagnant notification per goal.
    op.create_index(
        "ix_notifications_related_type",
        "notifications",
        ["related_id", "notification_type"],
        unique=False,
    )


def downgrade() -> None:
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_related_type")
        batch_op.drop_column("notification_type")
        batch_op.drop_column("related_type")
        batch_op.drop_column("related_id")
