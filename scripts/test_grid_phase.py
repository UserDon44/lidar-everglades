#!/usr/bin/env python3
"""
Test whether SMRF/ELM results depend on the INPUT DATA EXTENT.

WHY
---
Two hypotheses for the failed edge-effect control have been refuted:

  1. filters.outlier's global mean+3sigma threshold shifting when
     neighbour points are added -- removing the stage changed nothing.
  2. SMRF inpainting across large water voids -- large interior
     differences show no overall enrichment near no-return cells.

A third remains, and it would invalidate the buffered-vs-unbuffered
comparison entirely rather than merely complicating it: PDAL's
filters.smrf and filters.elm build their internal rasters from the
extent of the points they receive. Neither takes an origin parameter.
Adding a 30 m margin moves the data's minimum corner to an arbitrary
sub-cell phase, so every internal cell boundary shifts and any point
near a cell edge can land in a different cell -- tile-wide, with no
relation to distance from the tile boundary.

THE TEST
--------
Isolate extent from buffering. Run the UNBUFFERED pipeline twice, the
second time cropping away a thin strip on the WEST edge only. No
neighbour data, no buffer, and the only thing that changes is where the
data's bounding box starts.

  A : plain unbuffered
  B : unbuffered, points with X < XMIN + SHIFT removed

SHIFT = 1.5 m = half an SMRF cell, chosen to maximally displace the grid
phase. Then compare A and B over cells FAR from the removed strip
(X > XMIN + 200 m). Those cells contain identical points in both runs.

  If they are identical      -> grid phase is not the mechanism.
  If they differ tile-wide   -> confirmed, and the buffered comparison
                                can never be clean, because a buffer
                                necessarily changes the extent.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
PIPE_DIR = ROOT / "scripts" / "pipelines"
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"

XMIN, YMIN, XMAX, YMAX = 1557000.0, 456000.0, 1558000.0, 457000.0
RES = 3.0
SHIFT = 1.5
FAR = 200.0


def pdal_env():
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([str(ENV), str(ENV / "Library" / "bin"),
                                  str(ENV / "Scripts"), e.get("PATH", "")])
    e["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    e["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")
    return e


def build(tag, crop_xmin=None):
    out = DEM / f"dem_{tag}.tif"
    if out.exists():
        print(f"  {tag}: exists")
        return out
    stages = [{"type": "readers.las", "filename": str(TILE).replace("\\", "/")}]
    if crop_xmin is not None:
        stages.append({"type": "filters.crop",
                       "bounds": f"([{crop_xmin},{XMAX}],[{YMIN},{YMAX}])"})
    stages += [
        {"type": "filters.assign", "assignment": "Classification[:]=0"},
        {"type": "filters.elm", "cell": 10.0, "threshold": 1.0},
        {"type": "filters.smrf", "cell": 3.0, "window": 3.0, "slope": 0.05,
         "threshold": 0.15, "scalar": 1.25, "ignore": "Classification[7:7]"},
        {"type": "filters.range", "limits": "Classification[2:2]"},
        {"type": "writers.gdal", "filename": str(out).replace("\\", "/"),
         "resolution": RES, "output_type": "idw", "window_size": 6,
         "origin_x": XMIN, "origin_y": YMIN, "width": 333, "height": 333,
         "nodata": -9999},
    ]
    p = PIPE_DIR / f"pipe_{tag}.json"
    p.write_text(json.dumps({"pipeline": stages}, indent=2))
    print(f"  {tag}: running...")
    r = subprocess.run([str(ENV / "Library" / "bin" / "pdal.exe"),
                        "pipeline", str(p)],
                       capture_output=True, text=True, env=pdal_env())
    if r.returncode != 0:
        print(r.stderr[-1500:], file=sys.stderr)
        raise SystemExit("pdal failed")
    return out


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a


def main():
    print("building the two runs (no buffer, no neighbours in either):")
    a = build("phaseA_plain")
    b = build("phaseB_shift1.5m", crop_xmin=XMIN + SHIFT)

    A, B = load(a), load(b)
    d = B - A
    _, cols = np.indices(A.shape)
    x = XMIN + (cols + 0.5) * RES
    far = np.isfinite(d) & (x > XMIN + FAR)

    n_diff = int(np.sum(far & (d != 0)))
    print(f"\ncells more than {FAR:.0f} m east of the removed strip: {int(far.sum()):,}")
    print(f"  differing at all : {n_diff:,} ({100*n_diff/far.sum():.1f}%)")
    if n_diff:
        dd = d[far & (d != 0)]
        print(f"  RMS  {np.sqrt((dd**2).mean()):.6f} m")
        print(f"  max  {np.abs(dd).max():.4f} m")
        print(f"  >0.05 m : {int(np.sum(np.abs(dd) > 0.05)):,} cells")

    print(f"""
VERDICT

  These cells contain byte-identical input points in both runs. The only
  difference is that run B's data bounding box starts {SHIFT} m further east,
  which shifts the phase of every internal SMRF/ELM cell.

  {'CONFIRMED: extent alone changes the result tile-wide.' if n_diff else 'NOT confirmed: extent does not affect distant cells.'}
""")
    if n_diff:
        print("""  Consequence: a buffered run cannot be compared cell-by-cell with an
  unbuffered one, because adding a margin necessarily moves the extent.
  The difference between them is grid phase plus edge effect, and this
  method cannot separate the two. The edge-effect numbers measured
  earlier must NOT be reported.""")


if __name__ == "__main__":
    main()
