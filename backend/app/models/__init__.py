# Import all models so that SQLAlchemy's mapper and Alembic can discover them.
from app.models.lake import Lake
from app.models.india_state import IndiaState
from app.models.embedding import RegionEmbedding
from app.models.region import Region, RegionFeature
from app.models.report import Report, ReportStatus
from app.models.temporal_profile import TemporalProfile
from app.models.sub_region import SubRegion, SubRegionFeature

__all__ = [
    "Region",
    "RegionFeature",
    "Lake",
    "IndiaState",
    "RegionEmbedding",
    "TemporalProfile",
    "Report",
    "ReportStatus",
    "SubRegion",
    "SubRegionFeature",
]
