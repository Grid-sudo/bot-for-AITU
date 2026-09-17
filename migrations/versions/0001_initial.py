"""initial schema: users, events, registrations

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# `postgresql.ENUM` (the dialect-specific class) is required here, not the
# cross-dialect `sa.Enum` — only `postgresql.ENUM` actually honours
# `create_type=False`. With that flag set, `create_table()`/`drop_table()`
# below will *not* try to auto-manage these types (auto-create fires
# regardless of `create_type` when unset, and auto-drop never fires once the
# type is bound to a table's metadata anyway) — the explicit `.create()` /
# `.drop()` calls in `upgrade()`/`downgrade()` become the single source of
# truth, so the type is created and dropped exactly once each.
user_status_enum = PGEnum("PENDING", "GOING", "NOT_GOING", name="user_status", create_type=False)
registration_status_enum = PGEnum(
    "PENDING", "GOING", "NOT_GOING", "CHECKED_IN", name="registration_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    user_status_enum.create(bind, checkfirst=True)
    registration_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            user_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            registration_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "event_id", name="uq_registration_user_event"),
    )
    op.create_index(
        "ix_registration_event_status", "registrations", ["event_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_registration_event_status", table_name="registrations")
    op.drop_table("registrations")
    op.drop_table("events")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    registration_status_enum.drop(bind, checkfirst=True)
    user_status_enum.drop(bind, checkfirst=True)
