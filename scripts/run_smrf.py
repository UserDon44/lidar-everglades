#!/usr/bin/env python3
"""
Bare-earth DEM via PDAL SMRF for the Everglades / S-151 tile.

ALL LINEAR PARAMETERS ARE METRES. This tile is EPSG:6350 (Conus Albers,
metres); project one's equivalent script defaults to feet and its ELM
defaults were feet-valued literals until they were parameterized. Nothing
here inherits a numeric default from that project -- every value is
either measured from this data or explicitly flagged as unvalidated.

Deliberately a local script rather than a call into project one's
run_dem.py: that project is frozen, and its outputs would land in its
tree. The duplicated pipeline construction is accepted for now; the
right extraction is a shared package, which is a larger decision than
this task.

Writes the pipeline JSON for every run to scripts/pipelines/ as an audit
trail, same convention as project one.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The conda env's CLI tools live in Library/bin, not the env root, and
# importing them without a patched PATH fails with exit 127 and no Python
# traceback (a DLL resolution failure, not an exception). Resolve
# explicitly so this script runs from an unactivated shell.
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
PDAL = ENV / "Library" / "bin" / "pdal.exe"


def pdal_env():
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([
        str(ENV), str(ENV / "Library" / "bin"), str(ENV / "Scripts"),
        e.get("PATH", ""),
    ])
    e["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    e["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")
    return e
TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"
DEM_DIR = ROOT / "output" / "dem"
PIPE_DIR = ROOT / "scripts" / "pipelines"

# Tile bounds from the LAZ header (Conus Albers metres). Fixed here so
# every run rasterizes onto the SAME grid -- otherwise writers.gdal sizes
# each raster from its own surviving point set and outputs become
# non-differenceable, which is exactly the grid-alignment bug project one
# had to fix after the fact.
XMIN, YMIN, XMAX, YMAX = 1557000.0, 456000.0, 1558000.0, 457000.0


def build_pipeline(out_tif, window, slope, threshold, scalar, cell, res,
                    elm_cell, elm_threshold):
    width = int(round((XMAX - XMIN) / res))
    height = int(round((YMAX - YMIN) / res))
    return {
        "pipeline": [
            {"type": "readers.las", "filename": str(TILE).replace("\\", "/")},
            # Strip the vendor's classification so SMRF is genuinely doing
            # the work and the result is independent of their decisions.
            {"type": "filters.assign", "assignment": "Classification[:]=0"},
            {"type": "filters.elm", "cell": elm_cell, "threshold": elm_threshold},
            {"type": "filters.outlier", "method": "statistical",
             "mean_k": 8, "multiplier": 3.0},
            {"type": "filters.smrf",
             "cell": cell, "window": window, "slope": slope,
             "threshold": threshold, "scalar": scalar,
             "ignore": "Classification[7:7]"},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"type": "writers.gdal",
             "filename": str(out_tif).replace("\\", "/"),
             "resolution": res,
             "output_type": "idw",
             "window_size": 6,
             "origin_x": XMIN, "origin_y": YMIN,
             "width": width, "height": height,
             "nodata": -9999},
        ]
    }


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(tag, window, slope, threshold, scalar, cell, res,
         elm_cell, elm_threshold, force=False):
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    PIPE_DIR.mkdir(parents=True, exist_ok=True)
    out_tif = DEM_DIR / f"dem_{tag}.tif"
    pipe_path = PIPE_DIR / f"pipe_{tag}.json"

    pipe = build_pipeline(out_tif, window, slope, threshold, scalar, cell,
                           res, elm_cell, elm_threshold)
    pipe_path.write_text(json.dumps(pipe, indent=2))

    if out_tif.exists() and not force:
        print(f"  {tag}: exists, skipping (--force to rebuild)")
        return out_tif, None

    print(f"  {tag}: window={window} slope={slope} threshold={threshold} "
          f"scalar={scalar} cell={cell} res={res}")
    t0 = time.time()
    proc = subprocess.run(
        [str(PDAL), "pipeline", str(pipe_path)],
        capture_output=True, text=True, env=pdal_env(),
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"pdal failed for {tag} (exit {proc.returncode})")
    elapsed = time.time() - t0
    print(f"    done in {elapsed:.1f}s -> {out_tif.name}")
    return out_tif, elapsed


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag", required=True, help="output name stem")
    p.add_argument("--window", type=float, required=True, help="METRES")
    p.add_argument("--slope", type=float, required=True, help="dimensionless")
    p.add_argument("--threshold", type=float, required=True, help="METRES")
    p.add_argument("--scalar", type=float, default=1.25,
                   help="NOT derived from this data -- inherited, unvalidated")
    p.add_argument("--cell", type=float, required=True, help="METRES")
    p.add_argument("--res", type=float, default=3.0, help="METRES")
    p.add_argument("--elm-cell", type=float, required=True, help="METRES")
    p.add_argument("--elm-threshold", type=float, required=True, help="METRES")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()

    out, _ = run(a.tag, a.window, a.slope, a.threshold, a.scalar, a.cell,
                  a.res, a.elm_cell, a.elm_threshold, a.force)
    print(f"  md5 {md5(out)}  {out.name}")


if __name__ == "__main__":
    main()
