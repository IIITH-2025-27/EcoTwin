"""Rebuild regions as lake-year aggregate embeddings.

Revision ID: 013
Revises: 012
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regions CASCADE")
    op.create_table(
        "regions",
        sa.Column("lake_id", sa.BigInteger(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("coverage_percent", sa.Float(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry("MULTIPOLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lake_id"], ["lakes.lake_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lake_id", "year", name="pk_regions"),
    )
    op.create_index("ix_regions_status", "regions", ["status"])
    op.create_index("ix_regions_geom", "regions", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    raise NotImplementedError("The regions table rebuild is intentionally irreversible")
