"""Add India state boundaries and lake state attribution fields.

Revision ID: 006
Revises: 005
Create Date: 2026-07-12 00:00:00.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "india_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state_name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("geom", geoalchemy2.types.Geometry("MULTIPOLYGON", srid=4326), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_india_states_geom", "india_states", ["geom"], postgresql_using="gist")
    op.create_index("ix_india_states_state_name", "india_states", ["state_name"])

    op.alter_column("lakes", "lake_name", existing_type=sa.String(length=255), nullable=True)
    op.add_column("lakes", sa.Column("centroid", geoalchemy2.types.Geometry("POINT", srid=4326), nullable=True))
    op.add_column("lakes", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("lakes", sa.Column("display_name", sa.String(length=320), nullable=True))
    op.create_index("ix_lakes_centroid", "lakes", ["centroid"], postgresql_using="gist")
    op.create_index("ix_lakes_state", "lakes", ["state"])
    op.create_index("ix_lakes_display_name", "lakes", ["display_name"])

    # Keep the new field valid for rows that predate this migration. A later
    # state-boundary import fills in the state-specific display names.
    op.execute(
        """
        UPDATE lakes
        SET display_name = CASE
            WHEN lake_name IS NOT NULL AND btrim(lake_name) <> ''
                 AND btrim(lake_name) <> lake_id::text THEN lake_name
            ELSE format('Unnamed Lake #%s', lake_id)
        END
        """
    )
    op.alter_column("lakes", "display_name", existing_type=sa.String(length=320), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_lakes_display_name", table_name="lakes")
    op.drop_index("ix_lakes_state", table_name="lakes")
    op.drop_index("ix_lakes_centroid", table_name="lakes")
    op.drop_column("lakes", "display_name")
    op.drop_column("lakes", "state")
    op.drop_column("lakes", "centroid")
    op.alter_column("lakes", "lake_name", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_india_states_state_name", table_name="india_states")
    op.drop_index("ix_india_states_geom", table_name="india_states")
    op.drop_table("india_states")
