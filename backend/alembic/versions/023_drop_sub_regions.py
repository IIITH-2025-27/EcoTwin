"""Drop sub_regions (legacy 1 km cell embeddings).

Embeddings are now built per lake-year from lake + shore tokens and stored
directly on ``regions`` (migration 022); nothing reads or writes the 1 km
cell table any more. ``sub_region_features`` is dropped too if it exists.

Downgrade recreates the empty table structure only — the dropped rows are
not restored.

Revision ID: 023
Revises: 022
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sub_region_features")
    op.execute("DROP TABLE IF EXISTS sub_regions")


def downgrade() -> None:
    op.create_table(
        "sub_regions",
        sa.Column(
            "sub_region_id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("lake_id", sa.BigInteger(), nullable=False),
        sa.Column("cell_number", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("coverage_percent", sa.Float(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column("geom", geoalchemy2.Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lake_id"], ["lakes.lake_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sub_region_id", name="sub_regions_pkey"),
        sa.UniqueConstraint(
            "lake_id", "cell_number", "year", name="uq_sub_region_lake_cell_year"
        ),
    )
    op.create_index("ix_sub_regions_lake_id", "sub_regions", ["lake_id"])
    op.create_index("ix_sub_regions_status", "sub_regions", ["status"])
    op.create_index(
        "ix_sub_regions_embedding", "sub_regions", ["embedding"],
        postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
    )
