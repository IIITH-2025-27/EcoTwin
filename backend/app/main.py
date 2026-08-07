from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import EcoTwinBaseException
from app.core.logging import configure_logging
from app.db.session import engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: RUF029
    configure_logging()
    logger.info(
        "EcoTwin API starting",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    yield
    logger.info("EcoTwin API shutting down")
    await engine.dispose()


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Geospatial Ecosystem Discovery, Similarity Search, "
            "and Analog Forecasting Platform"
        ),
        # Disable interactive docs in production
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1_000)

    # ── Exception handlers ────────────────────────────────────────
    @app.exception_handler(EcoTwinBaseException)
    async def domain_exception_handler(
        request: Request, exc: EcoTwinBaseException
    ) -> JSONResponse:
        logger.warning(
            "Domain exception",
            error=exc.message,
            code=exc.code,
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
        )

    # ── Routers ───────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_application()
