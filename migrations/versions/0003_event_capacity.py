"""add event participant capacity

Revision ID: 0003_event_capacity
Revises: 0002_event_photo
Create Date: 2026-09-17
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_event_capacity"
down_revision: str | None = "0002_event_photo"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("max_participants", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "max_participants")