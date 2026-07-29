"""Drop unused embedding tables.

Revision ID: 015
Revises: 014
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS temporal_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS region_features CASCADE")
    op.execute("DROP TABLE IF EXISTS sub_region_features CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "Dropping tables is intentionally irreversible."
    )