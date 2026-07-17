"""add dedup_key to notifications

Revision ID: a09635d81cdf
Revises: 0001_consolidated
Create Date: 2026-07-17 15:22:32.474918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a09635d81cdf'
down_revision: Union[str, Sequence[str], None] = '0001_consolidated'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE notifications ADD COLUMN dedup_key TEXT;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_dedup_key ON notifications (dedup_key);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_notifications_dedup_key;")
    op.execute("ALTER TABLE notifications DROP COLUMN dedup_key;")
