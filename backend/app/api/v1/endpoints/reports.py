import asyncio

import structlog
from fastapi import APIRouter, Depends, Query, Response

from app.core.config import settings
from app.core.dependencies import DatabaseDep
from app.schemas.similarity import SimilarityMethod
from app.services.report import build_report_context, render_report_pdf

router = APIRouter(tags=["Reports"])
logger = structlog.get_logger(__name__)


@router.post("/{lake_id}")
async def generate_report(
    lake_id: int,
    db: DatabaseDep,
    top_k: int = Query(settings.DEFAULT_TOP_K, ge=1, le=20),
    method: SimilarityMethod = Query(
        SimilarityMethod.COSINE,
        description=(
            "Vector similarity method used for the analog search: "
            "cosine | euclidean | knn."
        ),
    ),
) -> Response:
    """
    Generate and return a complete ecosystem discovery report (PDF) for a lake.

    The report is rendered synchronously: context is assembled from the
    database, maps are generated, and the result is returned as a
    ``application/pdf`` response that the frontend opens in a new tab.
    """
    context = await build_report_context(db, lake_id=lake_id, method=method, top_k=top_k)

    pdf_bytes = await asyncio.to_thread(render_report_pdf, context)

    filename = f"ecotwin-report-{lake_id}.pdf"
    logger.info(
        "Report generated",
        lake_id=lake_id,
        method=method.value,
        top_k=top_k,
        size_bytes=len(pdf_bytes),
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
