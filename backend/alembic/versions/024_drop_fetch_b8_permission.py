"""Drop the fetch_b8 pipeline permission.

B8 (NIR) is now part of the single downloaded band stack and its statistics
are computed by the lake feature generator, so the separate "Fetch B8"
pipeline (and its Earth Engine zonal-stats pass) was removed. Also updates
the merge_embeddings description to the lake / shore re-blend it now does.

Revision ID: 024
Revises: 023
"""

from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM pipeline_permissions WHERE permission_key = 'fetch_b8'")
    op.execute(
        """
        UPDATE pipeline_permissions
        SET description = 'Re-blend stored lake and shore embeddings with a chosen lake weight.'
        WHERE permission_key = 'merge_embeddings'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO pipeline_permissions (permission_key, display_name, is_enabled, description)
        VALUES ('fetch_b8', 'Fetch B8', FALSE,
                'Fetch Sentinel-2 B8 (NIR) band and compute zonal statistics.')
        ON CONFLICT (permission_key) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE pipeline_permissions
        SET description = 'Aggregate lake tile embeddings into final lake embeddings.'
        WHERE permission_key = 'merge_embeddings'
        """
    )
