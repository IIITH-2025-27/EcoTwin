"""Initial schema – regions, features, embeddings, temporal profiles, reports

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
import geoalchemy2

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── regions ───────────────────────────────────────────────────
    op.create_table(
        "regions",
        sa.Column("region_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("center_lat", sa.Float, nullable=False),
        sa.Column("center_lon", sa.Float, nullable=False),
        sa.Column("area_km", sa.Float, server_default="25.0"),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry("POLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_regions_coords", "regions", ["center_lat", "center_lon"])

    # ── region_features ───────────────────────────────────────────
    op.create_table(
        "region_features",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "region_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("regions.region_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        # NDVI
        sa.Column("ndvi_mean", sa.Float),
        sa.Column("ndvi_std", sa.Float),
        sa.Column("ndvi_median", sa.Float),
        sa.Column("ndvi_min", sa.Float),
        sa.Column("ndvi_max", sa.Float),
        # NDWI
        sa.Column("ndwi_mean", sa.Float),
        sa.Column("ndwi_std", sa.Float),
        sa.Column("ndwi_median", sa.Float),
        sa.Column("ndwi_min", sa.Float),
        sa.Column("ndwi_max", sa.Float),
        # NBR
        sa.Column("nbr_mean", sa.Float),
        sa.Column("nbr_std", sa.Float),
        sa.Column("nbr_median", sa.Float),
        sa.Column("nbr_min", sa.Float),
        sa.Column("nbr_max", sa.Float),
        sa.Column("dominant_ecosystem", sa.String(100)),
    )
    op.create_index("idx_rf_region_id", "region_features", ["region_id"])
    op.create_unique_constraint(
        "uq_region_feature_year", "region_features", ["region_id", "year"]
    )

    # ── region_embeddings ─────────────────────────────────────────
    op.create_table(
        "region_embeddings",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "region_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("regions.region_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        # Vector column created via raw DDL (pgvector type)
        sa.Column("embedding", sa.Text, nullable=False),  # placeholder; see below
    )
    # Replace placeholder column with the real VECTOR type
    op.execute("ALTER TABLE region_embeddings DROP COLUMN embedding")
    op.execute("ALTER TABLE region_embeddings ADD COLUMN embedding VECTOR(768) NOT NULL")

    op.create_index("idx_re_region_id", "region_embeddings", ["region_id"])
    op.create_unique_constraint(
        "uq_region_embedding_year", "region_embeddings", ["region_id", "year"]
    )
    # IVFFlat cosine index for sub-500 ms similarity search
    op.execute("""
        CREATE INDEX idx_region_embedding_cosine
        ON region_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # ── temporal_profiles ─────────────────────────────────────────
    op.create_table(
        "temporal_profiles",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "region_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("regions.region_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("ndvi", sa.Float),
        sa.Column("ndwi", sa.Float),
        sa.Column("nbr", sa.Float),
    )
    op.create_index("idx_tp_region_id", "temporal_profiles", ["region_id"])
    op.create_unique_constraint(
        "uq_temporal_profile_year", "temporal_profiles", ["region_id", "year"]
    )

    # ── reports ───────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("report_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "region_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("regions.region_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("pdf_url", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("celery_task_id", sa.String(255)),
        sa.Column("error_message", sa.Text),
    )
    op.create_index("idx_reports_region_id", "reports", ["region_id"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("temporal_profiles")
    op.drop_table("region_embeddings")
    op.drop_table("region_features")
    op.drop_table("regions")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS postgis")
