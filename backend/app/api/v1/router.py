from fastapi import APIRouter

from app.api.v1.endpoints import forecast, health, regions, reports, similarity, temporal

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(regions.router, prefix="/regions")
api_router.include_router(similarity.router, prefix="/similarity")
api_router.include_router(temporal.router, prefix="/temporal")
api_router.include_router(forecast.router, prefix="/forecast")
api_router.include_router(reports.router, prefix="/report")
