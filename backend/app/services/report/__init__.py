"""Ecosystem Discovery Report generation (Jinja2 + WeasyPrint).

Public API:
    build_report_context(db, lake_id, method, top_k) -> ReportContext
    render_report_pdf(context) -> bytes
"""

from app.services.report.context import (
    AnalogInfo,
    LakeInfo,
    ReportContext,
    SimilarityInfo,
    TechnicalInfo,
    build_report_context,
)
from app.services.report.renderer import render_report_pdf

__all__ = [
    "AnalogInfo",
    "LakeInfo",
    "ReportContext",
    "SimilarityInfo",
    "TechnicalInfo",
    "build_report_context",
    "render_report_pdf",
]
