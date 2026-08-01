# Import all models so that SQLAlchemy's mapper and Alembic can discover them.
from app.models.lake import Lake
from app.models.lake_feature import LakeFeature
from app.models.lake_image import LakeImage
from app.models.lake_tile import LakeTile
from app.models.lake_embedding import LakeEmbedding
from app.models.india_state import IndiaState
from app.models.embedding import RegionEmbedding
from app.models.region import Region
from app.models.report import Report, ReportStatus
from app.models.sub_region import SubRegion, SubRegionFeature

__all__ = [
    "Region",
    "Lake",
    "LakeFeature",
    "LakeImage",
    "LakeTile",
    "LakeEmbedding",
    "IndiaState",
    "RegionEmbedding",
    "Report",
    "ReportStatus",
    "SubRegion",
    "SubRegionFeature",
]
