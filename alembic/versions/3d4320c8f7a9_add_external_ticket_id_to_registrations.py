"""add external_ticket_id to registrations

Revision ID: 3d4320c8f7a9
Revises:
Create Date: 2026-11-03 18:04:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "3d4320c8f7a9"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ⚠️ ВАЖНО: проверь имя таблицы! Если в models.py у тебя __tablename__ = "tickets",
    # замени "registrations" на "tickets" ниже.
    op.add_column("registrations", sa.Column("external_ticket_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("registrations", "external_ticket_id")
