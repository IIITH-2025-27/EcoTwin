from fastapi import APIRouter

from app.api.v1.endpoints import (
    config,
    embeddings,
    forecast,
    health,
    imagery,
    lake_features,
    lakes,
    regions,
    reports,
    similarity,
    sync,
    temporal,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(config.router, prefix="/config")
api_router.include_router(regions.router, prefix="/regions")
api_router.include_router(lakes.router, prefix="/lakes")
api_router.include_router(similarity.router, prefix="/similarity")
api_router.include_router(temporal.router, prefix="/temporal")
api_router.include_router(forecast.router, prefix="/forecast")
api_router.include_router(reports.router, prefix="/report")
api_router.include_router(sync.router, prefix="/sync")
api_router.include_router(imagery.router, prefix="/imagery")
api_router.include_router(embeddings.router, prefix="/embeddings")
api_router.include_router(lake_features.router, prefix="/lake-features")
