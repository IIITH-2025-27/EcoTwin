"""Figure 1 — EcoTwin offline processing workflow, applied to a synthetic lake.

Six panels follow one irregular (synthetic) reservoir through the pipeline,
using the parameters of the deployed system:
  1 lake synchronisation   HydroLAKES → PostGIS, active cohort ≥ 2 km²
  2 imagery acquisition    3.5 km buffer, 25 km tiles on a fixed global grid,
                           Sentinel-2 L2A annual median, 12-band uint16
  3 tile merging           all tiles complete → lake_<id>.tif, nodata 65535
  4 lake features          lake pixels only: band stats, 14 indices, GLCM(B8)
  5 embeddings             224 px (6.72 km) windows, 480 m tokens, 500 m shore
                           ring, only lake/shore tokens encoded by Prithvi
  6 re-blending            z = normalise(λ·l + (1−λ)·s), λ = 0.7 → regions
Coordinates are in km.
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

OUT = sys.argv[1]  # output path without extension
rng = np.random.default_rng(11)

# ── Palette ──────────────────────────────────────────────────────────────────
INK = "#1f2933"
MUTED = "#5f6b7a"
LAKE = "#1f6fb2"
SHORE = "#e07b39"
BUFFER = "#4a5568"
TILE_COLORS = ["#8dd3c7", "#fdb462", "#bebada", "#fb8072", "#80b1d3", "#b3de69"]
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 6,
    "axes.linewidth": 0.6,
    "mathtext.fontset": "stix",  # serif math so bold l is not read as I
})

# ── Synthetic lake ───────────────────────────────────────────────────────────
def blob(cx, cy, rx, ry, rot_deg, amp=0.16, n=360):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = np.ones_like(t)
    for k in range(2, 9):
        r += amp / k ** 0.8 * rng.normal() * np.cos(k * t + rng.uniform(0, 2 * np.pi))
    poly = Polygon(np.c_[rx * r * np.cos(t), ry * r * np.sin(t)])
    return translate(rotate(poly, rot_deg, origin=(0, 0)), cx, cy)


CX, CY = 37.6, 24.2  # off the 25 km grid so tile lines cut through the lake
parts = [
    blob(0, 0, 11.5, 3.6, 8),          # main basin
    blob(9.5, 3.8, 6.0, 1.7, 38),      # north-east arm
    blob(-9.0, -2.4, 5.2, 2.1, -28),   # western arm
    blob(2.5, -4.6, 3.8, 1.3, -72),    # southern inlet
    blob(-3.0, 3.6, 3.0, 1.1, 64),     # small northern bay
]
lake = unary_union(parts).buffer(0.9).buffer(-0.9)
if lake.geom_type != "Polygon":
    lake = max(lake.geoms, key=lambda g: g.area)
island = blob(1.8, 0.4, 1.1, 0.55, 20, amp=0.1)
lake = translate(lake.difference(island), CX, CY)
lake = lake.simplify(0.03)

buffer_poly = lake.buffer(3.5).simplify(0.03)      # LAKE_IMAGERY_BUFFER_METRES
shore_outer = lake.buffer(0.5)                       # EMBEDDING_SHORE_RING_METRES
shore_ring = shore_outer.difference(lake)

xmin, ymin, xmax, ymax = buffer_poly.bounds
PAD = 1.2
EXT = (xmin - PAD, xmax + PAD, ymin - PAD, ymax + PAD)

# ── Synthetic Sentinel-2 composite (display resolution 0.15 km) ─────────────
RES = 0.15
xs = np.arange(EXT[0], EXT[1], RES) + RES / 2
ys = np.arange(EXT[2], EXT[3], RES) + RES / 2
X, Y = np.meshgrid(xs, ys)
in_lake = shapely.contains_xy(lake, X, Y)
in_buffer = shapely.contains_xy(buffer_poly, X, Y)
pts = shapely.points(X.ravel(), Y.ravel())
dist_shore = shapely.distance(lake.boundary, pts).reshape(X.shape)


def smooth_noise(shape, scale):
    f = np.fft.fft2(rng.normal(size=shape))
    ky = np.fft.fftfreq(shape[0])[:, None]
    kx = np.fft.fftfreq(shape[1])[None, :]
    f *= np.exp(-(kx ** 2 + ky ** 2) * (scale ** 2))
    n = np.real(np.fft.ifft2(f))
    return (n - n.mean()) / n.std()


veg = 0.55 * smooth_noise(X.shape, 18) + 0.45 * smooth_noise(X.shape, 6)
veg = np.clip((veg + 2) / 4, 0, 1)
veg = np.clip(veg + 0.25 * np.exp(-dist_shore / 1.2), 0, 1)  # greener near shore
soil, green = np.array(to_rgb("#b9a77f")), np.array(to_rgb("#4f7a3a"))
land_rgb = soil[None, None, :] * (1 - veg[..., None]) + green[None, None, :] * veg[..., None]
land_rgb *= (0.92 + 0.08 * smooth_noise(X.shape, 2)[..., None] * 0.5)
depth = np.clip(dist_shore / 2.5, 0, 1)
turbid = np.clip(0.5 + 0.5 * smooth_noise(X.shape, 10), 0, 1)
deep, shallow = np.array(to_rgb("#0d2b4a")), np.array(to_rgb("#3f8fa3"))
water_rgb = (shallow[None, None, :] * (1 - depth[..., None]) + deep[None, None, :] * depth[..., None])
water_rgb = water_rgb * (0.85 + 0.25 * turbid[..., None])
rgb = np.where(in_lake[..., None], water_rgb, land_rgb).clip(0, 1)

# NDCI-like field over the lake (higher in shallow, turbid bays)
ndci = 0.02 + 0.09 * (1 - depth) + 0.03 * turbid + 0.01 * smooth_noise(X.shape, 4)
ndci = np.where(in_lake, ndci, np.nan)

# ── 25 km tiles on a fixed global grid, trimmed to the buffer ────────────────
TILE = 25.0
tiles = []
for tx in np.arange(np.floor(xmin / TILE) * TILE, xmax, TILE):
    for ty in np.arange(np.floor(ymin / TILE) * TILE, ymax, TILE):
        piece = box(tx, ty, tx + TILE, ty + TILE).intersection(buffer_poly)
        if not piece.is_empty and piece.area > 0.2:
            tiles.append((tx, ty, piece))
tiles.sort(key=lambda t: (-t[1], t[0]))

# ── Prithvi windows (224 px × 30 m) and 480 m tokens over lake + shore ──────
WIN, TOK = 6.72, 0.48
sx0, sy0, sx1, sy1 = shore_outer.bounds
nwx = int(np.ceil((sx1 - sx0) / WIN))
nwy = int(np.ceil((sy1 - sy0) / WIN))
wx0 = sx0 - (nwx * WIN - (sx1 - sx0)) / 2
wy0 = sy0 - (nwy * WIN - (sy1 - sy0)) / 2
ntx, nty = nwx * 14, nwy * 14
SUB = 6  # sub-samples per token side to estimate pixel fractions
u = (np.arange(ntx * SUB) + 0.5) * (TOK / SUB) + wx0
v = (np.arange(nty * SUB) + 0.5) * (TOK / SUB) + wy0
U, V = np.meshgrid(u, v)
sub_lake = shapely.contains_xy(lake, U, V).reshape(nty, SUB, ntx, SUB)
sub_shore = shapely.contains_xy(shore_ring, U, V).reshape(nty, SUB, ntx, SUB)
a_t = sub_lake.mean(axis=(1, 3))   # lake fraction per token
b_t = sub_shore.mean(axis=(1, 3))  # shore fraction per token
encoded = (a_t > 0) | (b_t > 0)
n_tokens, n_encoded = encoded.size, int(encoded.sum())

# ── Figure layout (inches, measured from the top-left corner) ──────────────
# Portrait A4 text block: 6.27 in wide, so the figure is placed at 100 % scale.
# Two columns × three rows, read left to right: 1 2 / 3 4 / 5 6.
FIG_W = 6.27
PANEL_W = 2.86
PANEL_H = PANEL_W * (EXT[3] - EXT[2]) / (EXT[1] - EXT[0])  # maps fill their axes exactly
COL_X = [0.13, 0.13 + PANEL_W + 0.33]
NCOLS = 2
TITLE_H, KEY_H, CAPTION_H, BUS_H = 0.30, 0.24, 0.28, 0.26
ROW_TOP = [TITLE_H]
for _ in range(2):
    ROW_TOP.append(ROW_TOP[-1] + PANEL_H + KEY_H + CAPTION_H + BUS_H + TITLE_H)
FIG_H = ROW_TOP[-1] + PANEL_H + KEY_H + CAPTION_H + 0.27
fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=300)


def fx(x_in):
    return x_in / FIG_W


def fy(y_in_from_top):
    return 1 - y_in_from_top / FIG_H


# Panels are built in content order (sync, acquisition, merge, features,
# embeddings, re-blend); SLOT places them in pipeline order, so lake
# features — the last stage in the app's pipeline menu — sits in slot 6.
SLOT = [0, 1, 2, 5, 3, 4]
axes = [
    fig.add_axes([fx(COL_X[SLOT[i] % NCOLS]), fy(ROW_TOP[SLOT[i] // NCOLS] + PANEL_H), fx(PANEL_W),
                  PANEL_H / FIG_H])
    for i in range(6)
]

TITLES = [
    "1  Lake synchronisation",
    "2  Imagery acquisition",
    "3  Tile merging",
    "6  Lake-feature generation",
    "4  Embedding generation",
    "5  Embedding re-blending",
]
CAPTIONS = [
    "HydroLAKES polygons → PostGIS lakes table; active cohort:\narea ≥ 2 km² (smaller lakes kept for the map only)",
    "3.5 km buffer, 25 km tiles on a fixed global 30 m grid; S2 L2A,\nscene cloud ≤ 20 %, Cloud Score+ ≥ 0.6, annual median",
    "Merged once all tiles of the lake-year are complete →\nlake_<id>.tif, 12-band uint16 (reflectance × 10⁴)",
    "From the merged raster (3), lake pixels only: 11 bands ×\n5 statistics, 14 indices, GLCM on B8 → lake_features",
    "224 × 224 px windows (6.72 km) of 480 m tokens; only tokens\ntouching the lake or 500 m shore ring go to Prithvi-EO-1.0",
    "z = normalise(λ·l + (1 − λ)·s), λ = 0.7, stored with l and s in\nregions (pgvector); a new λ re-blends without inference",
]


def style_map(ax):
    ax.set_xlim(EXT[0], EXT[1])
    ax.set_ylim(EXT[2], EXT[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#c3cad4")


def draw_poly(ax, geom, **kw):
    geoms = getattr(geom, "geoms", [geom])
    for g in geoms:
        verts, codes = [], []
        for ring in [g.exterior, *g.interiors]:
            c = np.asarray(ring.coords)
            verts.extend(c)
            codes.extend([Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY])
        ax.add_patch(PathPatch(Path(verts, codes), **kw))


def scalebar(ax, km=10, color=INK):
    x0 = EXT[0] + 1.2
    y0 = EXT[2] + 1.2
    ax.plot([x0, x0 + km], [y0, y0], color=color, lw=1.4, solid_capstyle="butt")
    ax.text(x0 + km / 2, y0 + 0.6, f"{km} km", ha="center", va="bottom", fontsize=6, color=color)


def header(ax, i):
    pos = ax.get_position()
    fig.text(pos.x0, pos.y1 + 0.06 / FIG_H, TITLES[i], fontsize=8.5, fontweight="bold", color=INK, va="bottom")
    fig.text(pos.x0, pos.y0 - KEY_H / FIG_H, CAPTIONS[i], fontsize=6.2, color=MUTED, va="top",
             linespacing=1.35)


def key_row(ax, items):
    """Legend row under a panel: [(colour or None, text), ...]."""
    pos = ax.get_position()
    x = pos.x0
    y = pos.y0 - 0.075 / FIG_H
    for color, txt in items:
        if color:
            fig.patches.append(Rectangle((x, y - 0.035 / FIG_H), 0.07 / FIG_W, 0.07 / FIG_H,
                                         transform=fig.transFigure, fc=color, ec="none"))
            x += 0.1 / FIG_W
        t = fig.text(x, y, txt, fontsize=5.6, color=INK, va="center")
        width_px = t.get_window_extent(renderer=fig.canvas.get_renderer()).width
        x += width_px / fig.bbox.width + 0.14 / FIG_W


# Panel 1 — lake synchronisation -------------------------------------------------
ax = axes[0]
style_map(ax)
ax.set_facecolor("#f4f1ea")
small = []
for _ in range(60):
    cx, cy = rng.uniform(EXT[0], EXT[1]), rng.uniform(EXT[2], EXT[3])
    g = blob(cx, cy, rng.uniform(0.25, 0.9), rng.uniform(0.15, 0.5), rng.uniform(0, 180), amp=0.25, n=60)
    if g.distance(lake) > 0.6:
        small.append(g)
for g in small:
    draw_poly(ax, g, facecolor="#c9d3de", edgecolor="#9aa8b8", lw=0.3)
draw_poly(ax, lake, facecolor="#cfe3f5", edgecolor=LAKE, lw=1.0)
area = lake.area
label_xy = (EXT[0] + 1.2, EXT[3] - 1.2)
edge = lake.exterior.interpolate(lake.exterior.project(shapely.Point(label_xy[0] + 8, label_xy[1])))
ax.annotate(f"lake_id 1001 (active)\narea {area:.0f} km²",
            xy=(edge.x, edge.y), xytext=label_xy, fontsize=6.5, color=LAKE,
            va="top", arrowprops=dict(arrowstyle="-", color=LAKE, lw=0.5, shrinkA=0, shrinkB=0,
                                      relpos=(0.6, 0)))
ax.text(EXT[1] - 1, EXT[2] + 1.3, "< 2 km²: inventory only", fontsize=6, color="#7b8794", ha="right")
scalebar(ax)
header(ax, 0)

# Panel 2 — imagery acquisition --------------------------------------------------
ax = axes[1]
style_map(ax)
ax.set_facecolor("#ffffff")
SPLIT_TILE, RETRY_TILE = 1, 4  # T2 hits the GEE memory limit, T5 gets HTTP 429
for k, (tx, ty, piece) in enumerate(tiles):
    color = TILE_COLORS[k % len(TILE_COLORS)]
    draw_poly(ax, piece, facecolor=color, alpha=0.55, edgecolor="white", lw=1.0)
    if k == SPLIT_TILE:
        bx0, by0, bx1, by1 = piece.bounds
        mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
        for seg in (shapely.LineString([(mx, by0), (mx, by1)]), shapely.LineString([(bx0, my), (bx1, my)])):
            cut = seg.intersection(piece)
            for g in getattr(cut, "geoms", [cut]):
                ax.plot(*g.xy, color=INK, lw=0.5, ls=(0, (2, 1.2)))
    c = piece.representative_point()
    if piece.area > 40:
        c = piece.centroid if piece.contains(piece.centroid) else c
    label = f"T{k + 1}" + (" ×4" if k == SPLIT_TILE else "") + (" ↻" if k == RETRY_TILE else "")
    ax.text(c.x, c.y, label, fontsize=6.8, fontweight="bold", color=INK, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))
# fixed 25 km grid lines
for gx in np.arange(np.ceil(EXT[0] / TILE) * TILE, EXT[1], TILE):
    ax.axvline(gx, color=BUFFER, lw=0.5, ls=(0, (4, 2)))
for gy in np.arange(np.ceil(EXT[2] / TILE) * TILE, EXT[3], TILE):
    ax.axhline(gy, color=BUFFER, lw=0.5, ls=(0, (4, 2)))
draw_poly(ax, buffer_poly, facecolor="none", edgecolor=BUFFER, lw=0.8, ls=(0, (3, 1.5)))
draw_poly(ax, lake, facecolor="none", edgecolor=LAKE, lw=0.9)
ax.text(EXT[0] + 1, EXT[3] - 1, "3.5 km buffer", fontsize=6, color=BUFFER, va="top")
ax.text(EXT[1] - 0.8, EXT[2] + 1.0, "- - 25 km grid", fontsize=6, color=BUFFER, va="bottom", ha="right",
        bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))
scalebar(ax)
key_row(ax, [(None, "×4: memory limit → 4 parts, stitched"), (None, "↻: HTTP 429 → next account")])
header(ax, 1)

# Panel 3 — tile merging -------------------------------------------------------
ax = axes[2]
style_map(ax)
merged = np.where(in_buffer[..., None], rgb, 1.0)
ax.imshow(merged, extent=EXT, origin="lower", interpolation="nearest")
draw_poly(ax, buffer_poly, facecolor="none", edgecolor=BUFFER, lw=0.6)
ax.text(EXT[0] + 1, EXT[3] - 1, "nodata 65535", fontsize=6, color=MUTED, va="top")
# band-stack glyph in the empty bottom-right corner
GW, GH = 6.0, 3.4
gx, gy = EXT[1] - GW - 2.4, EXT[2] + 3.4
for k in range(5):
    ax.add_patch(Rectangle((gx + k * 0.45, gy - k * 0.45), GW, GH, fc="white", ec=INK, lw=0.4, zorder=5 + k))
ax.text(gx + 4 * 0.45 + GW / 2, gy - 4 * 0.45 + GH / 2, "B1–B12\n+ CLEAR", fontsize=5, ha="center",
        va="center", zorder=20, linespacing=1.15)
scalebar(ax)
header(ax, 2)

# Panel 4 — lake-feature generation ---------------------------------------------
ax = axes[3]
style_map(ax)
gray_rgb = np.where(in_buffer[..., None], 0.55 + 0.45 * rgb.mean(axis=2, keepdims=True), 1.0)
gray_rgb = np.repeat(gray_rgb, 3, axis=2) if gray_rgb.shape[2] == 1 else gray_rgb
ax.imshow(np.clip(gray_rgb, 0, 1), extent=EXT, origin="lower", interpolation="nearest", alpha=0.55)
cmap = LinearSegmentedColormap.from_list("ndci", ["#08306b", "#2171b5", "#41b6c4", "#a1dab4", "#f7fcb9"])
im = ax.imshow(ndci, extent=EXT, origin="lower", cmap=cmap, vmin=0.02, vmax=0.14, interpolation="nearest")
draw_poly(ax, lake, facecolor="none", edgecolor=INK, lw=0.6)
cax = fig.add_axes([axes[3].get_position().x0 + 0.012, axes[3].get_position().y1 - 0.045, 0.085, 0.009])
cb = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[0.02, 0.08, 0.14])
cb.ax.tick_params(labelsize=5.4, length=1.5, pad=1)
cb.outline.set_linewidth(0.3)
cax.set_title("NDCI (example)", fontsize=5.8, pad=2)
scalebar(ax)
key_row(ax, [("#b8bec7", "shore / buffer pixels: excluded"), (LAKE, "lake pixels: statistics")])
header(ax, 3)

# Panel 5 — embedding generation ------------------------------------------------
ax = axes[4]
style_map(ax)
tok_rgb = np.ones((nty, ntx, 3))
lake_c, shore_c, both_c = map(np.array, (to_rgb(LAKE), to_rgb(SHORE), to_rgb("#7b5ea7")))
for (iy, ix), _ in np.ndenumerate(a_t):
    a, b = a_t[iy, ix], b_t[iy, ix]
    if a > 0 and a >= b:
        tok_rgb[iy, ix] = 1 - (1 - lake_c) * (0.35 + 0.65 * a)
    elif b > 0:
        tok_rgb[iy, ix] = 1 - (1 - shore_c) * (0.35 + 0.65 * min(1, b * 2))
    else:
        tok_rgb[iy, ix] = (0.95, 0.95, 0.95)
tok_ext = (wx0, wx0 + ntx * TOK, wy0, wy0 + nty * TOK)
ax.imshow(tok_rgb, extent=tok_ext, origin="lower", interpolation="nearest")
for k in range(ntx + 1):
    ax.plot([wx0 + k * TOK] * 2, tok_ext[2:], color="white", lw=0.15)
for k in range(nty + 1):
    ax.plot(tok_ext[:2], [wy0 + k * TOK] * 2, color="white", lw=0.15)
for k in range(nwx + 1):
    ax.plot([wx0 + k * WIN] * 2, tok_ext[2:], color=INK, lw=0.7)
for k in range(nwy + 1):
    ax.plot(tok_ext[:2], [wy0 + k * WIN] * 2, color=INK, lw=0.7)
draw_poly(ax, lake, facecolor="none", edgecolor=LAKE, lw=0.6)
draw_poly(ax, shore_outer, facecolor="none", edgecolor=SHORE, lw=0.5)
ax.text((tok_ext[0] + tok_ext[1]) / 2, tok_ext[2] - 0.35,
         f"{nwx * nwy} windows · {n_encoded} of {n_tokens} tokens encoded", fontsize=5.8, color=INK,
         ha="center", va="top")
key_row(ax, [(LAKE, "lake token (aₜ > 0)"), (SHORE, "shore token (bₜ > 0)"), ("#e4e7eb", "not encoded")])
header(ax, 4)

# Panel 6 — embedding re-blending -----------------------------------------------
ax = axes[5]
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.set_xticks([])
ax.set_yticks([])
for s in ax.spines.values():
    s.set_color("#c3cad4")
vec_cmap = LinearSegmentedColormap.from_list("vec", ["#2c7bb6", "#f7f7f7", "#d7191c"])
lv = np.tanh(rng.normal(size=48) * 0.9)
sv = np.tanh(0.5 * lv + rng.normal(size=48) * 0.9)
zv = 0.7 * lv + 0.3 * sv
zv /= np.abs(zv).max()


def strip(y, values, label, color):
    ax.imshow(values[None, :], extent=(2.0, 9.4, y, y + 0.75), cmap=vec_cmap, vmin=-1, vmax=1, aspect="auto")
    ax.add_patch(Rectangle((2.0, y), 7.4, 0.75, fc="none", ec=color, lw=0.8))
    ax.text(1.8, y + 0.37, label, ha="right", va="center", fontsize=8.5, color=color)


strip(8.2, lv, r"$\mathbf{l}$", LAKE)
strip(6.9, sv, r"$\mathbf{s}$", SHORE)
ax.text(5.7, 8.2 + 0.95, "lake vector (768-d)", fontsize=5.8, ha="center", color=MUTED)
ax.text(5.7, 6.9 - 0.32, "shore vector (768-d)", fontsize=5.8, ha="center", color=MUTED, va="top")
ax.text(5.7, 5.45, r"normalise$(0.7\,\mathbf{l} + 0.3\,\mathbf{s})$", fontsize=7.2, ha="center", va="center",
        color=INK)
ax.add_patch(FancyArrowPatch((5.7, 5.05), (5.7, 4.55), arrowstyle="-|>", mutation_scale=6, color=INK, lw=0.6))
strip(3.7, zv, r"$\mathbf{z}$", INK)
# λ slider
ax.plot([2.0, 9.4], [2.75, 2.75], color="#c3cad4", lw=1.6, solid_capstyle="round")
ax.plot([2.0, 2.0 + 0.7 * 7.4], [2.75, 2.75], color=LAKE, lw=1.6, solid_capstyle="round")
ax.plot(2.0 + 0.7 * 7.4, 2.75, "o", ms=3.5, mfc="white", mec=LAKE, mew=0.8)
ax.text(2.0, 3.05, "shore", fontsize=5.6, color=SHORE)
ax.text(9.4, 3.05, "lake", fontsize=5.6, color=LAKE, ha="right")
ax.text(2.0 + 0.7 * 7.4, 2.35, "λ = 0.7", fontsize=5.8, ha="center", va="top", color=LAKE)
# database cylinder
cx0, cy0, cw, chh = 2.4, 0.35, 6.6, 1.15
ax.add_patch(Rectangle((cx0, cy0), cw, chh, fc="#eef2f7", ec=INK, lw=0.5))
for yy in (cy0, cy0 + chh):
    ax.add_patch(matplotlib.patches.Ellipse((cx0 + cw / 2, yy), cw, 0.35, fc="#eef2f7", ec=INK, lw=0.5))
ax.text(cx0 + cw / 2, cy0 + chh / 2 - 0.05, "regions · pgvector · (lake_id, year)", fontsize=6, ha="center",
        va="center", color=INK)
header(ax, 5)

# ── Flow arrows ──────────────────────────────────────────────────────────────
def fig_arrow(p0, p1, **kw):
    fig.patches.append(FancyArrowPatch(p0, p1, transform=fig.transFigure, arrowstyle="-|>",
                                       mutation_scale=9, color="#334e68", lw=1.0, **kw))


slot_pos = {SLOT[i]: axes[i].get_position() for i in range(6)}
line_kw = dict(transform=fig.transFigure, color="#334e68", lw=1.0)
# within a row: slot 0→1, 2→3, 4→5
for a in (0, 2, 4):
    pa, pb = slot_pos[a], slot_pos[a + 1]
    y = pa.y0 + pa.height / 2
    fig_arrow((pa.x1 + 0.006, y), (pb.x0 - 0.006, y))
# row wraps: slot 1→2 and 3→4
x_left = fx(COL_X[0] + PANEL_W / 2)
x_right = fx(COL_X[1] + PANEL_W / 2)
for row in (0, 1):
    caption_end = ROW_TOP[row] + PANEL_H + KEY_H + CAPTION_H
    bus_y = fy(caption_end + BUS_H * 0.5)
    fig.lines.append(plt.Line2D([x_right, x_right], [fy(caption_end + 0.02), bus_y], **line_kw))
    fig.lines.append(plt.Line2D([x_left, x_right], [bus_y, bus_y], **line_kw))
    fig_arrow((x_left, bus_y), (x_left, fy(ROW_TOP[row + 1] - TITLE_H + 0.03)))

fig.text(0.5, 0.05 / FIG_H,
         "Stages run in this order as background API jobs; each records per-tile / per-lake-year status in PostgreSQL\n"
         "and skips work that is already complete and current (resumable).  Illustrative synthetic lake, drawn to scale.",
         fontsize=5.6, ha="center", va="bottom", color=MUTED, linespacing=1.4)

fig.savefig(OUT + ".png", dpi=600, facecolor="white")
fig.savefig(OUT + ".pdf", facecolor="white")
print(f"lake area {area:.1f} km², tiles {len(tiles)}, windows {nwx * nwy}, tokens {n_encoded}/{n_tokens}")
