"""add seats_pattern to events

Revision ID: c067af192578
Revises: 3d4320c8f7a9
Create Date: 2026-11-03 23:29:36.864532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c067af192578'
down_revision: Union[str, Sequence[str], None] = '3d4320c8f7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('events', sa.Column('seats_pattern', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('events', 'seats_pattern')
