"""Store lake / shore embedding parts on regions.

``regions.embedding`` stays the single vector used by similarity and
forecasting; it is now ``normalize(w · lake + (1 − w) · shore)``. The two
parts are stored so the blend weight can be re-tuned later without
re-running Prithvi (POST /embeddings/merge).

embedding_version marks which method produced a row's vectors
(1 = legacy 1 km cells, 2 = lake + 500 m shore tokens at 30 m); existing
rows are version 1.

Revision ID: 022
Revises: 021
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("regions", sa.Column("lake_embedding", Vector(768), nullable=True))
    op.add_column("regions", sa.Column("shore_embedding", Vector(768), nullable=True))
    op.add_column("regions", sa.Column("lake_weight", sa.Float(), nullable=True))
    op.add_column("regions", sa.Column("lake_token_weight", sa.Float(), nullable=True))
    op.add_column("regions", sa.Column("shore_token_weight", sa.Float(), nullable=True))
    op.add_column("regions", sa.Column("tokens_encoded", sa.Integer(), nullable=True))
    op.add_column(
        "regions",
        sa.Column("embedding_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_regions_embedding_version", "regions", ["embedding_version"])


def downgrade() -> None:
    op.drop_index("ix_regions_embedding_version", table_name="regions")
    for col in [
        "embedding_version",
        "tokens_encoded",
        "shore_token_weight",
        "lake_token_weight",
        "lake_weight",
        "shore_embedding",
        "lake_embedding",
    ]:
        op.drop_column("regions", col)
