"""Add B1, B8A, B11, B12 band statistics and composite-quality columns to lake_features.

B1 (coastal aerosol), B8A (narrow NIR), B11 (SWIR1), B12 (SWIR2) complete
the single per-lake-year download stack; clear_obs_* summarise the
CLEAR_COUNT QA band (cloud-free scenes per pixel behind the median).

Revision ID: 021
Revises: 020
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BANDS = ["b1", "b8a", "b11", "b12"]
_STATS = ["mean", "std", "min", "max", "median"]
_CLEAR_OBS = ["clear_obs_mean", "clear_obs_min", "clear_obs_median"]


def upgrade() -> None:
    for band in _BANDS:
        for stat in _STATS:
            op.add_column(
                "lake_features",
                sa.Column(f"{band}_{stat}", sa.Double(), nullable=True),
            )
    for col in _CLEAR_OBS:
        op.add_column("lake_features", sa.Column(col, sa.Double(), nullable=True))


def downgrade() -> None:
    for col in reversed(_CLEAR_OBS):
        op.drop_column("lake_features", col)
    for band in reversed(_BANDS):
        for stat in reversed(_STATS):
            op.drop_column("lake_features", f"{band}_{stat}")
