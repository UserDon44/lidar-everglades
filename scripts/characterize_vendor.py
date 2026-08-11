#!/usr/bin/env python3
"""
Re-derive the vendor-baseline characterization from the point cloud, and
CHECK EVERY NUMBER AGAINST WHAT THE MEMO CURRENTLY CLAIMS.

WHY THIS SCRIPT EXISTS
======================
The vendor characterization is the foundation of this project: the
cell-size sweep is what set `cell = 3.0 m`, which set the structuring
element scale, which is why the levee crown cannot be preserved. Every
parameter in the derivation rests on it.

It was computed interactively in an earlier session and never scripted.
Its numbers reached the memo, the figures and CLAUDE.md, but no artifact
on disk produces them -- the deliverable-number audit flagged 20 of them
as untraced, and they are the last 20.

This is precisely the failure this project has hit repeatedly: a result
that is real, cited everywhere, and unreproducible because the
derivation lived in a terminal. The predecessor project lost its
hydrology volumes the same way, and published a CHM cluster count of 13
that no search radius reproduces.

THE POINT IS THE COMPARISON, NOT THE RECOMPUTATION
==================================================
EXPECTED below holds what the memo says TODAY. The script reports the
re-derived value beside it and flags any disagreement. A silent
recomputation that quietly replaced the published numbers would destroy
the only evidence that a discrepancy existed -- so mismatches are
reported as mismatches, with both values, and nothing is auto-corrected.

METHOD
======
Counts and densities come from the LAZ header and from binmode count
rasters (never PDAL's default radius search, which inflates density
several-fold -- measured at ~6x in the predecessor project).

The cell-size sweep rasterizes ONCE at 0.5 m and aggregates by integer
factors (2, 4, 6, 10, 20) to 1, 2, 3, 5 and 10 m. Aggregation of true
per-cell counts is exact, so this is equivalent to rasterizing at each
size while being far cheaper and guaranteeing identical grid phase
across sizes.

Ground/vegetation overlap samples the vendor 3 m surface at every point
and takes the residual, split by classification.
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
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"
DEM = ROOT / "output" / "dem"
VENDOR3 = DEM / "dem_VENDOR_3m_aligned.tif"

XMIN, YMIN, XMAX, YMAX = 1557000.0, 456000.0, 1558000.0, 457000.0
BASE = 0.5                       # base rasterization, aggregates exactly
FACTORS = [1, 2, 4, 6, 10, 20]   # -> 0.5, 1, 2, 3, 5, 10 m

# What the memo/CLAUDE.md currently claim. Key -> (value, unit).
EXPECTED = {
    "ground share of points (%)": 7.432,
    "all-return density (pts/m2)": 16.89,
    "ground density (pts/m2)": 1.26,
    "ground relief p1-p99 (m)": 2.81,
    "no ground @0.5 m (%)": 76.79,
    "no ground @1 m (%)": 47.04,
    "no ground @2 m (%)": 18.11,
    "no ground @3 m (%)": 8.31,
    "no ground @5 m (%)": 4.63,
    "no ground @10 m (%)": 2.21,
    "no returns @1 m (%)": 6.06,
    "no returns @3 m (%)": 4.72,
    "water dropout (%)": 6.07,
    "vegetation blocked (%)": 41.10,
    "ground present (%)": 52.89,
    "slope median (%)": 0.489,
    "slope p90 (%)": 2.33,
    "slope p99 (%)": 20.4,
    "slope max (%)": 50.8,
    "class-2 residual std (m)": 0.072,
    "class-2 p5-p95 spread (m)": 0.133,
    "unclassified p50 above ground (m)": 0.240,
    "unclassified below 0.15 m (%)": 40.6,
    "unclassified below 0.30 m (%)": 56.1,
    "canal surface elevation (m)": 2.28,
}

TOL = {  # absolute tolerance by magnitude; presentation rounding only
    "default": 0.011,
}


def pdal_env():
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([str(ENV), str(ENV / "Library" / "bin"),
                                  str(ENV / "Scripts"), e.get("PATH", "")])
    e["GDAL_DATA"] = str(ENV / "Library" / "share" / "gdal")
    e["PROJ_LIB"] = str(ENV / "Library" / "share" / "proj")
    return e


def rasterize_counts(tag, ground_only):
    """binmode count raster at BASE resolution on the fixed grid."""
    out = DEM / f"count_{tag}_{BASE}m.tif"
    if out.exists():
        return out
    n = int(round((XMAX - XMIN) / BASE))
    stages = [{"type": "readers.las", "filename": str(TILE).replace("\\", "/")}]
    if ground_only:
        stages.append({"type": "filters.range", "limits": "Classification[2:2]"})
    stages.append({
        "type": "writers.gdal", "filename": str(out).replace("\\", "/"),
        "resolution": BASE, "output_type": "count", "binmode": True,
        "origin_x": XMIN, "origin_y": YMIN, "width": n, "height": n,
        "nodata": 0})
    p = ROOT / "scripts" / "pipelines" / f"pipe_count_{tag}_{BASE}m.json"
    p.write_text(json.dumps({"pipeline": stages}, indent=2))
    r = subprocess.run([str(ENV / "Library" / "bin" / "pdal.exe"), "pipeline",
                        str(p)], capture_output=True, text=True, env=pdal_env())
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        raise SystemExit(f"pdal failed for {tag}")
    return out


def agg(a, f):
    """Exact block-sum of per-cell counts by integer factor f."""
    if f == 1:
        return a
    h = (a.shape[0] // f) * f
    w = (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).sum(axis=(1, 3))


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if ds.nodata is not None:
        a[a == ds.nodata] = 0.0
    return a


def main():
    import laspy

    with Dump(
        "vendor_characterization",
        "Vendor baseline characterization, re-derived from the point cloud",
        {
            "tile": TILE.name,
            "grid": f"origin {XMIN}/{YMIN}, {XMAX-XMIN:.0f} m square",
            "counting": "binmode=true (true per-cell bins). PDAL's default "
                        "radius search inflates density several-fold",
            "cell sweep": f"rasterized once at {BASE} m, aggregated by "
                          f"{FACTORS} -- exact for counts, and guarantees "
                          "identical grid phase across sizes",
            "no ground": "share of cells whose class-2 count is 0",
            "no returns": "share of cells whose all-return count is 0",
            "relief": "class-2 Z, p1 to p99 (excludes single-point extremes)",
            "slope source": "gdaldem slope -p on the vendor 3 m surface",
            "overlap": "vendor 3 m surface sampled at every point; residual "
                       "split by classification",
            "canal elevation": "median vendor 3 m elevation over cells with "
                               "zero returns at 1 m",
            "purpose": "these numbers were computed interactively in an "
                       "earlier session and never scripted; EXPECTED holds "
                       "what the memo claims today",
        },
    ):
        got = {}

        # ---- header counts -------------------------------------------
        las = laspy.read(TILE)
        cls = np.asarray(las.classification)
        total = cls.size
        n_ground = int((cls == 2).sum())
        area = (XMAX - XMIN) * (YMAX - YMIN)
        got["ground share of points (%)"] = 100.0 * n_ground / total
        got["all-return density (pts/m2)"] = total / area
        got["ground density (pts/m2)"] = n_ground / area

        z = np.asarray(las.z, dtype="float64")
        gz = z[cls == 2]
        p1, p99 = np.percentile(gz, [1, 99])
        got["ground relief p1-p99 (m)"] = p99 - p1
        print(f"points {total:,}   class-2 {n_ground:,}")
        print(f"ground Z p1 {p1:.3f}  p99 {p99:.3f}\n")

        # ---- cell-size sweep -----------------------------------------
        g05 = load(rasterize_counts("ground", True))
        a05 = load(rasterize_counts("allret", False))
        print(f"{'cell':>6} {'no ground':>11} {'no returns':>12} "
              f"{'median g/cell':>14}")
        print("-" * 48)
        for f in FACTORS:
            cell = BASE * f
            g, a = agg(g05, f), agg(a05, f)
            ng = 100.0 * np.mean(g == 0)
            na = 100.0 * np.mean(a == 0)
            key_g = f"no ground @{cell:g} m (%)"
            key_a = f"no returns @{cell:g} m (%)"
            if key_g in EXPECTED:
                got[key_g] = ng
            if key_a in EXPECTED:
                got[key_a] = na
            print(f"{cell:>5.1f}m {ng:>10.2f}% {na:>11.2f}% "
                  f"{np.median(g):>14.1f}")
        print()

        # ---- void classes at 1 m -------------------------------------
        g1, a1 = agg(g05, 2), agg(a05, 2)
        water = a1 == 0
        veg = (a1 > 0) & (g1 == 0)
        grd = g1 > 0
        got["water dropout (%)"] = 100.0 * water.mean()
        got["vegetation blocked (%)"] = 100.0 * veg.mean()
        got["ground present (%)"] = 100.0 * grd.mean()

        # ---- slope ----------------------------------------------------
        slope_tif = DEM / "slope_pct_3m_aligned.tif"
        if not slope_tif.exists():
            subprocess.run([str(ENV / "Library" / "bin" / "gdaldem.exe"),
                            "slope", "-p", str(VENDOR3), str(slope_tif)],
                           capture_output=True, text=True, env=pdal_env())
        sd = rasterio.open(slope_tif)
        sl = sd.read(1).astype("float64")
        sl = sl[np.isfinite(sl) & (sl != (sd.nodata if sd.nodata is not None else -9999))]
        for k, q in (("slope median (%)", 50), ("slope p90 (%)", 90),
                      ("slope p99 (%)", 99)):
            got[k] = float(np.percentile(sl, q))
        got["slope max (%)"] = float(sl.max())

        # Both grids are reported: the memo quotes the original
        # point-derived grid, and the aligned grid is what everything
        # downstream uses. They differ by grid phase, not by disagreement.
        orig = DEM / "slope_pct_3m.tif"
        if orig.exists():
            od = rasterio.open(orig)
            osl = od.read(1).astype("float64")
            ond = od.nodata if od.nodata is not None else -9999
            osl = osl[np.isfinite(osl) & (osl != ond)]
            print(f"slope on ORIGINAL grid {od.shape}: "
                  f"median {np.percentile(osl,50):.3f}  p90 {np.percentile(osl,90):.3f}  "
                  f"p99 {np.percentile(osl,99):.3f}  max {osl.max():.3f}")
            print(f"slope on ALIGNED  grid {sd.shape}: "
                  f"median {np.percentile(sl,50):.3f}  p90 {np.percentile(sl,90):.3f}  "
                  f"p99 {np.percentile(sl,99):.3f}  max {sl.max():.3f}")
            print("")

        # ---- ground / vegetation overlap ------------------------------
        vd = rasterio.open(VENDOR3)
        surf = vd.read(1).astype("float64")
        if vd.nodata is not None:
            surf[surf == vd.nodata] = np.nan
        x = np.asarray(las.x, dtype="float64")
        y = np.asarray(las.y, dtype="float64")
        inv = ~vd.transform
        cc, rr = inv * (x, y)
        rr = np.floor(rr).astype(int)
        cc = np.floor(cc).astype(int)
        ok = (rr >= 0) & (rr < surf.shape[0]) & (cc >= 0) & (cc < surf.shape[1])
        resid = np.full(x.shape, np.nan)
        resid[ok] = z[ok] - surf[rr[ok], cc[ok]]

        r2 = resid[(cls == 2) & np.isfinite(resid)]
        got["class-2 residual std (m)"] = float(r2.std(ddof=1))
        lo, hi = np.percentile(r2, [5, 95])
        got["class-2 p5-p95 spread (m)"] = float(hi - lo)

        r1 = resid[(cls == 1) & np.isfinite(resid)]
        got["unclassified p50 above ground (m)"] = float(np.percentile(r1, 50))
        got["unclassified below 0.15 m (%)"] = 100.0 * float(np.mean(r1 < 0.15))
        got["unclassified below 0.30 m (%)"] = 100.0 * float(np.mean(r1 < 0.30))

        # ---- canal surface --------------------------------------------
        w3 = agg(a05, 6) == 0
        vs = surf.copy()
        h = min(w3.shape[0], vs.shape[0])
        w = min(w3.shape[1], vs.shape[1])
        sel = vs[:h, :w][w3[:h, :w]]
        got["canal surface elevation (m)"] = float(np.nanmedian(sel))
        # Alternative definitions, reported because the superseded 2.28 m
        # figure matches none of them and its own method was never stated.
        from scipy import ndimage as _nd
        lab, nlab = _nd.label(w3)
        szs = _nd.sum(w3, lab, range(1, nlab + 1))
        big = (lab == int(np.argmax(szs)) + 1)
        bsel = vs[:h, :w][big[:h, :w]]
        w1 = agg(a05, 2) == 0
        h1 = min(w1.shape[0] // 3 * 3, vs.shape[0])
        print(f"canal elevation by definition: median {np.nanmedian(sel):.3f}  "
              f"mean {np.nanmean(sel):.3f}  "
              f"largest-body {np.nanmedian(bsel):.3f}  "
              f"p25 {np.nanpercentile(sel, 25):.3f}")

        # ---- comparison ------------------------------------------------
        print("=" * 78)
        print("RE-DERIVED vs WHAT THE MEMO CLAIMS TODAY")
        print("=" * 78)
        print(f"{'quantity':<38} {'memo':>10} {'re-derived':>12} {'':>6}")
        print("-" * 78)
        mismatches = []
        for k, exp in EXPECTED.items():
            if k not in got:
                print(f"{k:<38} {exp:>10} {'NOT RUN':>12}")
                continue
            val = got[k]
            tol = max(TOL["default"], abs(exp) * 0.005)
            ok_ = abs(val - exp) <= tol
            flag = "ok" if ok_ else "<< DIFFERS"
            if not ok_:
                mismatches.append((k, exp, val))
            print(f"{k:<38} {exp:>10.3f} {val:>12.3f} {flag:>6}")
        print("=" * 78)

        if mismatches:
            print(f"\n{len(mismatches)} DISCREPANCIES -- both values shown, "
                  "nothing auto-corrected:\n")
            for k, exp, val in mismatches:
                print(f"  {k}")
                print(f"    memo carries : {exp}")
                print(f"    re-derived   : {val:.4f}")
                print(f"    difference   : {val - exp:+.4f}\n")
            print("  Decide which is right by reading the method, not by "
                  "preferring the newer number.")
        else:
            print("\nALL RE-DERIVED VALUES MATCH THE MEMO within presentation "
                  "rounding.\nThe characterization reproduces.")


if __name__ == "__main__":
    main()
