"""Figure 2 — EcoTwin system components and their communication (simplified).

Coordinates are inches on a 6.27 in wide portrait text block; the axes fill
the figure, so 1 data unit = 1 inch.
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = sys.argv[1]
W, H = 6.27, 3.8

INK = "#1f2933"
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

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7})
fig = plt.figure(figsize=(W, H), dpi=300)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")


def box(x, y, w, h, kind, title=None, lines=(), title_size=8, body_size=6.6, ls="-", lw=1.0, z=1):
    fc, ec = C[kind]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.06",
                                fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))
    cx = x + w / 2
    if title and lines:
        ax.text(cx, y + h - 0.1, title, fontsize=title_size, fontweight="bold", color=ec,
                ha="center", va="top", zorder=z + 1)
        ax.text(cx, y + h - 0.16 - title_size / 72 * 1.4, "\n".join(lines), fontsize=body_size,
                color=INK, ha="center", va="top", linespacing=1.4, zorder=z + 1)
    elif title:
        ax.text(cx, y + h / 2, title, fontsize=title_size, fontweight="bold", color=ec,
                ha="center", va="center", zorder=z + 1)


def arrow(p0, p1, color, lw=1.2):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>", mutation_scale=8, color=color, lw=lw,
                                 zorder=5, shrinkA=0, shrinkB=0))


def label(x, y, text, color, ha="center"):
    ax.text(x, y, text, fontsize=6.2, color=color, ha=ha, va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.95))


# frontend and Earth Engine
box(0.06, 3.20, 3.95, 0.50, "front", "Frontend (web browser)",
    ["map & lake search · analogs · forecasts · reports · pipeline controls"])
box(4.46, 3.20, 1.75, 0.50, "gee", "Google Earth Engine", ["Sentinel-2 imagery"])

# backend
box(0.06, 1.15, 4.20, 1.65, "back", None, ls=(0, (4, 2)), lw=0.9, z=0)
ax.text(2.16, 2.74, "FastAPI backend", fontsize=8, fontweight="bold", color=C["back"][1],
        ha="center", va="top")
box(0.18, 1.25, 1.90, 1.05, "online", "Online analysis",
    ["lake & map data", "similarity search", "ecological forecast", "PDF reports"], z=2)
box(2.24, 1.25, 1.90, 1.05, "pipe", "Offline pipeline",
    ["lake sync", "imagery download & merge", "embedding generation", "lake features"], z=2)

# local resources used by the pipeline
box(4.46, 1.90, 1.75, 0.55, "prithvi", "Prithvi encoder", ["pretrained, encoder only"])
box(4.46, 1.15, 1.75, 0.55, "files", "GeoTIFF store", ["merged lake rasters"])

# database
box(0.06, 0.30, 6.15, 0.50, "db", "PostgreSQL + PostGIS + pgvector",
    ["lake geometries · index history · 768-d embeddings"])

# links
arrow((1.13, 3.20), (1.13, 2.30), C["front"][1])
arrow((3.19, 3.20), (3.19, 2.30), C["front"][1])
label(2.16, 2.98, "REST / JSON", C["front"][1])
arrow((5.33, 2.95), (5.33, 3.20), C["gee"][1])
ax.plot([4.14, 4.36, 4.36, 5.33], [2.20, 2.20, 2.95, 2.95], color=C["gee"][1], lw=1.2, zorder=5)
arrow((4.14, 2.00), (4.46, 2.00), C["prithvi"][1])
arrow((4.14, 1.42), (4.46, 1.42), C["files"][1])
arrow((1.13, 1.25), (1.13, 0.80), C["db"][1])
arrow((3.19, 1.25), (3.19, 0.80), C["db"][1])
label(2.16, 0.98, "SQL", C["db"][1])

ax.text(W / 2, 0.13, "Online requests read stored results only; Earth Engine and Prithvi are used by the "
        "offline pipeline.", fontsize=6.2, ha="center", va="center", color="#52606d", style="italic")

fig.savefig(OUT + ".png", dpi=600, facecolor="white")
fig.savefig(OUT + ".pdf", facecolor="white")
print("ok")
