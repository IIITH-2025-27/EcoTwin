"""Store aggregated lake embeddings directly on regions rows.

Revision ID: 012
Revises: 011
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("regions", sa.Column("lake_id", sa.BigInteger(), nullable=True))
    op.add_column("regions", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("regions", sa.Column("embedding", Vector(768), nullable=True))
    op.add_column("regions", sa.Column("coverage_percent", sa.Float(), nullable=True))
    op.add_column("regions", sa.Column("num_cells", sa.Integer(), nullable=True))
    op.add_column("regions", sa.Column("status", sa.String(20), nullable=True, server_default="completed"))

    op.create_index("ix_regions_lake_id", "regions", ["lake_id"])
    op.create_index("ix_regions_year", "regions", ["year"])
    op.create_unique_constraint("uq_region_lake_year", "regions", ["lake_id", "year"])


def downgrade() -> None:
    op.drop_constraint("uq_region_lake_year", "regions", type_="unique")
    op.drop_index("ix_regions_year", table_name="regions")
    op.drop_index("ix_regions_lake_id", table_name="regions")
    op.drop_column("regions", "status")
    op.drop_column("regions", "num_cells")
    op.drop_column("regions", "coverage_percent")
    op.drop_column("regions", "embedding")
    op.drop_column("regions", "year")
    op.drop_column("regions", "lake_id")
