"""Create pipeline_permissions table.

Revision ID: 020
Revises: 019
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_permissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "permission_key",
            sa.String(length=100),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "display_name",
            sa.String(length=150),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Seed default permission rows — all disabled.
    op.execute(
        """
        INSERT INTO pipeline_permissions (permission_key, display_name, is_enabled, description)
        VALUES
            ('allow_data_pipeline_run', 'Allow Data Pipeline Run',       FALSE, 'Master switch — controls whether ANY data-pipeline operation is available.'),
            ('sync_lakes',              'Sync Lakes',                    FALSE, 'Import HydroLAKES records into the lakes table.'),
            ('fetch_images',            'Fetch Images',                  FALSE, 'Download Sentinel-2 GeoTIFF composites for active lakes.'),
            ('merge_image_tiles',       'Merge Image Tiles',             FALSE, 'Merge downloaded tiles into single GeoTIFFs per lake.'),
            ('generate_embeddings',     'Generate Embeddings',           FALSE, 'Generate embeddings from locally merged lake images.'),
            ('merge_embeddings',        'Merge Embeddings',              FALSE, 'Aggregate lake tile embeddings into final lake embeddings.'),
            ('generate_features',       'Generate Lake Features',        FALSE, 'Extract ecological features from merged Sentinel-2 images.'),
            ('fetch_b8',                'Fetch B8',                      FALSE, 'Fetch Sentinel-2 B8 (NIR) band and compute zonal statistics.')
        """
    )


def downgrade() -> None:
    op.drop_table("pipeline_permissions")
