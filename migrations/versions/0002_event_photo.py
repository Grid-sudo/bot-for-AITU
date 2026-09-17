"""add event photo id

Revision ID: 0002_event_photo
Revises: 0001_initial
Create Date: 2026-09-17
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_event_photo"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("photo_file_id", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "photo_file_id")
