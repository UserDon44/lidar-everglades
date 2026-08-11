#!/usr/bin/env python3
"""
Is there a systematic vertical offset between the two flight lines?

WHY THIS IS WORTH MEASURING
===========================
The tile is two swaths -- PointSourceId 34012 (north) and 34101 (south)
-- flown 19.8 hours apart (GPS time gap 71,229 s). The predecessor
project measured a systematic +0.124 ft (38 mm) offset between swaths on
a SINGLE-DAY collection. An overnight gap is a stronger candidate still:
GNSS constellation and atmospheric conditions change, and in a managed
wetland the water level itself can move between passes.

It also bears directly on a published number. The marsh agreement figure
of 0.081 m RMSE is presented as disagreement between two
CLASSIFICATIONS. If the two swaths disagree with each other vertically,
part of that spread is inter-swath disagreement in the SOURCE DATA,
present in both surfaces, and not attributable to classification at all.

METHOD, AND WHY NOT SMRF
========================
The obvious approach -- classify each swath separately and difference the
results -- is INVALID here. This project established that filters.smrf
and filters.elm anchor their internal grids to the extent of the points
they receive, so two swaths with different extents get different grid
phase, and a 1.5 m extent shift alone changes 93% of cells. That
confound would swamp a 40 mm offset.

So SMRF is avoided entirely. The VENDOR's class-2 points are split by
PointSourceId and rasterized with writers.gdal on an EXPLICIT, identical
grid (origin/width/height fixed). Rasterization has no extent-derived
phase, so the two products are directly comparable by construction, and
the question asked is the right one anyway: do the two passes agree in
ELEVATION, independent of anyone's classification?

Cells are compared only where BOTH swaths actually observed ground --
count > 0 in each -- so no comparison rests on IDW fill.

PARAMETERS
==========
  swaths     : PointSourceId 34012 (north), 34101 (south)
  points     : vendor Classification[2:2] only
  grid       : 333x333 @ 3 m, origin 1557000/456000 (the project grid)
  comparison : cells with ground count > 0 in BOTH swaths
  regions    : marsh vs crest reported separately, since the crest has
               ~6x the ground return density and would otherwise
               dominate any pooled spread
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import Dump  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"
VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"

XMIN, YMIN, RES, N = 1557000.0, 456000.0, 3.0, 333
SWATHS = [34012, 34101]
CREST_ABOVE = 2.0


def env():
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([str(ENV), str(ENV / "Library" / "bin"),
                                  str(ENV / "Scripts"), e.get("PATH", "")])
    e["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    e["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")
    return e


def build(psid, kind):
    """Per-swath vendor-ground raster on the FIXED grid."""
    out = DEM / f"swath{psid}_{kind}_3m.tif"
    if out.exists():
        return out
    w = {"type": "writers.gdal",
         "filename": str(out).replace("\\", "/"),
         "resolution": RES,
         "output_type": "idw" if kind == "z" else "count",
         "origin_x": XMIN, "origin_y": YMIN, "width": N, "height": N,
         "nodata": -9999 if kind == "z" else 0}
    if kind == "z":
        w["window_size"] = 0        # no fallback fill: measured cells only
    else:
        w["binmode"] = True
    stages = [
        {"type": "readers.las", "filename": str(TILE).replace("\\", "/")},
        {"type": "filters.range", "limits": "Classification[2:2]"},
        {"type": "filters.range",
         "limits": f"PointSourceId[{psid}:{psid}]"},
        w,
    ]
    p = ROOT / "scripts" / "pipelines" / f"pipe_swath{psid}_{kind}.json"
    p.write_text(json.dumps({"pipeline": stages}, indent=2))
    r = subprocess.run([str(ENV / "Library" / "bin" / "pdal.exe"), "pipeline",
                        str(p)], capture_output=True, text=True, env=env())
    if r.returncode != 0:
        print(r.stderr[-1500:], file=sys.stderr)
        raise SystemExit(f"pdal failed for swath {psid} {kind}")
    return out


def load(p, to_nan=True):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if to_nan and ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a


def main():
    with Dump(
        "swath_offset",
        "Vertical offset between the two flight lines, measured on vendor "
        "ground points",
        {
            "swaths": "PointSourceId 34012 (north) and 34101 (south)",
            "time gap": "71,229 s = 19.8 hours between passes",
            "points": "vendor Classification[2:2] only",
            "grid": f"{N}x{N} @ {RES} m, origin {XMIN}/{YMIN} (explicit)",
            "window_size": "0 -- no IDW fallback, so every compared cell was "
                           "actually observed by that swath",
            "compared cells": "ground count > 0 in BOTH swaths",
            "why not per-swath SMRF": "smrf/elm anchor their grids to the "
                                      "input extent; two swaths have "
                                      "different extents, and a 1.5 m extent "
                                      "shift alone changes 93% of cells",
            "regions": "marsh and crest reported separately; the crest has "
                       "~6x the ground density and would dominate a pooled "
                       "spread",
            "bears on": "the 0.081 m marsh agreement figure, which is "
                        "presented as classification disagreement",
        },
    ):
        zs, cs = {}, {}
        for pid in SWATHS:
            zs[pid] = load(build(pid, "z"))
            cs[pid] = load(build(pid, "count"), to_nan=False)
            cs[pid] = np.nan_to_num(cs[pid])
            print(f"swath {pid}: {int((cs[pid] > 0).sum()):,} cells with "
                  f"ground returns")

        a, b = SWATHS
        both = (cs[a] > 0) & (cs[b] > 0) & np.isfinite(zs[a]) & np.isfinite(zs[b])
        d = zs[b] - zs[a]            # south minus north

        v = load(VENDOR)
        marsh_z = float(np.nanmedian(v))
        crest = np.nan_to_num(v, nan=-9999) > (marsh_z + CREST_ABOVE)

        print(f"\noverlap: {int(both.sum()):,} cells observed by BOTH swaths "
              f"({100*both.sum()/both.size:.1f}% of tile)")
        rows, cols = np.where(both)
        if rows.size:
            print(f"  northing range of overlap: "
                  f"{YMIN + (N-1-rows.max())*RES:.0f} to "
                  f"{YMIN + (N-1-rows.min())*RES:.0f} m")

        print("\n" + "=" * 78)
        print(f"ELEVATION DIFFERENCE, swath {b} (south) minus {a} (north)")
        print("=" * 78)
        print(f"{'region':<22} {'cells':>9} {'mean':>9} {'median':>9} "
              f"{'std':>8} {'RMSE':>8} {'t':>8}")
        print("-" * 78)
        for name, m in (("all overlap", both),
                         ("marsh only", both & ~crest),
                         ("crest only", both & crest)):
            dd = d[m]
            dd = dd[np.isfinite(dd)]
            if dd.size < 10:
                print(f"{name:<22} {dd.size:>9,}  (too few cells)")
                continue
            se = dd.std(ddof=1) / np.sqrt(dd.size)
            t = dd.mean() / se if se > 0 else np.nan
            print(f"{name:<22} {dd.size:>9,} {dd.mean():>+9.4f} "
                  f"{np.median(dd):>+9.4f} {dd.std(ddof=1):>8.4f} "
                  f"{np.sqrt((dd**2).mean()):>8.4f} {t:>+8.1f}")
        print("=" * 78)

        dm = d[both & ~crest]
        dm = dm[np.isfinite(dm)]
        mean_off = float(dm.mean())
        print(f"""
INTERPRETATION

  Marsh mean offset {mean_off:+.4f} m between passes flown 19.8 hours apart.

  With {dm.size:,} cells the t-statistic is large for almost any offset, so
  significance is not the question -- magnitude is. Compare against:

    published marsh agreement (this surface vs vendor) : 0.0807 m RMSE
    intrinsic SMRF grid-phase sensitivity              : 0.055 m
    inter-swath offset measured here                   : {abs(mean_off):.4f} m mean,
                                                         {np.sqrt((dm**2).mean()):.4f} m RMSE

  An inter-swath disagreement is present in BOTH the vendor surface and
  this one, since both are built from all returns regardless of swath. It
  is therefore a component of the 0.0807 m figure that is NOT
  classification disagreement, and the memo should say so rather than
  attributing the whole spread to classification.
""")


if __name__ == "__main__":
    main()
