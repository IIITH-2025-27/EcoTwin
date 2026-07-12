"""Create 1 km lake grid processing tables.

Revision ID: 008
Revises: 007
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sub_regions",
        sa.Column("sub_region_id", sa.UUID(), primary_key=True),
        sa.Column("lake_id", sa.BigInteger(), sa.ForeignKey("lakes.lake_id", ondelete="CASCADE"), nullable=False),
        sa.Column("cell_number", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("coverage_percent", sa.Float(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column("geom", geoalchemy2.types.Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column("embedding", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("lake_id", "cell_number", "year", name="uq_sub_region_lake_cell_year"),
    )
    op.execute("ALTER TABLE sub_regions DROP COLUMN embedding")
    op.execute("ALTER TABLE sub_regions ADD COLUMN embedding VECTOR(768)")
    op.create_index("ix_sub_regions_lake_id", "sub_regions", ["lake_id"])
    op.create_index("ix_sub_regions_geom", "sub_regions", ["geom"], postgresql_using="gist")
    op.create_index("ix_sub_regions_embedding", "sub_regions", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})

    op.create_table(
        "sub_region_features",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("sub_region_id", sa.UUID(), sa.ForeignKey("sub_regions.sub_region_id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        *[sa.Column(name, sa.Float()) for name in (
            "ndvi_mean", "ndvi_std", "ndvi_median", "ndvi_min", "ndvi_max",
            "ndwi_mean", "ndwi_std", "ndwi_median", "ndwi_min", "ndwi_max",
            "nbr_mean", "nbr_std", "nbr_median", "nbr_min", "nbr_max",
        )],
        sa.Column("dominant_ecosystem", sa.String(length=100)),
        sa.Column("ecosystem_confidence", sa.Float(), nullable=True),
        sa.UniqueConstraint("sub_region_id", "year", name="uq_sub_region_feature_year"),
    )
    op.create_index("ix_sub_region_features_sub_region_id", "sub_region_features", ["sub_region_id"])


def downgrade() -> None:
    op.drop_index("ix_sub_region_features_sub_region_id", table_name="sub_region_features")
    op.drop_table("sub_region_features")
    op.drop_index("ix_sub_regions_embedding", table_name="sub_regions")
    op.drop_index("ix_sub_regions_geom", table_name="sub_regions")
    op.drop_index("ix_sub_regions_lake_id", table_name="sub_regions")
    op.drop_table("sub_regions")
