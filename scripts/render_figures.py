#!/usr/bin/env python3
"""
Presentation figures for the S-151 deliverable.

CONVENTIONS (project standing rules, applied here rather than remembered)
=========================================================================
- Every figure is written to output/figures/ AT RENDER TIME. A figure
  that exists only in a scratchpad is gone when the report is written --
  this cost the predecessor project its entire first figure set.
- Every map figure carries a scale bar and a north arrow; every legend
  names its units. Linear units are METRES (EPSG:6350), never feet.
- A caption may not claim more than the figure demonstrates. Where a
  finding is real but only legible in numbers, the figure shows the
  numbers -- a curve, a table, a histogram -- rather than asking the
  reader to see something in a hillshade that is not visible at print
  size. Overclaiming captions in the predecessor project turned out to
  be the first visible symptom of an unverified result underneath.
- Any comparison states its reference explicitly, because the reference
  is the component that has been wrong in every retracted finding here.

North is up: EPSG:6350 is a projected CRS and these rasters are
axis-aligned, so a plain arrow is honest.
"""
import subprocess
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_bootstrap  # noqa: F401,E402  -- MUST precede numpy/rasterio

import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
FIG = ROOT / "output" / "figures"
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
DPI = 200

VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"

# S-151 works, SFWMD AHED coordinate projected to EPSG:6350. Marked on
# the coverage panels because an unexplained disruption in a coverage
# figure invites the reader to wonder what went wrong; naming it settles
# that. Verified by containment, not by matching shapes.
S151_XY = (1557843.9, 456241.2)


def mark_s151(ax, color="white"):
    ax.plot(*S151_XY, marker="o", ms=9, mfc="none", mec=color, mew=1.8,
            zorder=13)
    ax.annotate("S-151", xy=S151_XY, xytext=(-46, 16),
                textcoords="offset points", color=color, fontsize=9,
                zorder=13, fontweight="bold",
                bbox=dict(fc="black", ec="none", alpha=0.45, pad=1.5))
FINAL = DEM / "dem_w3_s0.05_t0.15.tif"


def env():
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([str(ENV), str(ENV / "Library" / "bin"),
                                  str(ENV / "Scripts"), e.get("PATH", "")])
    e["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    e["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")
    return e


def add_scalebar(ax, length_m, loc=(0.05, 0.06), color="black"):
    """Scale bar in METRES, drawn in axes fraction over map coordinates."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    span = x1 - x0
    xs = x0 + loc[0] * span
    ys = y0 + loc[1] * (y1 - y0)
    h = 0.012 * abs(y1 - y0)
    ax.add_patch(Rectangle((xs, ys), length_m, h, facecolor=color,
                            edgecolor=color, zorder=10))
    ax.add_patch(Rectangle((xs + length_m / 2, ys), length_m / 2, h,
                            facecolor="white", edgecolor=color, zorder=11))
    ax.text(xs + length_m / 2, ys + h * 1.9, f"{length_m:g} m",
            ha="center", va="bottom", fontsize=8, color=color, zorder=12,
            bbox=dict(fc="white", ec="none", alpha=0.75, pad=1))


def add_north_arrow(ax, loc=(0.93, 0.86), size=0.09, color="black"):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + loc[0] * (x1 - x0)
    y = y0 + loc[1] * (y1 - y0)
    dy = size * (y1 - y0)
    ax.annotate("", xy=(x, y + dy), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.6),
                zorder=12)
    ax.text(x, y + dy * 1.08, "N", ha="center", va="bottom", fontsize=9,
            color=color, zorder=12,
            bbox=dict(fc="white", ec="none", alpha=0.75, pad=1))


def load(p, nodata_to_nan=True):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if nodata_to_nan and ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    ext = [ds.bounds.left, ds.bounds.right, ds.bounds.bottom, ds.bounds.top]
    return a, ext, ds


def agg(a, f):
    if f == 1:
        return a
    h = (a.shape[0] // f) * f
    w = (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).sum(axis=(1, 3))


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    out = FIG / name
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out.relative_to(ROOT)}")


# ======================================================================
# fig01 -- what the tile actually offers: coverage, not density
# ======================================================================
def fig01_coverage():
    g05, _, _ = load(DEM / "count_ground_0.5m.tif", False)
    a05, _, _ = load(DEM / "count_allret_0.5m.tif", False)
    g05 = np.nan_to_num(g05)
    a05 = np.nan_to_num(a05)
    g3, a3 = agg(g05, 6), agg(a05, 6)
    _, ext, _ = load(VENDOR)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6))

    im = axes[0].imshow(a3 / 9.0, extent=ext, origin="upper", cmap="viridis",
                        vmin=0, vmax=40)
    cb = plt.colorbar(im, ax=axes[0], fraction=0.046, pad=0.03, extend="max")
    cb.set_label("all returns per m²")
    # The density structure is the two flight lines, not a corner: both
    # the north and south edges are single-coverage (measured 12.5/13.6
    # and 10.6/11.6 pts/m² west/east) while the middle band, where the
    # swaths overlap, runs 19.6. An earlier caption called this an "SE
    # corner", which described a full-width band by one of its corners.
    axes[0].set_title("All returns — 16.89 pts/m² mean\n"
                       "N and S edges are single-swath (11–14 pts/m²);\n"
                       "the middle band has both lines (19.6 pts/m²)")

    im = axes[1].imshow(g3 / 9.0, extent=ext, origin="upper", cmap="magma",
                        vmin=0, vmax=6)
    cb = plt.colorbar(im, ax=axes[1], fraction=0.046, pad=0.03, extend="max")
    cb.set_label("ground returns per m²")
    axes[1].set_title("Ground returns — 1.26 pts/m² mean\n"
                       "7.4% of points; the operative constraint.\n"
                       "Bright SE feature is the S-151 works (hard surfaces)")

    # Void classes: the finding is that 'void' is two different failures.
    cls = np.zeros(a3.shape)
    cls[(a3 > 0) & (g3 == 0)] = 1     # vegetation blocked
    cls[a3 == 0] = 2                  # water dropout
    cmap = matplotlib.colors.ListedColormap(["#e8e8e8", "#4c9f70", "#2b5d9e"])
    axes[2].imshow(cls, extent=ext, origin="upper", cmap=cmap, vmin=0, vmax=2)
    # The green class was proposed to be the levee crown. Measured and
    # refuted: 6 of 706 crest cells are green, and green cells sit at
    # +0.07 m above marsh against the crown's +2.37 m. They are the
    # vegetated toe and berm flanking the levee, enriched 9-51 m out.
    axes[2].set_title("Two distinct void classes at 3 m\n"
                       "(vegetation is recoverable; water is not).\n"
                       "Green strips = vegetated levee toe and berm, NOT the crown")
    axes[2].legend(handles=[
        Line2D([], [], marker="s", ls="", ms=10, mfc="#e8e8e8", mec="grey",
               label="ground present — 52.9%"),
        Line2D([], [], marker="s", ls="", ms=10, mfc="#4c9f70", mec="none",
               label="returns, none ground — 41.0% (toe/berm vegetation)"),
        Line2D([], [], marker="s", ls="", ms=10, mfc="#2b5d9e", mec="none",
               label="no returns at all — 6.1%"),
    ], loc="upper left", bbox_to_anchor=(0.0, -0.14), fontsize=8,
       framealpha=0.9, borderaxespad=0.0)

    for ax in axes:
        ax.set_xlabel("Easting (m, EPSG:6350)")
        ax.tick_params(labelsize=8)
        add_scalebar(ax, 200)
        add_north_arrow(ax)
        mark_s151(ax)
    axes[0].set_ylabel("Northing (m, EPSG:6350)")
    fig.suptitle("Coverage, not density, is the binding constraint at S-151\n"
                 "Density structure is the two flight lines (panel 1); the "
                 "bright SE feature is the S-151 works (panel 2)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, "fig01_coverage.png")


# ======================================================================
# fig02 -- the cell-size sweep: the measurement that set cell = 3 m
# ======================================================================
def fig02_cell_sweep():
    cells = [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
    no_ground = [76.789, 47.042, 18.111, 8.292, 4.630, 2.210]
    no_return = [7.240, 6.061, 5.290, 4.725, 3.790, 1.980]

    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    ax.plot(cells, no_ground, "o-", lw=2, color="#b5423a",
            label="cells with NO ground return (vegetation + water)")
    ax.plot(cells, no_return, "s-", lw=2, color="#2b5d9e",
            label="cells with NO returns at all (water only)")
    ax.fill_between(cells, no_return, no_ground, alpha=0.15, color="#b5423a",
                    label="the vegetation-recoverable gap")

    ax.axvspan(3.0, 5.0, color="green", alpha=0.10)
    ax.annotate("3–5 m: the gap has closed,\nonly water remains",
                xy=(4.0, 30), ha="center", fontsize=9, color="darkgreen")
    ax.axvline(1.0, ls=":", color="grey")
    ax.annotate("San Xavier's cell (3.3 ft ≈ 1 m)\nwould leave 47% of cells empty",
                xy=(1.0, 47.0), xytext=(1.35, 62), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="grey"))

    ax.set_xscale("log")
    ax.set_xticks(cells)
    ax.set_xticklabels([f"{c:g}" for c in cells])
    ax.set_xlabel("SMRF cell size (m)")
    ax.set_ylabel("Share of tile (%)")
    ax.set_title("Cell size is set by ground COVERAGE, not by point density\n"
                  "Reference: share of cells over the full 1 km tile, "
                  "binmode counts (no interpolation)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    save(fig, "fig02_cell_sweep.png")


# ======================================================================
# fig03 -- why the crown cannot be preserved. The headline limitation,
#          shown as numbers because it is not visible in a hillshade.
# ======================================================================
def fig03_embankment_profile():
    h = [0.30, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 2.75]
    w = [45.7, 43.3, 36.0, 32.3, 30.0, 25.5, 21.6, 18.0, 13.4, 8.5, 6.0]

    fig, ax = plt.subplots(figsize=(8.6, 5.8))
    ax.plot(w, h, "o-", lw=2.2, color="#6b4c9a", label="embankment width")
    ax.fill_betweenx(h, 0, w, alpha=0.12, color="#6b4c9a")

    for r, style in ((1, "-"), (2, "--"), (4, ":")):
        span = (2 * r + 1) * 3.0
        ax.axvline(span, ls=style, color="#b5423a", lw=1.5)
        ax.text(span, 2.86, f" r={r}px\n {span:.0f} m", color="#b5423a",
                fontsize=8, va="top")

    ax.annotate("crown: 6–8.5 m,\nnarrower than SMRF's\nSMALLEST element (9 m)",
                xy=(7.2, 2.62), xytext=(20, 2.45), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="black"))
    ax.annotate("the 32–46 m figure the first\nderivation used — the BASE",
                xy=(43, 0.40), xytext=(22, 0.75), fontsize=9, color="grey",
                arrowprops=dict(arrowstyle="->", color="grey"))

    ax.set_xlabel("Width at that height (m) — 2 × inscribed radius")
    ax.set_ylabel("Height above marsh datum (m)")
    ax.set_title("A levee is a wedge: opening cuts at the height in question\n"
                  "Vertical lines = span of SMRF's diamond element at cell = 3 m")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9, loc="upper right")
    fig.tight_layout()
    save(fig, "fig03_embankment_profile.png")


# ======================================================================
# fig04 -- window sweep result, against the vendor reference stated
# ======================================================================
def fig04_window_sweep():
    win = [3, 6, 12, 25, 50]
    above = [1.612, 0.797, 0.679, 0.688, 0.688]
    vendor = 2.369

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    ax.axhline(vendor, color="#2b5d9e", lw=2, ls="--",
               label=f"vendor crest height = {vendor:.3f} m (the reference)")
    ax.plot(win, above, "o-", lw=2, color="#b5423a",
            label="crest height retained, this pipeline")
    ax.fill_between(win, above, vendor, alpha=0.12, color="#b5423a")

    ax.annotate("w=25 and w=50 are BYTE-IDENTICAL\n"
                "(convergence: SE already exceeds every real feature)",
                xy=(37, 0.688), xytext=(9, 0.30), fontsize=8.5,
                arrowprops=dict(arrowstyle="->", color="grey"))
    ax.annotate(f"best case still loses 0.757 m",
                xy=(3, 1.612), xytext=(3.4, 2.02), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="black"))

    ax.set_xscale("log")
    ax.set_xticks(win)
    ax.set_xticklabels([str(w) for w in win])
    ax.set_xlabel("SMRF window (m)")
    ax.set_ylabel("Crest height above marsh datum (m)")
    ax.set_ylim(0, 2.7)
    ax.set_title("No window preserves the crown at cell = 3 m\n"
                  "Reference: median height of the SAME 706 crest cells in "
                  "the vendor surface")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9, loc="center right")
    fig.tight_layout()
    save(fig, "fig04_window_sweep.png")


# ======================================================================
# fig05 -- agreement with vendor, BY REGION (the pooled number misleads)
# ======================================================================
def fig05_qc_regions():
    """Histogram only. This used to carry a difference MAP in a left panel
    as well, but fig08 now shows the same data full-size on a hillshade
    base -- printing both would show one dataset twice at two sizes, and
    the small version was the weaker of the two."""
    v, ext, _ = load(VENDOR)
    m, _, _ = load(FINAL)
    a05, _, _ = load(DEM / "count_allret_0.5m.tif", False)
    a3 = agg(np.nan_to_num(a05), 6)
    d = m - v
    marsh_z = float(np.nanmedian(v))
    water = a3 == 0
    crest = np.nan_to_num(v, nan=-9999) > (marsh_z + 2.0)
    marsh = ~water & ~crest

    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    bins = np.linspace(-0.5, 0.5, 121)
    for mask, lbl, col in ((marsh, "marsh - 94.6% of tile, RMSE 0.081 m", "#4c9f70"),
                            (water, "water - 4.7%, both surfaces interpolated", "#2b5d9e"),
                            (crest, "crest - 0.6%, RMSE 0.963 m", "#b5423a")):
        vals = d[mask & np.isfinite(d)]
        ax.hist(vals, bins=bins, density=True, histtype="step", lw=2,
                color=col, label=lbl)
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel("delivered minus vendor (m)")
    ax.set_ylabel("density")
    ax.set_title("Three populations, not one\n"
                 "The pooled RMSE (0.111 m) describes none of them. "
                 "Agreement between two\nclassifications, NOT accuracy: "
                 "no external control exists on this tile.\n"
                 "For where these differences fall spatially, see Figure 6.",
                 fontsize=10.5)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    save(fig, "fig05_qc_regions.png")


# ======================================================================
# fig06 -- the delivered surface
# ======================================================================
def fig06_final_surface():
    hs = DEM / "hs_w3_s0.05_t0.15.tif"
    if not hs.exists():
        subprocess.run([str(ENV / "Library" / "bin" / "gdaldem.exe"),
                        "hillshade", "-z", "20", "-az", "315", "-alt", "45",
                        str(FINAL), str(hs)],
                       capture_output=True, text=True, env=env())
    h, ext, _ = load(hs, False)
    z, _, _ = load(FINAL)

    fig, ax = plt.subplots(figsize=(9.0, 8.4))
    ax.imshow(h, extent=ext, origin="upper", cmap="gray", alpha=1.0)
    im = ax.imshow(z, extent=ext, origin="upper", cmap="terrain",
                   alpha=0.55, vmin=2.0, vmax=5.0)
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03, extend="both")
    cb.set_label("Elevation (m, NAVD88 / Geoid12B)")
    ax.set_xlabel("Easting (m, EPSG:6350)")
    ax.set_ylabel("Northing (m, EPSG:6350)")
    ax.set_title("Bare-earth DEM, 3 m — S-151 at L-67A / Miami Canal\n"
                  "cell 3.0 m · window 3.0 m · slope 0.05 · threshold 0.15 m\n"
                  "Hillshade uses 20× vertical exaggeration: relief is 2.81 m "
                  "across 1 km and is invisible at 1×",
                  fontsize=11)
    add_scalebar(ax, 200)
    add_north_arrow(ax)
    fig.tight_layout()
    save(fig, "fig06_final_surface.png")


# ======================================================================
# fig07 -- plain grayscale hillshade of the delivered surface.
# The base map the other overlays are drawn on. Project one carries one
# of these per surface; the Everglades set had none, which left it
# heavier on analytical plots than on maps.
# ======================================================================
def fig07_hillshade():
    h, ext, _ = load(DEM / "hs_w3_s0.05_t0.15.tif", False)
    fig, ax = plt.subplots(figsize=(9.0, 8.6))
    ax.imshow(h, extent=ext, origin="upper", cmap="gray", vmin=0, vmax=255)
    ax.set_xlabel("Easting (m, EPSG:6350)")
    ax.set_ylabel("Northing (m, EPSG:6350)")
    ax.set_title("Bare-earth hillshade, delivered surface\n"
                 "cell 3.0 m | window 3.0 m | slope 0.05 | threshold 0.15 m\n"
                 "Illumination 315 deg az, 40 deg alt, 20x z-factor "
                 "(relief is 2.81 m across 1 km and is flat at 1x)",
                 fontsize=10.5)
    add_scalebar(ax, 200)
    add_north_arrow(ax)
    mark_s151(ax, color="black")
    fig.tight_layout()
    save(fig, "fig07_hillshade.png")


# ======================================================================
# fig08 -- WHERE the two classifications disagree, not merely by how
# much. Sign convention is DELIVERED minus VENDOR, matching section 6,
# the qc_vs_vendor dump and fig05. Inverting it for one figure would put
# a map beside a table it appears to contradict.
# ======================================================================
def fig08_difference_map():
    v, ext, _ = load(VENDOR)
    m, _, _ = load(FINAL)
    h, _, _ = load(DEM / "hs_w3_s0.05_t0.15.tif", False)
    d = m - v

    fig, ax = plt.subplots(figsize=(9.4, 8.6))
    ax.imshow(h, extent=ext, origin="upper", cmap="gray", vmin=0, vmax=255)
    lim = 0.5
    im = ax.imshow(np.where(np.abs(d) > 0.02, d, np.nan), extent=ext,
                   origin="upper", cmap="RdBu_r", vmin=-lim, vmax=lim,
                   alpha=0.80)
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03, extend="both")
    cb.set_label("delivered minus vendor (m)")
    ax.set_xlabel("Easting (m, EPSG:6350)")
    ax.set_ylabel("Northing (m, EPSG:6350)")
    # Caption checked against the data before being written. An earlier
    # draft said the levee "reads as a continuous blue line", which the
    # image does not show: 58.1% of crest cells are blue and 0.0% are red,
    # but only 40.5% of blue cells sit ON the crest -- most are on the
    # steep canal and bank flanks (section 7.2). Both halves matter and
    # the first draft got both wrong.
    ax.set_title("Where the two classifications disagree\n"
                 "Blue = this surface below the vendor's. 58% of crest "
                 "cells are blue and none are red\n(the crown truncation); "
                 "most blue lies OFF the crest, on steep canal and bank "
                 "flanks.\nCells within 0.02 m are unshaded.", fontsize=10)
    add_scalebar(ax, 200)
    add_north_arrow(ax)
    fig.tight_layout()
    save(fig, "fig08_difference_map.png")


# ======================================================================
# fig09 -- ground-return density at the DELIVERED cell size. fig01 shows
# density too, but as one of three panels sharing a frame with
# all-returns; this asks the narrower question of how many ground
# observations actually underlie each 3 m cell that was shipped.
# ======================================================================
def fig09_density_3m():
    g05, _, _ = load(DEM / "count_ground_0.5m.tif", False)
    g3 = agg(np.nan_to_num(g05), 6) / 9.0          # counts -> pts per m2
    h, ext, _ = load(DEM / "hs_w3_s0.05_t0.15.tif", False)

    fig, ax = plt.subplots(figsize=(9.4, 8.6))
    ax.imshow(h, extent=ext, origin="upper", cmap="gray", vmin=0, vmax=255)
    im = ax.imshow(np.where(g3 > 0, g3, np.nan), extent=ext, origin="upper",
                   cmap="viridis", vmin=0, vmax=4, alpha=0.78)
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.03, extend="max")
    cb.set_label("ground returns per m$^2$ (3 m cell, binmode count)")

    empty = 100.0 * float(np.mean(g3 == 0))
    ax.set_xlabel("Easting (m, EPSG:6350)")
    ax.set_ylabel("Northing (m, EPSG:6350)")
    ax.set_title("Ground-return density at the delivered 3 m cell\n"
                 f"Mean 1.26 pts/m$^2$; {empty:.2f}% of cells hold no ground "
                 "return at all\n(unshaded = no ground observation; the "
                 "surface there is interpolated)", fontsize=10.5)
    add_scalebar(ax, 200)
    add_north_arrow(ax)
    fig.tight_layout()
    save(fig, "fig09_density_3m.png")


# ======================================================================
# fig10 -- stage-area hypsometry. The analysis this terrain supports,
# and the one D8 cannot replace: a threshold on the elevation
# distribution, with no gradient assumption anywhere in it.
# ======================================================================
def fig10_hypsometry():
    rows = np.load(DEM / "hypsometry.npy")
    stage, area_ha, pct, rate = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]

    fig, ax = plt.subplots(figsize=(9.0, 6.0))
    ax.plot(stage, pct, lw=2.4, color="#2b5d9e", label="area inundated")
    ax.set_xlabel("Water surface elevation (m, NAVD88 / Geoid12B)")
    ax.set_ylabel("Share of tile inundated (%)", color="#2b5d9e")
    ax.tick_params(axis="y", labelcolor="#2b5d9e")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)

    ax2 = ax.twinx()
    ok = np.isfinite(rate)
    ax2.plot(stage[ok], rate[ok], lw=1.6, ls="--", color="#b5423a",
             label="sensitivity")
    ax2.set_ylabel("Hectares flooded per additional cm of stage",
                   color="#b5423a")
    ax2.tick_params(axis="y", labelcolor="#b5423a")

    pk = np.nanargmax(np.where(ok, rate, np.nan))
    ax2.annotate(f"peak sensitivity {stage[pk]:.2f} m\n"
                 f"{rate[pk]:.1f} ha per cm",
                 xy=(stage[pk], rate[pk]), xytext=(stage[pk] + 0.35,
                                                    rate[pk] * 0.8),
                 fontsize=9, color="#b5423a",
                 arrowprops=dict(arrowstyle="->", color="#b5423a"))
    ax.axvspan(2.30, 2.60, color="#2b5d9e", alpha=0.08)
    # Anchor on the BLUE curve, well clear of the red sensitivity trace.
    # An earlier placement put the arrowhead visually on the red curve
    # while the text described the blue one.
    ax.annotate("5% to 94% inundated\nacross 30 cm of stage",
                xy=(2.58, 91), xytext=(2.95, 68), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#2b5d9e"),
                color="#2b5d9e")

    ax.set_title("Stage-area hypsometry\n"
                 "No flow routing: this is a threshold on the elevation "
                 "distribution, which\nis well constrained even where local "
                 "gradients are not (see section 8).\n"
                 "Elevations are NAVD88/Geoid12B and are NOT tied to a "
                 "gauge datum.", fontsize=10.5)
    lines = ax.get_lines() + ax2.get_lines()
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left",
              fontsize=9)
    fig.tight_layout()
    save(fig, "fig10_hypsometry.png")


# ======================================================================
# fig11 -- levee crest profile, on the VENDOR surface. Our own truncates
# the crown by a median 0.911 m, which is the very quantity this plots.
# ======================================================================
def fig11_crest_profile():
    prof = np.load(DEM / "crest_profile.npy")
    t, e = prof[:, 0], prof[:, 1]
    v, _, _ = load(VENDOR)
    marsh_z = float(np.nanmedian(v))

    fig, ax = plt.subplots(figsize=(9.4, 5.6))
    ax.plot(t, e, lw=2.0, color="#6b4c9a", marker="o", ms=3.5,
            label="crest elevation (max per 15 m bin)")
    ax.axhline(marsh_z, color="#4c9f70", ls="--", lw=1.4,
               label=f"marsh datum {marsh_z:.2f} m")
    ax.fill_between(t, marsh_z, e, color="#6b4c9a", alpha=0.12)

    order = np.argsort(e)[:3]
    for i in order:
        ax.plot(t[i], e[i], marker="v", ms=11, color="#b5423a", zorder=5)
        ax.annotate(f"{e[i]:.2f} m", xy=(t[i], e[i]),
                    xytext=(0, -20), textcoords="offset points",
                    ha="center", fontsize=8.5, color="#b5423a")
    ax.plot([], [], marker="v", ls="", color="#b5423a",
            label="three lowest bins (first to overtop)")

    ax.set_xlabel("Distance along levee axis (m, bearing 20 deg)")
    ax.set_ylabel("Elevation (m, NAVD88 / Geoid12B)")
    ax.set_title("L-67A levee crest profile - VENDOR surface\n"
                 "Computed on the vendor's classification, NOT this "
                 "project's: ours truncates\nthe crown by a median 0.911 m "
                 "(section 7.1), which is exactly what this measures.\n"
                 "Crest varies 0.72 m along its length; read as freeboard "
                 "relative to itself.", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9, loc="lower right")
    fig.tight_layout()
    save(fig, "fig11_crest_profile.png")


if __name__ == "__main__":
    print("rendering figures to output/figures/ ...")
    fig01_coverage()
    fig02_cell_sweep()
    fig03_embankment_profile()
    fig04_window_sweep()
    fig05_qc_regions()
    fig06_final_surface()
    fig07_hillshade()
    fig08_difference_map()
    fig09_density_3m()
    fig10_hypsometry()
    fig11_crest_profile()
    print("done")
