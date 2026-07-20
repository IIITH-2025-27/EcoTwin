"""Add status and error_message to sub_regions and sub_region_features.

Enables pipeline observability, re-run of failed/pending cells, and
progress visualisation in the UI.

Status lifecycle:  pending → processing → completed | failed

Revision ID: 011
Revises: 010
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── sub_regions ──────────────────────────────────────────────────────
    op.add_column(
        "sub_regions",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "sub_regions",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_sub_regions_status", "sub_regions", ["status"])

    # ── sub_region_features ──────────────────────────────────────────────
    op.add_column(
        "sub_region_features",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "sub_region_features",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_sub_region_features_status", "sub_region_features", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_sub_region_features_status", table_name="sub_region_features")
    op.drop_column("sub_region_features", "error_message")
    op.drop_column("sub_region_features", "status")

    op.drop_index("ix_sub_regions_status", table_name="sub_regions")
    op.drop_column("sub_regions", "error_message")
    op.drop_column("sub_regions", "status")
