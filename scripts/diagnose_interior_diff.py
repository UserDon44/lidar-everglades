#!/usr/bin/env python3
"""
Locate the interior buffered-vs-unbuffered differences.

CONTEXT
-------
The edge-effect measurement's own control failed: cells more than 21 m
from any tile edge changed between the buffered and unbuffered runs, by
up to 1.2 m, which no filter in the pipeline can reach. The first
hypothesis -- that filters.outlier's global mean+3sigma threshold shifts
when neighbour points are added -- was tested by removing that stage
from both runs and REFUTED: the interior difference was unchanged.

This script does not propose a new mechanism. It asks where the
differences physically are, so the next hypothesis is constrained by
data rather than by plausibility.

The table already suggests two distinct populations, which this
separates rather than pools:

  tiny  (|d| <= 0.05 m) on ~39% of cells -- consistent with
        floating-point accumulation order in IDW, since merging five
        files changes the order points arrive in
  large (|d| >  0.05 m) on <0.5% of cells, some over 1 m -- these are
        classification flips and are what actually needs explaining

CANDIDATE the spatial test can confirm or kill: SMRF builds a minimum
surface then INPAINTS its empty cells. Water voids here are large
connected holes (6.07% of the tile, 95.7% of that in clusters over
100 m^2). How a hole is filled depends on the data around it, and
extending the grid changes that data for any hole touching the tile
edge -- which could propagate error far inside along the canal, with no
relation to distance from the edge.

If the large interior differences cluster on or near water, that is the
mechanism. If they are scattered uniformly, it is not.
"""
import numpy as np
import rasterio
from pathlib import Path
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
RES = 3.0
BIG = 0.05


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a


def main():
    u = load(DEM / "dem_noout_w3_s0.05_t0.15.tif")
    b = load(DEM / "dem_noout_w3_buf30_s0.05_t0.15.tif")
    cnt = np.nan_to_num(load(DEM / "count_allret_3m_aligned.tif"), nan=0.0)
    d = b - u

    H, W = u.shape
    rows, cols = np.indices(u.shape)
    dist_edge = np.minimum.reduce([rows, cols, H - 1 - rows, W - 1 - cols]) * RES

    water = cnt == 0
    # Distance from each cell to the nearest no-return (water) cell.
    dist_water = ndimage.distance_transform_edt(~water) * RES

    interior = np.isfinite(d) & (dist_edge >= 21)
    big = interior & (np.abs(d) > BIG)
    tiny = interior & (np.abs(d) > 0) & (np.abs(d) <= BIG)

    print(f"interior cells (>=21 m from edge) : {int(interior.sum()):,}")
    print(f"  differing at all                : {int((interior & (d != 0)).sum()):,} "
          f"({100*(interior & (d != 0)).sum()/interior.sum():.1f}%)")
    print(f"  |d| <= {BIG} m  (tiny)             : {int(tiny.sum()):,}")
    print(f"  |d| >  {BIG} m  (large)            : {int(big.sum()):,} "
          f"({100*big.sum()/interior.sum():.2f}%)")

    print(f"\nTiny population: max |d| = {np.abs(d[tiny]).max():.6f} m, "
          f"RMS = {np.sqrt((d[tiny]**2).mean()):.6f} m")
    print("  (consistent with float accumulation order, not classification)")

    print("\n" + "=" * 74)
    print("LARGE interior differences vs. distance to nearest no-return cell")
    print("=" * 74)
    print(f"{'distance to water':<22} {'all interior':>14} {'large-diff':>12} "
          f"{'enrichment':>12}")
    print("-" * 74)
    bands = [(0, 3), (3, 9), (9, 21), (21, 51), (51, 101), (101, 10_000)]
    base_rate = big.sum() / interior.sum()
    for lo, hi in bands:
        m = interior & (dist_water >= lo) & (dist_water < hi)
        if m.sum() == 0:
            continue
        mb = big & (dist_water >= lo) & (dist_water < hi)
        rate = mb.sum() / m.sum()
        lbl = f"{lo}-{hi} m" if hi < 10_000 else f">{lo} m"
        print(f"{lbl:<22} {int(m.sum()):>14,} {int(mb.sum()):>12,} "
              f"{rate/base_rate:>11.2f}x")
    print("=" * 74)

    frac_near = big[dist_water <= 9].sum() / max(big.sum(), 1)
    print(f"""
  {100*frac_near:.1f}% of large interior differences lie within 9 m of a
  no-return cell, against a base rate of
  {100*interior[dist_water <= 9].sum()/interior.sum():.1f}% of interior area.

  Enrichment far above 1.0x in the near-water bands supports the
  inpainting mechanism. Enrichment near 1.0x everywhere kills it and the
  cause is elsewhere.
""")


if __name__ == "__main__":
    main()
