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
                    elm_cell, elm_threshold, no_outlier=False):
    width = int(round((XMAX - XMIN) / res))
    height = int(round((YMAX - YMIN) / res))
    outlier = [] if no_outlier else [
        {"type": "filters.outlier", "method": "statistical",
         "mean_k": 8, "multiplier": 3.0}]
    return {
        "pipeline": [
            {"type": "readers.las", "filename": str(TILE).replace("\\", "/")},
            # Strip the vendor's classification so SMRF is genuinely doing
            # the work and the result is independent of their decisions.
            {"type": "filters.assign", "assignment": "Classification[:]=0"},
            {"type": "filters.elm", "cell": elm_cell, "threshold": elm_threshold},
            *outlier,
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


NEIGHBOURS = [
    "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0457.laz",  # N
    "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0455.laz",  # S
    "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1558n0456.laz",  # E
    "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1556n0456.laz",  # W
]


def build_buffered_pipeline(out_tif, buffer_m, window, slope, threshold,
                             scalar, cell, res, elm_cell, elm_threshold,
                             no_outlier=False):
    """Classify with a margin of neighbour points, then crop the RASTER.

    The buffer must exceed BOTH reaches that can distort an edge cell:

      SMRF classification : ceil(window / cell) cells
      IDW interpolation   : writers.gdal window_size (6) * res = 18 m

    The prior project's first buffered implementation cropped the POINTS
    to the tile before rasterizing. That fixed SMRF's edge effect but left
    IDW interpolating edge cells from a one-sided neighbourhood -- inside
    the very zone the seam metric sampled -- and produced a headline
    finding that had to be retracted the same day. So here the raster is
    written on an EXTENDED grid and clipped afterwards with
    gdal_translate -srcwin, which is the only ordering that removes both.
    """
    if buffer_m % res != 0:
        raise ValueError(f"buffer {buffer_m} must be a whole number of {res} m cells")
    pad = int(buffer_m / res)

    ext_origin_x = XMIN - buffer_m
    ext_origin_y = YMIN - buffer_m
    ext_w = int(round((XMAX - XMIN) / res)) + 2 * pad
    ext_h = int(round((YMAX - YMIN) / res)) + 2 * pad

    readers = [{"type": "readers.las", "filename": str(TILE).replace("\\", "/")}]
    missing = []
    for name in NEIGHBOURS:
        p = TILE.parent / name
        if p.exists():
            readers.append({"type": "readers.las",
                            "filename": str(p).replace("\\", "/")})
        else:
            missing.append(name)
    if missing:
        raise SystemExit("missing neighbour tiles:\n  " + "\n  ".join(missing))

    stages = readers + [
        {"type": "filters.merge"},
        # Read only what the buffer needs; this is an efficiency crop on
        # the INPUT extent, not the output crop -- the output is cropped
        # from the raster below.
        {"type": "filters.crop",
         "bounds": f"([{XMIN - buffer_m},{XMAX + buffer_m}],"
                   f"[{YMIN - buffer_m},{YMAX + buffer_m}])"},
        {"type": "filters.assign", "assignment": "Classification[:]=0"},
        {"type": "filters.elm", "cell": elm_cell, "threshold": elm_threshold},
        *([] if no_outlier else [{"type": "filters.outlier",
                                  "method": "statistical",
                                  "mean_k": 8, "multiplier": 3.0}]),
        {"type": "filters.smrf",
         "cell": cell, "window": window, "slope": slope,
         "threshold": threshold, "scalar": scalar,
         "ignore": "Classification[7:7]"},
        {"type": "filters.range", "limits": "Classification[2:2]"},
        {"type": "writers.gdal",
         "filename": str(out_tif).replace("\\", "/"),
         "resolution": res, "output_type": "idw", "window_size": 6,
         "origin_x": ext_origin_x, "origin_y": ext_origin_y,
         "width": ext_w, "height": ext_h, "nodata": -9999},
    ]
    return {"pipeline": stages}, pad, ext_w, ext_h


def crop_raster(src, dst, pad, ext_w, ext_h, res):
    """Clip the extended raster back to the true tile, via -srcwin.

    yoff is measured from the TOP of the extended raster; the buffer is
    symmetric so it equals pad, but it is computed rather than assumed.
    """
    width = ext_w - 2 * pad
    height = ext_h - 2 * pad
    cmd = [str(ENV / "Library" / "bin" / "gdal_translate.exe"),
           "-srcwin", str(pad), str(pad), str(width), str(height),
           "-a_nodata", "-9999", str(src), str(dst)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=pdal_env())
    if proc.returncode != 0:
        print(proc.stderr[-1500:], file=sys.stderr)
        raise RuntimeError("gdal_translate failed")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(tag, window, slope, threshold, scalar, cell, res,
         elm_cell, elm_threshold, force=False, buffer_m=0.0,
         no_outlier=False):
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    PIPE_DIR.mkdir(parents=True, exist_ok=True)
    out_tif = DEM_DIR / f"dem_{tag}.tif"
    pipe_path = PIPE_DIR / f"pipe_{tag}.json"

    crop_args = None
    if buffer_m:
        raw_tif = DEM_DIR / f"dem_{tag}_extended.tif"
        pipe, pad, ext_w, ext_h = build_buffered_pipeline(
            raw_tif, buffer_m, window, slope, threshold, scalar, cell, res,
            elm_cell, elm_threshold, no_outlier)
        crop_args = (raw_tif, out_tif, pad, ext_w, ext_h, res)
    else:
        pipe = build_pipeline(out_tif, window, slope, threshold, scalar, cell,
                               res, elm_cell, elm_threshold, no_outlier)
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
    if crop_args:
        crop_raster(*crop_args)
        print(f"    cropped extended raster back to tile bounds "
              f"({crop_args[2]} cells removed each side)")
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
    p.add_argument("--buffer-m", type=float, default=0.0,
                   help="METRES of neighbour-tile margin to classify with, "
                        "cropped off the RASTER afterwards. Must exceed both "
                        "SMRF reach (ceil(window/cell) cells) and IDW reach "
                        "(window_size*res = 18 m). 0 = unbuffered.")
    p.add_argument("--no-outlier", action="store_true",
                   help="drop filters.outlier. Its statistical method "
                        "thresholds on statistics taken over the WHOLE point "
                        "set, so adding neighbour tiles shifts it globally -- "
                        "which confounds any buffered/unbuffered comparison.")
    a = p.parse_args()

    out, _ = run(a.tag, a.window, a.slope, a.threshold, a.scalar, a.cell,
                  a.res, a.elm_cell, a.elm_threshold, a.force, a.buffer_m,
                  a.no_outlier)
    print(f"  md5 {md5(out)}  {out.name}")


if __name__ == "__main__":
    main()
