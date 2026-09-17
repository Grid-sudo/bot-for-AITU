"""add user language

Revision ID: 0004_user_language
Revises: 0003_event_capacity
Create Date: 2026-09-17
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_language"
down_revision: str | None = "0003_event_capacity"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.String(length=2), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "language")