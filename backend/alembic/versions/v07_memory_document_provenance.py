"""Add Memory↔Knowledge provenance columns to memories (Phase 1.5).

When a memory is derived from a knowledge-base document (e.g. the user
discussed an uploaded PDF and the extractor captured a fact from that
discussion), source_document_id / source_document_name record the link so
the frontend can show "derived from: <doc>" and jump to the document.

Purely additive — existing rows get NULL and behave identically.

Revision ID: v07_memory_document_provenance
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "v07_memory_document_provenance"
down_revision: Union[str, None] = "v06_drop_goals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.add_column(sa.Column("source_document_id", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_document_name", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.drop_column("source_document_name")
        batch_op.drop_column("source_document_id")
