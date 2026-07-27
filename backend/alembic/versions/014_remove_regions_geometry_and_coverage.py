"""Remove geometry and coverage from lake-year embedding output rows.

Revision ID: 014
Revises: 013
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_regions_geom", table_name="regions")
    op.drop_column("regions", "geom")
    op.drop_column("regions", "coverage_percent")


def downgrade() -> None:
    raise NotImplementedError("Removing regions geometry and coverage is irreversible")
