"""Initial migration: create all tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-08
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(), nullable=False, unique=True),
        sa.Column("last_sync_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sync_status", sa.String(), nullable=False, server_default="idle"),
        sa.Column("events_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_event_time", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("place_id", sa.String(), nullable=True),
        sa.Column("place_name", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("seats_pattern", sa.String(), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=True, server_default="published"),
        sa.Column("number_of_visitors", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "registrations",
        sa.Column("ticket_id", sa.Uuid(), primary_key=True),
        sa.Column("external_ticket_id", sa.String(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("seat", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], ondelete="CASCADE", name="fk_registrations_event_id"
        ),
    )
    op.create_index(op.f("ix_registrations_event_id"), "registrations", ["event_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_registrations_event_id"), table_name="registrations")
    op.drop_table("registrations")
    op.drop_table("events")
    op.drop_table("sync_metadata")
