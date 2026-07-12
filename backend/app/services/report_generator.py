import io
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def build_pdf(
    report_id: str,
    region_id: str,
    include_forecast: bool,
    include_analogs: bool,
) -> bytes:
    """Build the PDF report content."""
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
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


def persist_pdf(report_id: str, pdf_bytes: bytes) -> str:
    """Save a report PDF to local storage."""
    from app.core.config import settings

    os.makedirs(settings.REPORTS_STORAGE_PATH, exist_ok=True)
    path = os.path.join(settings.REPORTS_STORAGE_PATH, f"{report_id}.pdf")
    with open(path, "wb") as file_handle:
        file_handle.write(pdf_bytes)
    return f"/reports/{report_id}.pdf"
