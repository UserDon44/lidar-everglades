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

# ----------------------------------------------------------------------
# ENVIRONMENT BOOTSTRAP -- must run BEFORE importing matplotlib/rasterio.
#
# Running this env's python without an activated shell fails at import
# with EXIT CODE 127 AND NO TRACEBACK: it is a DLL resolution failure,
# not a Python exception, so nothing is printed and the script simply
# vanishes. Python 3.8+ on Windows no longer searches PATH for extension
# module DLLs, so os.add_dll_directory is required -- setting PATH alone
# is not enough. Documented in the predecessor project after the same
# symptom cost real debugging time.
# ----------------------------------------------------------------------
_ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
for _d in (_ENV / "Library" / "bin", _ENV / "Library" / "mingw-w64" / "bin",
            _ENV / "Scripts", _ENV):
    if _d.is_dir():
        try:
            os.add_dll_directory(str(_d))
        except (AttributeError, OSError):
            pass
os.environ["PATH"] = os.pathsep.join(
    [str(_ENV), str(_ENV / "Library" / "bin"), str(_ENV / "Scripts"),
     os.environ.get("PATH", "")])
os.environ.setdefault("GDAL_DATA", str(_ENV / "Library" / "share" / "gdal"))
os.environ.setdefault("PROJ_LIB", str(_ENV / "Library" / "share" / "proj"))

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
    axes[0].set_title("All returns — 16.89 pts/m² mean\n(QL1-class density)")

    im = axes[1].imshow(g3 / 9.0, extent=ext, origin="upper", cmap="magma",
                        vmin=0, vmax=6)
    cb = plt.colorbar(im, ax=axes[1], fraction=0.046, pad=0.03, extend="max")
    cb.set_label("ground returns per m²")
    axes[1].set_title("Ground returns — 1.26 pts/m² mean\n"
                       "7.4% of points; the operative constraint")

    # Void classes: the finding is that 'void' is two different failures.
    cls = np.zeros(a3.shape)
    cls[(a3 > 0) & (g3 == 0)] = 1     # vegetation blocked
    cls[a3 == 0] = 2                  # water dropout
    cmap = matplotlib.colors.ListedColormap(["#e8e8e8", "#4c9f70", "#2b5d9e"])
    axes[2].imshow(cls, extent=ext, origin="upper", cmap=cmap, vmin=0, vmax=2)
    axes[2].set_title("Two distinct void classes at 3 m\n"
                       "(vegetation is recoverable; water is not)")
    axes[2].legend(handles=[
        Line2D([], [], marker="s", ls="", ms=10, mfc="#e8e8e8", mec="grey",
               label="ground present — 52.9%"),
        Line2D([], [], marker="s", ls="", ms=10, mfc="#4c9f70", mec="none",
               label="returns, none ground — 41.0%"),
        Line2D([], [], marker="s", ls="", ms=10, mfc="#2b5d9e", mec="none",
               label="no returns at all — 6.1%"),
    ], loc="lower left", fontsize=8, framealpha=0.9)

    for ax in axes:
        ax.set_xlabel("Easting (m, EPSG:6350)")
        ax.tick_params(labelsize=8)
        add_scalebar(ax, 200)
        add_north_arrow(ax)
    axes[0].set_ylabel("Northing (m, EPSG:6350)")
    fig.suptitle("Coverage, not density, is the binding constraint at S-151",
                 fontsize=13)
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
    v, ext, _ = load(VENDOR)
    m, _, _ = load(FINAL)
    a05, _, _ = load(DEM / "count_allret_0.5m.tif", False)
    a3 = agg(np.nan_to_num(a05), 6)
    d = m - v
    marsh_z = float(np.nanmedian(v))
    water = a3 == 0
    crest = np.nan_to_num(v, nan=-9999) > (marsh_z + 2.0)
    marsh = ~water & ~crest

    fig, axes = plt.subplots(1, 2, figsize=(14.5, 6.0),
                              gridspec_kw={"width_ratios": [1.05, 1]})

    lim = 0.5
    im = axes[0].imshow(d, extent=ext, origin="upper", cmap="RdBu_r",
                        vmin=-lim, vmax=lim)
    cb = plt.colorbar(im, ax=axes[0], fraction=0.046, pad=0.03, extend="both")
    cb.set_label("this surface − vendor (m)")
    axes[0].set_xlabel("Easting (m, EPSG:6350)")
    axes[0].set_ylabel("Northing (m, EPSG:6350)")
    axes[0].set_title("Difference from the vendor ground surface")
    add_scalebar(axes[0], 200)
    add_north_arrow(axes[0])

    bins = np.linspace(-0.5, 0.5, 121)
    for mask, lbl, col in ((marsh, "marsh — 94.6%, RMSE 0.081 m", "#4c9f70"),
                            (water, "water — 4.7%, both interpolated", "#2b5d9e"),
                            (crest, "crest — 0.6%, RMSE 0.963 m", "#b5423a")):
        vals = d[mask & np.isfinite(d)]
        axes[1].hist(vals, bins=bins, density=True, histtype="step", lw=2,
                     color=col, label=lbl)
    axes[1].axvline(0, color="grey", lw=0.8)
    axes[1].set_xlabel("this surface − vendor (m)")
    axes[1].set_ylabel("density")
    axes[1].set_title("Three populations, not one\n"
                       "the pooled RMSE (0.111 m) describes none of them")
    axes[1].legend(fontsize=9)
    axes[1].grid(alpha=0.3)

    fig.suptitle("Agreement between two independent classifications — "
                 "NOT an accuracy assessment (no external control exists)",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
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


if __name__ == "__main__":
    print("rendering figures to output/figures/ ...")
    fig01_coverage()
    fig02_cell_sweep()
    fig03_embankment_profile()
    fig04_window_sweep()
    fig05_qc_regions()
    fig06_final_surface()
    print("done")
