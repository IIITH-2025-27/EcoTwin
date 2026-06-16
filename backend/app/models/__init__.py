# Import all models so that SQLAlchemy's mapper and Alembic can discover them.
from app.models.embedding import RegionEmbedding
from app.models.region import Region, RegionFeature
from app.models.report import Report, ReportStatus
from app.models.temporal_profile import TemporalProfile

__all__ = [
    "Region",
    "RegionFeature",
    "RegionEmbedding",
    "TemporalProfile",
    "Report",
    "ReportStatus",
]
