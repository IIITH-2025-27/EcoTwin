"""Add region_id UUID primary key to regions.

Revision ID: 015
Revises: 014
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "regions",
        sa.Column("region_id", sa.UUID(), nullable=True),
    )
    op.execute("UPDATE regions SET region_id = gen_random_uuid() WHERE region_id IS NULL")
    op.alter_column("regions", "region_id", nullable=False)

    op.drop_constraint("pk_regions", "regions", type_="primary")
    op.create_primary_key("pk_regions", "regions", ["region_id"])
    op.create_unique_constraint(
        "uq_regions_lake_year",
        "regions",
        ["lake_id", "year"],
    )
    op.create_index("ix_regions_lake_id", "regions", ["lake_id"])
    op.create_index("ix_regions_year", "regions", ["year"])


def downgrade() -> None:
    op.drop_index("ix_regions_year", table_name="regions")
    op.drop_index("ix_regions_lake_id", table_name="regions")
    op.drop_constraint("uq_regions_lake_year", "regions", type_="unique")
    op.drop_constraint("pk_regions", "regions", type_="primary")
    op.create_primary_key("pk_regions", "regions", ["lake_id", "year"])
    op.drop_column("regions", "region_id")
