"""Add state_name column to regions table

Revision ID: 003
Revises: 002
Create Date: 2026-06-16 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "regions",
        sa.Column("state_name", sa.String(100), nullable=True),
    )
    op.create_index("ix_regions_state_name", "regions", ["state_name"])


def downgrade() -> None:
    op.drop_index("ix_regions_state_name", table_name="regions")
    op.drop_column("regions", "state_name")
