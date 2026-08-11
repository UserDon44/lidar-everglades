#!/usr/bin/env python3
"""
Rebuild the vendor class-2 DEM on the SAME fixed grid the SMRF runs use.

The original dem_VENDOR_3m.tif let writers.gdal size the raster from the
point cloud's own extent (335x334, origin 1557000/455997). Every
SMRF run from run_smrf.py is written onto an explicit grid
(333x333, origin 1557000/456000), so the two are not cell-aligned and
cannot be compared or masked against each other.

This is the same grid-alignment defect project one hit between its
vendor and SMRF runs, and the fix is the same in principle: pin the grid
to fixed numbers rather than to whatever any individual run's surviving
points happen to span. Doing it by rebuilding rather than by warping
avoids resampling the reference surface the crest mask is derived from.
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")

TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"
OUT = ROOT / "output" / "dem" / "dem_VENDOR_3m_aligned.tif"
PIPE = ROOT / "scripts" / "pipelines" / "pipe_VENDOR_3m_aligned.json"

# Must match run_smrf.py exactly.
ORIGIN_X, ORIGIN_Y, WIDTH, HEIGHT, RES = 1557000.0, 456000.0, 333, 333, 3.0


def main():
    pipe = {
        "pipeline": [
            {"type": "readers.las", "filename": str(TILE).replace("\\", "/")},
            {"type": "filters.range", "limits": "Classification[2:2]"},
            {"type": "writers.gdal",
             "filename": str(OUT).replace("\\", "/"),
             "resolution": RES, "output_type": "idw", "window_size": 6,
             "origin_x": ORIGIN_X, "origin_y": ORIGIN_Y,
             "width": WIDTH, "height": HEIGHT, "nodata": -9999},
        ]
    }
    PIPE.write_text(json.dumps(pipe, indent=2))

    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([
        str(ENV), str(ENV / "Library" / "bin"), str(ENV / "Scripts"),
        env.get("PATH", ""),
    ])
    env["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    env["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")

    proc = subprocess.run(
        [str(ENV / "Library" / "bin" / "pdal.exe"), "pipeline", str(PIPE)],
        capture_output=True, text=True, env=env,
    )
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        raise SystemExit(f"pdal failed (exit {proc.returncode})")
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
