"""Add band median, spectral summary rename, and extra water stats columns.

Revision ID: 017
Revises: 016
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Band median columns ───────────────────────────────────────────────
    for band in [2, 3, 4, 5, 6, 7]:
        op.add_column(
            "lake_features",
            sa.Column(f"b{band}_median", sa.Double(), nullable=True),
        )

    # ── Spectral summary rename ───────────────────────────────────────────
    # brightness → visible_brightness
    # greenness  → nir_red_difference
    # wetness    → green_swir_difference
    op.alter_column(
        "lake_features", "brightness",
        new_column_name="visible_brightness",
    )
    op.alter_column(
        "lake_features", "greenness",
        new_column_name="nir_red_difference",
    )
    op.alter_column(
        "lake_features", "wetness",
        new_column_name="green_swir_difference",
    )

    # ── Extra water / pixel statistics ────────────────────────────────────
    op.add_column(
        "lake_features",
        sa.Column("valid_pixel_ratio", sa.Double(), nullable=True),
    )
    op.add_column(
        "lake_features",
        sa.Column("masked_pixel_percentage", sa.Double(), nullable=True),
    )
    op.add_column(
        "lake_features",
        sa.Column("water_to_land_ratio", sa.Double(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lake_features", "water_to_land_ratio")
    op.drop_column("lake_features", "masked_pixel_percentage")
    op.drop_column("lake_features", "valid_pixel_ratio")

    op.alter_column(
        "lake_features", "green_swir_difference",
        new_column_name="wetness",
    )
    op.alter_column(
        "lake_features", "nir_red_difference",
        new_column_name="greenness",
    )
    op.alter_column(
        "lake_features", "visible_brightness",
        new_column_name="brightness",
    )

    for band in [7, 6, 5, 4, 3, 2]:
        op.drop_column("lake_features", f"b{band}_median")
