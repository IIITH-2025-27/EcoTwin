"""Create lakes table for HydroLAKES source records

Revision ID: 005
Revises: 004
Create Date: 2026-07-12 00:00:00.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lakes",
        sa.Column("lake_id", sa.BigInteger(), primary_key=True),
        sa.Column("lake_name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("area_sqkm", sa.Float(), nullable=True),
        sa.Column("elevation", sa.Float(), nullable=True),
        sa.Column("pour_lat", sa.Float(), nullable=True),
        sa.Column("pour_long", sa.Float(), nullable=True),
        sa.Column("lake_type", sa.String(length=100), nullable=True),
        sa.Column("depth_avg", sa.Float(), nullable=True),
        sa.Column("vol_total", sa.Float(), nullable=True),
        sa.Column("wshd_area", sa.Float(), nullable=True),
        sa.Column("geom", geoalchemy2.types.Geometry("MULTIPOLYGON", srid=4326), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lakes_country", "lakes", ["country"])
    op.create_index("ix_lakes_lake_name", "lakes", ["lake_name"])


def downgrade() -> None:
    op.drop_index("ix_lakes_lake_name", table_name="lakes")
    op.drop_index("ix_lakes_country", table_name="lakes")
    op.drop_table("lakes")