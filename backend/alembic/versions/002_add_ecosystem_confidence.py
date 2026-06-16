"""Add ecosystem_confidence column to region_features

Revision ID: 002
Revises: 001
Create Date: 2026-06-16 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ecosystem_confidence; NULL until Phase 3 of the ML pipeline runs.
    op.add_column(
        "region_features",
        sa.Column("ecosystem_confidence", sa.Float, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("region_features", "ecosystem_confidence")
