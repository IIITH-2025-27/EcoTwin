"""Refactor regions to lake metadata

Revision ID: 004
Revises: 003
Create Date: 2026-07-11 00:00:00.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(connection, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(connection)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(connection, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(connection)
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS hydrolake_id VARCHAR(64)")
    op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS name VARCHAR(255)")
    op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS country VARCHAR(100)")
    # op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS area_sqkm DOUBLE PRECISION DEFAULT 25.0 NOT NULL")
    op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS bbox JSON")
    op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL")

    op.execute(
        """
        UPDATE regions
        SET
            hydrolake_id = COALESCE(hydrolake_id, region_id::text),
            name = COALESCE(name, 'Legacy Region'),
            country = COALESCE(country, 'India')
        """
    )

    op.execute("ALTER TABLE regions ALTER COLUMN hydrolake_id SET NOT NULL")
    op.execute("ALTER TABLE regions ALTER COLUMN name SET NOT NULL")
    op.execute("ALTER TABLE regions ALTER COLUMN country SET NOT NULL")
    op.execute("ALTER TABLE regions ALTER COLUMN updated_at SET DEFAULT NOW()")

    columns = {c["name"] for c in inspector.get_columns("regions")}

    if "area_km" in columns:
        op.execute("ALTER TABLE regions RENAME COLUMN area_km TO area_sqkm")
    elif "area_sqkm" not in columns:
        op.execute("""
            ALTER TABLE regions
            ADD COLUMN area_sqkm DOUBLE PRECISION DEFAULT 25.0 NOT NULL
        """)
    # if _has_column(connection, "regions", "area_km") and not _has_column(connection, "regions", "area_sqkm"):
    #     op.execute("ALTER TABLE regions RENAME COLUMN area_km TO area_sqkm")

    op.execute("ALTER TABLE regions DROP CONSTRAINT IF EXISTS regions_hydrolake_id_key")
    if not _has_index(connection, "regions", "ix_regions_hydrolake_id"):
        op.create_index("ix_regions_hydrolake_id", "regions", ["hydrolake_id"], unique=True)
    if not _has_index(connection, "regions", "ix_regions_country"):
        op.create_index("ix_regions_country", "regions", ["country"])

    op.execute("ALTER TABLE regions ALTER COLUMN geom TYPE geometry(MULTIPOLYGON, 4326) USING ST_Multi(geom)")

    if _has_column(connection, "regions", "state_name"):
        op.execute("ALTER TABLE regions DROP COLUMN IF EXISTS state_name")


def downgrade() -> None:
    connection = op.get_bind()

    op.execute("ALTER TABLE regions ADD COLUMN IF NOT EXISTS state_name VARCHAR(100)")
    op.execute("UPDATE regions SET state_name = NULL")
    op.execute("DROP INDEX IF EXISTS ix_regions_country")
    if _has_index(connection, "regions", "ix_regions_hydrolake_id"):
        op.drop_index("ix_regions_hydrolake_id", table_name="regions")

    if _has_column(connection, "regions", "area_sqkm") and not _has_column(connection, "regions", "area_km"):
        op.execute("ALTER TABLE regions RENAME COLUMN area_sqkm TO area_km")

    op.execute("ALTER TABLE regions ALTER COLUMN geom TYPE geometry(POLYGON, 4326) USING geom")

    for column_name in ["updated_at", "bbox", "area_sqkm", "country", "name", "hydrolake_id"]:
        if _has_column(connection, "regions", column_name):
            op.execute(f'ALTER TABLE regions DROP COLUMN IF EXISTS "{column_name}"')
