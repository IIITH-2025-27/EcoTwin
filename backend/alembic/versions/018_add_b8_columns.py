"""Add B8 (NIR) band statistics columns to lake_features.

Revision ID: 018
Revises: 017
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for stat in ["mean", "std", "min", "max", "median"]:
        op.add_column(
            "lake_features",
            sa.Column(f"b8_{stat}", sa.Double(), nullable=True),
        )


def downgrade() -> None:
    for stat in ["median", "max", "min", "std", "mean"]:
        op.drop_column("lake_features", f"b8_{stat}")
