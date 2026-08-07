"""HTML → PDF rendering for the EcoTwin Ecosystem Discovery Report.

Uses Jinja2 templates (kept under ``app/services/report/templates/``) and
WeasyPrint. Templates are organised as one partial per report section so
new sections can be added without disturbing the existing structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.services.report.context import ReportContext, format_lat_lon, format_score, method_label

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── Presentation helpers exposed to the templates ───────────────────────────


def _fmt_area(value: Optional[float]) -> str:
    return f"{value:,.2f} km²" if value is not None else "—"


def _fmt_score(value: Optional[float]) -> str:
    return format_score(value)


def _fmt_ms(value: Optional[float]) -> str:
    return f"{value:,.0f} ms" if value else "—"


def _fmt_km(value: Optional[float]) -> str:
    return f"{value:,.1f} km" if value is not None else "—"


def _match_quality(score: Optional[float]) -> str:
    """Qualitative label for a similarity score (publication-style banding)."""
    if score is None:
        return "—"
    if score >= 0.90:
        return "Excellent"
    if score >= 0.80:
        return "Strong"
    if score >= 0.70:
        return "Moderate"
    return "Low"


_environment.globals.update(
    fmt_coords=format_lat_lon,
    fmt_area=_fmt_area,
    fmt_score=_fmt_score,
    fmt_ms=_fmt_ms,
    fmt_km=_fmt_km,
    method_label=method_label,
    match_quality=_match_quality,
)


def render_report_pdf(context: ReportContext) -> bytes:
    """Render the report context into a PDF document (returns raw bytes)."""
    template = _environment.get_template("report.html")
    html = template.render(context=context)
    return HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()
