"""Create lake_tiles table for tile-based Sentinel-2 GeoTIFF tracking.

Each buffered lake is divided into a 10 km × 10 km grid.  One row per
tile per lake per year tracks download status and the on-disk file path.

Revision ID: 010
Revises: 009
"""

from typing import Sequence, Union

import geoalchemy2  # noqa: F401 — required for Geometry column reflection
import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lake_tiles",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("lake_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("tile_index", sa.String(20), nullable=False),
        sa.Column(
            "tile_geometry",
            geoalchemy2.Geometry("POLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column("bbox", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "lake_id", "year", "tile_index", name="uq_lake_tiles_lake_year_tile"
        ),
    )


def downgrade() -> None:
    op.drop_table("lake_tiles")
