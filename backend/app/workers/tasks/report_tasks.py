import io
import os
from uuid import UUID

import structlog
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.report_tasks.generate_report_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def generate_report_task(
    self,
    report_id: str,
    region_id: str,
    include_forecast: bool = True,
    include_analogs: bool = True,
    top_k_analogs: int = 5,
) -> dict:
    """
    Celery task: build a PDF ecosystem report and persist it.
    Updates the Report row via a synchronous DB session.
    """
    try:
        logger.info("Report generation started", report_id=report_id, region_id=region_id)

        pdf_bytes = _build_pdf(report_id, region_id, include_forecast, include_analogs)
        pdf_url = _persist_pdf(report_id, pdf_bytes)
        _update_report_db(report_id, status="completed", pdf_url=pdf_url)

        logger.info("Report generation completed", report_id=report_id, pdf_url=pdf_url)
        return {"status": "completed", "pdf_url": pdf_url}

    except Exception as exc:
        logger.error("Report generation failed", report_id=report_id, error=str(exc))
        _update_report_db(report_id, status="failed", error_message=str(exc))
        raise self.retry(exc=exc)


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_pdf(
    report_id: str,
    region_id: str,
    include_forecast: bool,
    include_analogs: bool,
) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title="EcoTwin Ecosystem Report",
    )

    story = [
        Paragraph("EcoTwin Ecosystem Report", styles["Title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"Region ID: {region_id}", styles["Normal"]),
        Paragraph(f"Report ID: {report_id}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
        Paragraph("Ecosystem Summary", styles["Heading2"]),
        Paragraph(
            "This report summarises the ecosystem analysis, analog discovery, "
            "and future trajectory forecast for the selected 5 km × 5 km grid cell.",
            styles["BodyText"],
        ),
        Spacer(1, 0.3 * cm),
    ]

    if include_analogs:
        story += [
            Paragraph("Top Analog Ecosystems", styles["Heading2"]),
            Paragraph(
                "The following regions were identified as the closest ecosystem "
                "analogs based on cosine similarity over Prithvi embeddings.",
                styles["BodyText"],
            ),
            Spacer(1, 0.3 * cm),
        ]

    if include_forecast:
        story += [
            Paragraph("Analog-Based Forecast", styles["Heading2"]),
            Paragraph(
                "Forecast derived from the historical trajectory of the best-matching "
                "analog ecosystem. Values represent predicted NDVI / NDWI / NBR means.",
                styles["BodyText"],
            ),
        ]

    doc.build(story)
    return buffer.getvalue()


def _persist_pdf(report_id: str, pdf_bytes: bytes) -> str:
    """Save PDF to local storage (swap with S3 upload in production)."""
    from app.core.config import settings  # noqa: PLC0415

    os.makedirs(settings.REPORTS_STORAGE_PATH, exist_ok=True)
    path = os.path.join(settings.REPORTS_STORAGE_PATH, f"{report_id}.pdf")

    with open(path, "wb") as fh:
        fh.write(pdf_bytes)

    return f"/reports/{report_id}.pdf"


def _update_report_db(
    report_id: str,
    *,
    status: str,
    pdf_url: str | None = None,
    error_message: str | None = None,
) -> None:
    """Synchronous DB update executed inside the Celery worker process."""
    from sqlalchemy import create_engine, update  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415
    from app.models.report import Report  # noqa: PLC0415

    engine = create_engine(settings.SYNC_DATABASE_URL)
    with engine.begin() as conn:
        stmt = (
            update(Report)
            .where(Report.report_id == report_id)
            .values(status=status, pdf_url=pdf_url, error_message=error_message)
        )
        conn.execute(stmt)
    engine.dispose()
