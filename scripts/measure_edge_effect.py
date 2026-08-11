#!/usr/bin/env python3
"""
Quantify the tile-edge classification/interpolation effect.

METHOD, AND WHY IT DIFFERS FROM THE PRIOR PROJECT'S
---------------------------------------------------
The prior project measured seams as an elevation STEP across the shared
boundary between two abutting tiles, because abutting tiles share no
area and there is nothing to difference.

Here a stronger measurement is available: build the SAME tile twice --
once in isolation, once with a margin of neighbour points included in
classification and the RASTER cropped back afterwards -- and difference
them. That difference IS the edge effect, cell for cell, with no
pseudo-seam baseline needed and no assumption that the two sides of a
boundary should agree.

Reported as a function of distance from the nearest tile edge, because
the whole claim under test is that the effect is confined to a narrow
band. Two reaches bound it:

    SMRF classification : ceil(window / cell) cells = 1 cell = 3 m
    IDW interpolation   : writers.gdal window_size (6) * res = 18 m

So differences should be confined within ~21 m and be essentially zero
beyond. If they are not, something other than the edge is changing and
the buffered run is not a valid comparison.

PARAMETERS
----------
  unbuffered : dem_w3_s0.05_t0.15.tif
  buffered   : dem_w3_buf30_s0.05_t0.15.tif  (30 m margin, > 21 m reach)
  both on the identical 333x333 grid at 3 m; the buffered raster is
  clipped with gdal_translate -srcwin so its grid is bit-identical by
  construction rather than by resampling.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
RES = 3.0

BINS = [0, 3, 6, 9, 12, 15, 18, 21, 30, 60, 120, 10_000]


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a, ds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unbuffered", default="w3_s0.05_t0.15")
    ap.add_argument("--buffered", default="w3_buf30_s0.05_t0.15")
    a = ap.parse_args()

    pu = DEM / f"dem_{a.unbuffered}.tif"
    pb = DEM / f"dem_{a.buffered}.tif"
    for p in (pu, pb):
        if not p.exists():
            raise SystemExit(f"missing {p.name}")

    u, dsu = load(pu)
    b, dsb = load(pb)
    if u.shape != b.shape:
        raise SystemExit(f"grid mismatch {u.shape} vs {b.shape}")
    if dsu.bounds != dsb.bounds:
        raise SystemExit(f"bounds mismatch {dsu.bounds} vs {dsb.bounds}")

    print(f"unbuffered : {pu.name}")
    print(f"buffered   : {pb.name}")
    print(f"grid {u.shape}, bounds identical, res {dsu.res[0]} m\n")

    d = b - u
    rows, cols = np.indices(u.shape)
    H, W = u.shape
    # Distance in metres from the nearest tile edge (cell centre basis).
    dist = np.minimum.reduce([rows, cols, H - 1 - rows, W - 1 - cols]) * RES

    finite = np.isfinite(d)
    print(f"cells differing at all : {int(np.sum(finite & (d != 0))):,} "
          f"of {int(finite.sum()):,} "
          f"({100*np.sum(finite & (d != 0))/finite.sum():.2f}%)\n")

    print("=" * 84)
    print("Buffered minus unbuffered, by distance from nearest tile edge")
    print("=" * 84)
    print(f"{'band (m)':<12} {'cells':>8} {'mean':>9} {'RMS':>9} "
          f"{'max|d|':>9} {'>0.05m':>8} {'>0.15m':>8}")
    print("-" * 84)
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = finite & (dist >= lo) & (dist < hi)
        n = int(m.sum())
        if n == 0:
            continue
        dd = d[m]
        lbl = f"{lo}-{hi}" if hi < 10_000 else f">{lo}"
        print(f"{lbl:<12} {n:>8,} {dd.mean():>+9.4f} "
              f"{np.sqrt((dd**2).mean()):>9.4f} {np.abs(dd).max():>9.4f} "
              f"{100*np.mean(np.abs(dd) > 0.05):>7.2f}% "
              f"{100*np.mean(np.abs(dd) > 0.15):>7.2f}%")
    print("=" * 84)

    inner = finite & (dist >= 21)
    outer = finite & (dist < 21)
    print(f"""
SUMMARY

  within 21 m of an edge : {int(outer.sum()):,} cells ({100*outer.sum()/finite.sum():.1f}% of tile)
      RMS change {np.sqrt((d[outer]**2).mean()):.4f} m,  max |change| {np.abs(d[outer]).max():.4f} m
  beyond 21 m           : {int(inner.sum()):,} cells
      RMS change {np.sqrt((d[inner]**2).mean()):.4f} m,  max |change| {np.abs(d[inner]).max():.4f} m

  The interior figure is the control. It should be at or near zero: the
  buffer cannot legitimately change cells further from the edge than the
  filters can reach. A non-trivial interior change means the comparison
  is contaminated and the edge numbers cannot be trusted on their own.
""")


if __name__ == "__main__":
    main()
