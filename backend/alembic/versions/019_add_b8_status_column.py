"""Add B8 fetch status column to lake_features.

Revision ID: 019
Revises: 018
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Plain text, not the lake_feature_status enum type — kept independent of
# the main pipeline's status column/state machine, and avoids depending on
# a Postgres enum type that may not exist in every environment.


def upgrade() -> None:
    op.add_column(
        "lake_features",
        sa.Column(
            "b8_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.create_check_constraint(
        "ck_lake_features_b8_status",
        "lake_features",
        "b8_status IN ('pending', 'processing', 'completed', 'failed')",
    )
    op.create_index(
        "ix_lake_features_b8_status", "lake_features", ["b8_status"]
    )


def downgrade() -> None:
    op.drop_index("ix_lake_features_b8_status", table_name="lake_features")
    op.drop_constraint("ck_lake_features_b8_status", "lake_features", type_="check")
    op.drop_column("lake_features", "b8_status")
