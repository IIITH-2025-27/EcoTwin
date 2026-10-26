"""Figure 3 — EcoTwin system components and their communication (as implemented).

Coordinates are inches on a 6.27 in wide portrait text block; the axes fill
the figure, so 1 data unit = 1 inch.
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = sys.argv[1]
W, H = 6.27, 7.75

INK = "#1f2933"
MUTED = "#52606d"
C = {
    "front": ("#e8f1fb", "#2b6cb0"),
    "back": ("#f4f6f9", "#486581"),
    "online": ("#ffffff", "#2b6cb0"),
    "pipe": ("#ffffff", "#c05621"),
    "gee": ("#e9f7ef", "#2f855a"),
    "prithvi": ("#f3ecfa", "#6b46c1"),
    "files": ("#fbf3e6", "#a5672a"),
    "db": ("#e6f6f5", "#2c7a7b"),
}
LINK = {"rest": "#2b6cb0", "sql": "#2c7a7b", "gee": "#2f855a", "prithvi": "#6b46c1", "file": "#a5672a"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 6})
fig = plt.figure(figsize=(W, H), dpi=300)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")


def box(x, y, w, h, kind, title=None, lines=(), title_size=6.6, body_size=5.5, ls="-", lw=0.9,
        align="left", pad=0.07, rounding=0.05, title_color=None, z=1):
    fc, ec = C[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rounding}",
                                fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))
    tx = x + pad if align == "left" else x + w / 2
    ha = "left" if align == "left" else "center"
    ty = y + h - pad
    if title:
        ax.text(tx, ty, title, fontsize=title_size, fontweight="bold", color=title_color or ec,
                ha=ha, va="top", zorder=z + 1)
        ty -= title_size / 72 * 1.45
    if lines:
        ax.text(tx, ty, "\n".join(lines), fontsize=body_size, color=INK, ha=ha, va="top",
                linespacing=1.35, zorder=z + 1)


def arrow(p0, p1, color, both=False, ls="-", lw=1.0, z=5):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>" if both else "-|>", mutation_scale=7,
                                 color=color, lw=lw, ls=ls, zorder=z, shrinkA=0, shrinkB=0))


def line(xs, ys, color, ls="-", lw=1.0, z=5):
    ax.plot(xs, ys, color=color, ls=ls, lw=lw, zorder=z, solid_capstyle="butt")


def label(x, y, text, color, size=5.2, ha="center", va="center", **kw):
    ax.text(x, y, text, fontsize=size, color=color, ha=ha, va=va, zorder=8, linespacing=1.3,
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.95), **kw)


# ── Frontend (browser) ───────────────────────────────────────────────────────
FX0, FY0, FW, FH = 0.06, 6.55, 4.30, 1.12
box(FX0, FY0, FW, FH, "front", "Frontend (web browser)",
    ["React 18 · TypeScript · Vite · Leaflet · React Query · Zustand · Recharts · Axios"])
chips = ["Map &\nlake search", "Analog\npanel", "Forecast\npanel", "Index\nhistory", "PDF\nreport",
         "Pipeline\ndialogs (6)"]
cw, gap = 0.655, 0.04
cx0 = FX0 + (FW - (len(chips) * cw + (len(chips) - 1) * gap)) / 2
for k, t in enumerate(chips):
    x = cx0 + k * (cw + gap)
    kind = "pipe" if k == len(chips) - 1 else "online"
    fc, ec = C[kind]
    ax.add_patch(FancyBboxPatch((x, FY0 + 0.1), cw, 0.42, boxstyle="round,pad=0,rounding_size=0.04",
                                fc=fc, ec=ec, lw=0.7, zorder=3))
    ax.text(x + cw / 2, FY0 + 0.31, t, fontsize=5.4, ha="center", va="center", color=INK, zorder=4,
            linespacing=1.2)

# ── Google Earth Engine (external cloud service) ─────────────────────────────
GX0, GY0, GW, GH = 4.56, 6.55, 1.65, 1.12
box(GX0, GY0, GW, GH, "gee", "Google Earth Engine",
    ["external cloud service", "COPERNICUS/S2_SR_HARMONIZED", "Cloud Score+ mask",
     "annual median composite"], body_size=5.2)

# ── Backend host ─────────────────────────────────────────────────────────────
HX0, HY0, HW, HH = 0.06, 1.62, 6.15, 4.42
box(HX0, HY0, HW, HH, "back", None, ls=(0, (4, 2)), lw=0.8, rounding=0.08, z=0)
ax.text(1.40, HY0 + HH - 0.07, "Backend host · single deployment", fontsize=6.2,
        fontweight="bold", color=C["back"][1], va="top")

# FastAPI application
AX0, AY0, AW, AH = 0.16, 1.72, 4.10, 4.02
box(AX0, AY0, AW, AH, "back", "FastAPI backend  (Python 3.12 · Uvicorn / Gunicorn, 1 worker)  /api/v1",
    title_size=6.4, lw=0.9, z=1)

# online analysis column
OX0, OW = 0.26, 1.90
ax.text(OX0, 5.30, "Online analysis (request / response)", fontsize=5.8, fontweight="bold",
        color=C["online"][1], va="top")
online = [
    ("Lake & map data", ["GET /lakes · /regions · /temporal", "geometry, metadata, index history"]),
    ("Similarity search", ["GET /similarity/{region_id}", "5-year windows, exhaustive cosine (NumPy)"]),
    ("Ecological forecast", ["GET /forecast/ecological/{region_id}", "rank-weighted analog changes, τ(k,h)"]),
    ("PDF report", ["POST /report/{lake_id}", "Jinja2 + WeasyPrint, map renders"]),
]
oy = 5.08
for title, lines in online:
    box(OX0, oy - 0.60, OW, 0.60, "online", title, lines, title_size=6.0, body_size=5.2, pad=0.06, z=2)
    oy -= 0.67

# offline pipeline column
PX0, PW = 2.26, 1.90
ax.text(PX0, 5.30, "Offline pipeline (background tasks)", fontsize=5.8, fontweight="bold",
        color=C["pipe"][1], va="top")
box(PX0, 4.86, PW, 0.22, "pipe", None, ["guard: pipeline_permissions (master + stage)"], body_size=4.9,
    pad=0.05, z=2, lw=0.6)
stages = [
    ("1 Lake sync", "POST /sync/… · HydroLAKES, state GeoJSON"),
    ("2 Imagery download", "POST /imagery/fetch · tiles, retries"),
    ("3 Tile merge", "POST /imagery/merge · Rasterio"),
    ("4 Embedding generation", "POST /embeddings/generate"),
    ("5 Embedding re-blending", "POST /embeddings/merge · no inference"),
    ("6 Lake features", "POST /lake-features/generate"),
]
STAGE_H, STAGE_GAP = 0.33, 0.05
stage_y = {}
sy = 4.78
for k, (title, sub) in enumerate(stages):
    y0 = sy - STAGE_H
    box(PX0, y0, PW, STAGE_H, "pipe", title, [sub], title_size=5.9, body_size=4.9, pad=0.05, z=2)
    stage_y[k] = y0 + STAGE_H / 2
    sy = y0 - STAGE_GAP
ax.text(PX0 + PW / 2, sy + 0.02, "in-memory progress → GET …/status (polled) · POST …/cancel",
        fontsize=4.8, color=MUTED, ha="center", va="top", style="italic")

# data-access layer
DX0, DY0, DW, DH = 0.26, 1.82, 3.90, 0.30
box(DX0, DY0, DW, DH, "db", None,
    ["Repositories · SQLAlchemy 2 (async, asyncpg) · GeoAlchemy2 · pgvector"], body_size=5.4,
    align="center", pad=0.09, z=2, lw=0.7)
for x in (OX0 + OW / 2, PX0 + PW / 2):
    arrow((x, 2.34), (x, DY0 + DH), LINK["sql"], both=True, lw=0.8)

# right column inside the host: file store + Prithvi
RX0, RW = 4.56, 1.55
FSY0, FSH = 3.42, 1.80
box(RX0, FSY0, RW, FSH, "files", "GeoTIFF file store",
    ["local disk (per-year folders)", "data/sentinel/<year>/", "25 km tiles → lake_<id>.tif",
     "12-band uint16, nodata 65535", "≈ 3.4 GB per year", "paths kept in lake_tiles /", "lake_images"],
    body_size=5.0, title_size=6.2, z=2)
PRY0, PRH = 1.72, 1.52
box(RX0, PRY0, RW, PRH, "prithvi", "Prithvi encoder",
    ["Prithvi-EO-1.0-100M", "PyTorch, in-process", "local .pt checkpoint", "CPU (CUDA if present)",
     "encoder only, no fine-tuning"], body_size=5.0, title_size=6.2, z=2)

# ── PostgreSQL ───────────────────────────────────────────────────────────────
BX0, BY0, BW, BH = 0.06, 0.42, 6.15, 0.98
box(BX0, BY0, BW, BH, "db", "PostgreSQL 14  +  PostGIS  +  pgvector", title_size=6.6, z=1)
tables = ["lakes\n(geometry)", "india_states", "lake_tiles", "lake_images", "lake_features",
          "regions\n(3 × vector 768)", "pipeline_\npermissions", "reports"]
tw, tg = 0.70, 0.055
tx0 = BX0 + (BW - (len(tables) * tw + (len(tables) - 1) * tg)) / 2
for k, t in enumerate(tables):
    x = tx0 + k * (tw + tg)
    ax.add_patch(FancyBboxPatch((x, BY0 + 0.1), tw, 0.46, boxstyle="round,pad=0,rounding_size=0.03",
                                fc="white", ec=C["db"][1], lw=0.6, zorder=3))
    ax.text(x + tw / 2, BY0 + 0.33, t, fontsize=5.1, ha="center", va="center", color=INK, zorder=4,
            linespacing=1.15)
arrow((2.21, DY0), (2.21, BY0 + BH), LINK["sql"], both=True, lw=1.0)
label(2.21, (DY0 + BY0 + BH) / 2, "SQL over asyncpg", LINK["sql"])

# ── Links ────────────────────────────────────────────────────────────────────
# frontend ↔ backend (REST/JSON)
x_on, x_pipe = OX0 + OW / 2, PX0 + PW / 2
arrow((x_on, FY0), (x_on, AY0 + AH), LINK["rest"], both=True, lw=1.1)
arrow((x_pipe, FY0), (x_pipe, AY0 + AH), LINK["rest"], both=True, lw=1.1)
label(x_on, (FY0 + AY0 + AH) / 2, "HTTPS · REST / JSON\nanalysis requests", LINK["rest"])
label(x_pipe, (FY0 + AY0 + AH) / 2, "start job · poll /status · cancel", LINK["rest"])

# imagery download ↔ Earth Engine
x_gee_route = 4.37
y_img = stage_y[1]
line([PX0 + PW, x_gee_route], [y_img + 0.06, y_img + 0.06], LINK["gee"], lw=1.0)
line([x_gee_route, x_gee_route], [y_img + 0.06, 6.30], LINK["gee"], lw=1.0)
line([x_gee_route, GX0 + GW / 2], [6.30, 6.30], LINK["gee"], lw=1.0)
arrow((GX0 + GW / 2, 6.30), (GX0 + GW / 2, GY0), LINK["gee"], both=True, lw=1.0)
label((x_gee_route + GX0 + GW) / 2 + 0.05, 5.74,
      "Earth Engine Python API\nservice-account keys\ngetDownloadURL → GeoTIFF\nHTTP 429 → next account",
      LINK["gee"], size=4.9)

# stages ↔ file store
x_file = 4.46
line([PX0 + PW, x_file], [stage_y[1] - 0.06, stage_y[1] - 0.06], LINK["file"], lw=0.9)
for k in (2, 3, 5):  # merge, embedding generation, lake features use the rasters
    line([PX0 + PW, x_file], [stage_y[k] + 0.05, stage_y[k] + 0.05], LINK["file"], lw=0.9)
line([x_file, x_file], [stage_y[5] + 0.05, stage_y[1] - 0.06], LINK["file"], lw=0.9)
arrow((x_file, stage_y[2]), (RX0, stage_y[2]), LINK["file"], both=True, lw=0.9)
label(RX0 + RW / 2, FSY0 - 0.01, "write tiles · read merged rasters", LINK["file"], size=4.7, va="top")

# embeddings ↔ Prithvi
y_emb = stage_y[3] - 0.08
arrow((PX0 + PW, y_emb), (RX0, PRY0 + PRH - 0.25), LINK["prithvi"], both=True, lw=1.0)
label(RX0 + RW / 2, PRY0 - 0.0, "6-band windows → 768-d token vectors", LINK["prithvi"], size=4.6, va="top")

# ── Legend / note ────────────────────────────────────────────────────────────
items = [("rest", "REST / JSON"), ("sql", "SQL"), ("gee", "Earth Engine API"), ("file", "file I/O"),
         ("prithvi", "in-process model call")]
lx = 0.10
for key, txt in items:
    ax.plot([lx, lx + 0.22], [0.27, 0.27], color=LINK[key], lw=1.4)
    t = ax.text(lx + 0.27, 0.27, txt, fontsize=5.3, va="center", color=INK)
    lx += 0.27 + t.get_window_extent(renderer=fig.canvas.get_renderer()).width / fig.dpi + 0.2
ax.text(0.10, 0.09, "Online requests read stored results only; they never call Earth Engine or Prithvi. "
        "Pipeline stages are started from the frontend and run as FastAPI background tasks.",
        fontsize=5.0, va="center", ha="left", color=MUTED, style="italic")

fig.savefig(OUT + ".png", dpi=600, facecolor="white")
fig.savefig(OUT + ".pdf", facecolor="white")
print("ok")
