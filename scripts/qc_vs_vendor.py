#!/usr/bin/env python3
"""
QC the working SMRF surface against the vendor's delivered ground
classification.

WHAT THIS IS AND IS NOT
-----------------------
This measures AGREEMENT between two independent classifications of the
same point cloud. It is NOT an accuracy assessment. There is no external
control on this tile -- no NGS marks were sought or used, and USGS
published no vertical accuracy report for this collection comparable to
the sealed Psomas/Sanborn documents behind project one's San Xavier
tile. Both surfaces could be wrong together and this statistic would not
show it.

Stated plainly because the number looks exactly like an RMSEz and will
be read as one otherwise.

REGIONS
-------
The tile is not homogeneous and a single pooled statistic hides the only
interesting parts. Three disjoint regions, in priority order:

  water   : cells with ZERO returns of any kind (binmode count == 0).
            Both surfaces interpolate across these; neither measured
            anything. Reported separately so interpolated water is never
            counted as terrain agreement.
  crest   : vendor > marsh + CREST_ABOVE. The L-67A levee top, where the
            documented crown truncation lives.
  marsh   : everything else -- the 70%+ of the tile that is flat sawgrass
            and the only region where the two surfaces are both measuring
            real ground.

PARAMETERS
----------
  reference   : dem_VENDOR_3m_aligned.tif  (vendor class-2, aligned grid)
  test        : dem_<TAG>.tif              (default w3_s0.05_t0.15)
  counts      : count_allret_3m_aligned.tif (binmode, all returns)
  marsh datum : median of valid vendor cells
  CREST_ABOVE : 2.0 m  (same mask as measure_window_sweep.py, so the
                numbers here and there refer to the same cells)

binmode is used for the count raster because PDAL's default radius search
inflates counts several-fold -- project one measured ~6x -- which would
mislabel real dropout as covered.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"

VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"
COUNTS = DEM / "count_allret_3m_aligned.tif"
ORIGIN_X, ORIGIN_Y, WIDTH, HEIGHT, RES = 1557000.0, 456000.0, 333, 333, 3.0
CREST_ABOVE = 2.0


def pdal_env():
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([
        str(ENV), str(ENV / "Library" / "bin"), str(ENV / "Scripts"),
        e.get("PATH", "")])
    e["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    e["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")
    return e


def ensure_counts():
    """All-return count on the aligned grid, binmode (true per-cell bins)."""
    if COUNTS.exists():
        return
    pipe = {"pipeline": [
        {"type": "readers.las", "filename": str(TILE).replace("\\", "/")},
        {"type": "writers.gdal",
         "filename": str(COUNTS).replace("\\", "/"),
         "resolution": RES, "output_type": "count", "binmode": True,
         "origin_x": ORIGIN_X, "origin_y": ORIGIN_Y,
         "width": WIDTH, "height": HEIGHT, "nodata": 0}]}
    p = ROOT / "scripts" / "pipelines" / "pipe_count_allret_3m_aligned.json"
    p.write_text(json.dumps(pipe, indent=2))
    print("building all-return count raster (binmode)...")
    r = subprocess.run([str(ENV / "Library" / "bin" / "pdal.exe"),
                        "pipeline", str(p)],
                       capture_output=True, text=True, env=pdal_env())
    if r.returncode != 0:
        print(r.stderr[-1500:], file=sys.stderr)
        raise SystemExit("pdal failed building counts")


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a


def stats(d):
    d = d[np.isfinite(d)]
    if d.size == 0:
        return None
    return {
        "n": d.size,
        "mean": d.mean(), "median": float(np.median(d)),
        "std": d.std(ddof=1), "rmse": float(np.sqrt((d ** 2).mean()),),
        "p16": float(np.percentile(d, 16)), "p84": float(np.percentile(d, 84)),
        "min": d.min(), "max": d.max(),
        "gt15": 100.0 * np.mean(np.abs(d) > 0.15),
        "gt50": 100.0 * np.mean(np.abs(d) > 0.50),
    }


def row(name, s):
    if s is None:
        return f"{name:<28} (no cells)"
    return (f"{name:<28} {s['n']:>8,} {s['mean']:>+8.4f} {s['median']:>+8.4f} "
            f"{s['std']:>7.4f} {s['rmse']:>7.4f} {s['gt15']:>7.2f}% {s['gt50']:>7.2f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="w3_s0.05_t0.15")
    a = ap.parse_args()

    ensure_counts()
    test_path = DEM / f"dem_{a.tag}.tif"
    from dump import Dump
    dump = Dump(
        "qc_vs_vendor",
        "Agreement between the SMRF bare-earth surface and the vendor "
        "ground classification",
        {
            "test surface": f"dem_{a.tag}.tif",
            "reference": VENDOR.name,
            "grid": f"{WIDTH}x{HEIGHT} @ {RES} m, origin {ORIGIN_X}/{ORIGIN_Y}",
            "water region": "cells with ZERO returns (binmode count == 0)",
            "crest region": f"vendor > marsh median + {CREST_ABOVE} m",
            "marsh region": "everything not water and not crest",
            "marsh datum": "median of all valid vendor cells",
            "why regions": "a pooled statistic blends real ground agreement, "
                           "an accepted truncation, and two interpolations "
                           "across unmeasured ground",
            "NOT an accuracy figure": "no external control exists on this "
                                      "tile; this is classification agreement",
        })
    dump.__enter__()
    v = load(VENDOR)
    m = load(test_path)
    cnt = np.nan_to_num(load(COUNTS), nan=0.0)

    marsh_z = float(np.nanmedian(v))
    water = cnt == 0
    crest = np.nan_to_num(v, nan=-9999) > (marsh_z + CREST_ABOVE)
    marsh = ~water & ~crest

    diff = m - v
    valid = np.isfinite(diff)

    print(f"\ntest      : {test_path.name}")
    print(f"reference : {VENDOR.name}")
    print(f"marsh datum : {marsh_z:.3f} m   |   crest mask: vendor > marsh + {CREST_ABOVE} m")
    print(f"\ngrid {v.shape}, {int(valid.sum()):,} of {v.size:,} cells valid in both "
          f"({100*valid.sum()/v.size:.2f}%)")

    print("\nRegions (disjoint, covering the tile):")
    for nm, msk in (("water (0 returns)", water), ("crest (levee top)", crest),
                     ("marsh (everything else)", marsh)):
        print(f"  {nm:<26} {int(msk.sum()):>8,} cells  "
              f"{100*msk.sum()/v.size:>6.2f}%")

    print("\n" + "=" * 96)
    print("Difference from vendor ground surface  (test - vendor), metres")
    print("=" * 96)
    print(f"{'region':<28} {'cells':>8} {'mean':>8} {'median':>8} "
          f"{'std':>7} {'RMSE':>7} {'>0.15m':>8} {'>0.50m':>8}")
    print("-" * 96)
    print(row("ALL (pooled)", stats(diff[valid])))
    print(row("marsh  <- the real number", stats(diff[marsh & valid])))
    print(row("crest  <- truncation lives here", stats(diff[crest & valid])))
    print(row("water  <- both interpolated", stats(diff[water & valid])))
    print("=" * 96)

    s_marsh = stats(diff[marsh & valid])
    s_crest = stats(diff[crest & valid])
    # Published prose states the truncation as a magnitude ("truncated by
    # 0.911 m"), while the table holds it signed. Print both so either
    # phrasing is traceable to this dump.
    print(f"crest truncation magnitude: median {abs(s_crest['median']):.4f} m, "
          f"mean {abs(s_crest['mean']):.4f} m below the vendor surface")
    print(f"""
READING THIS

  The pooled row is the one to distrust. It blends three populations that
  answer different questions -- real ground agreement, a known truncation,
  and two interpolations of nothing.

  marsh RMSE {s_marsh['rmse']:.4f} m is the meaningful agreement figure, and it is
  AGREEMENT between two classifications, not accuracy against control.

  crest mean {s_crest['mean']:+.4f} m is the documented L-67A crown truncation.
  It is negative by construction: the working surface sits below the
  vendor's because SMRF's smallest structuring element is wider than the
  crown. See output/reports/parameter_derivation.md sections 3-3b.
""")


if __name__ == "__main__":
    main()
