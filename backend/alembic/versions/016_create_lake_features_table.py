
"""Create lake_features table for yearly ecological feature extraction.

One row represents the ecological state of one lake for one year,
computed from the clipped Sentinel-2 image corresponding to that lake.

Revision ID: 016
Revises: 015
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# status_enum = sa.Enum(
#     "pending",
#     "processing",
#     "completed",
#     "failed",
#     name="lake_feature_status",
#     create_type=False,
# )


def dcol(name: str):
    """Convenience helper for nullable DOUBLE columns."""
    return sa.Column(name, sa.Double(), nullable=True)


def upgrade() -> None:
    # status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "lake_features",

        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),

        # Identity
        sa.Column(
            "lake_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "lakes.lake_id",
                name="fk_lake_features_lake_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),

        # Processing
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "feature_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),

        sa.Column("pixel_count", sa.Integer()),
        sa.Column("valid_pixel_count", sa.Integer()),
        sa.Column("nodata_pixel_count", sa.Integer()),

        dcol("coverage_percent"),
        dcol("cloud_percent"),

        # Sentinel-2 Band Statistics (B2-B7)
        *[
            dcol(f"b{band}_{stat}")
            for band in [2, 3, 4, 5, 6, 7]
            for stat in ("mean", "std", "min", "max")
        ],

        # Vegetation Indices
        dcol("ndvi_mean"),
        dcol("ndvi_std"),
        dcol("ndvi_min"),
        dcol("ndvi_max"),
        dcol("ndvi_median"),
        dcol("ndvi_p25"),
        dcol("ndvi_p75"),

        dcol("evi_mean"),
        dcol("evi_std"),

        dcol("savi_mean"),
        dcol("savi_std"),

        dcol("msavi_mean"),
        dcol("gci_mean"),
        dcol("ndre_mean"),

        # Water Indices
        dcol("ndwi_mean"),
        dcol("ndwi_std"),
        dcol("ndwi_min"),
        dcol("ndwi_max"),
        dcol("ndwi_median"),
        dcol("ndwi_p25"),
        dcol("ndwi_p75"),

        dcol("mndwi_mean"),
        dcol("ndmi_mean"),
        dcol("awei_mean"),

        # Burn / Soil Indices
        dcol("nbr_mean"),
        dcol("nbr_std"),
        dcol("nbr2_mean"),
        dcol("bsi_mean"),
        dcol("ndbi_mean"),

        # Texture (GLCM)
        dcol("glcm_contrast"),
        dcol("glcm_correlation"),
        dcol("glcm_energy"),
        dcol("glcm_entropy"),
        dcol("glcm_homogeneity"),
        dcol("glcm_dissimilarity"),

        # Spectral Summary
        dcol("brightness"),
        dcol("greenness"),
        dcol("wetness"),
        dcol("spectral_variance"),
        dcol("spectral_entropy"),

        # Water / Land Statistics
        dcol("water_area_sqkm"),

        sa.Column("water_pixels", sa.Integer()),
        sa.Column("vegetation_pixels", sa.Integer()),
        sa.Column("soil_pixels", sa.Integer()),

        dcol("water_percentage"),
        dcol("vegetation_percentage"),
        dcol("soil_percentage"),

        # Metadata
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.UniqueConstraint(
            "lake_id",
            "year",
            name="uq_lake_features_lake_year",
        ),
    )

    op.create_index(
        "ix_lake_features_lake_id",
        "lake_features",
        ["lake_id"],
    )

    op.create_index(
        "ix_lake_features_year",
        "lake_features",
        ["year"],
    )

    op.create_index(
        "ix_lake_features_status",
        "lake_features",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_lake_features_status", table_name="lake_features")
    op.drop_index("ix_lake_features_year", table_name="lake_features")
    op.drop_index("ix_lake_features_lake_id", table_name="lake_features")
    op.drop_table("lake_features")
    # status_enum.drop(op.get_bind(), checkfirst=True)