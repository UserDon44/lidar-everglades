#!/usr/bin/env python3
"""
Hydrologic analysis appropriate to a managed wetland, plus the test that
rules out the standard one.

WHY THIS IS NOT A D8 WORKFLOW
=============================
The predecessor project ran depression filling, D8 flow direction and
accumulation, stream extraction and watershed delineation on a tile with
164 ft of relief. Repeating that structure here would be running a method
because the previous project ran it.

D8 assigns each cell's flow to whichever of its eight neighbours lies
lowest. That is only meaningful if the elevation difference deciding the
choice exceeds the surface's own uncertainty. Part 1 below measures
exactly that and finds it does not -- by roughly an order of magnitude.
The finding is reported rather than worked around, because a flow network
computed anyway would look entirely plausible and be a map of noise.

WHAT IS COMPUTED INSTEAD
========================
Part 2  stage-area hypsometry: inundated area as a function of water
        surface elevation. A threshold on the DEM -- no routing, no
        gradient assumption. The elevation DISTRIBUTION is well
        constrained even where local gradients are not, which is why this
        survives when D8 does not.

Part 3  levee crest profile and low points, computed on the VENDOR
        surface rather than ours. This project's own surface truncates
        the crown by a median 0.911 m (qc_memo section 7.1), which is
        precisely the quantity a crest profile measures. Using our own
        deliverable here would report our known deficiency as terrain.
        Choosing the better input for one specific analysis, and saying
        so, is the correct call.

NOT ATTEMPTED, deliberately: flow accumulation, watershed delineation,
stream extraction. See Part 1.
"""
import os
import sys
from pathlib import Path

# Env bootstrap before any native-DLL import. Without it this exits 127
# with no traceback -- a DLL resolution failure rather than an exception,
# so the script prints nothing at all and looks like it did nothing. This
# is the fourth script in the project to need it; it belongs in a shared
# module, which is noted as a cleanup rather than done mid-analysis.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import Dump  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
FINAL = DEM / "dem_w3_s0.05_t0.15.tif"
VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"
COUNTS = DEM / "count_allret_0.5m.tif"

CELL = 3.0
CELL_AREA = CELL * CELL
NOISE = 0.0807          # marsh agreement RMSE, qc_vs_vendor
GRIDPHASE = 0.055       # SMRF extent sensitivity, qc_memo section 7.6
CREST_ABOVE = 2.0
BIN = 15.0              # m along the levee axis


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a, ds


def agg(a, f):
    h = (a.shape[0] // f) * f
    w = (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).sum(axis=(1, 3))


def neighbour_drops(z):
    """Elevation drop from each cell to each of its 8 neighbours."""
    H, W = z.shape
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nb = np.full_like(z, np.nan)
            sr = slice(max(0, dr), H + min(0, dr))
            sc = slice(max(0, dc), W + min(0, dc))
            tr = slice(max(0, -dr), H + min(0, -dr))
            tc = slice(max(0, -dc), W + min(0, -dc))
            nb[tr, tc] = z[sr, sc]
            out.append(z - nb)
    return np.dstack(out)


def main():
    with Dump(
        "hydrology",
        "Hydrologic analysis for a managed wetland, and the test ruling "
        "out gradient-based flow routing",
        {
            "surface (parts 1-2)": FINAL.name,
            "surface (part 3)": VENDOR.name + "  -- deliberately NOT ours",
            "why vendor for crest": "our surface truncates the crown by a "
                                    "median 0.911 m, which is the very "
                                    "quantity a crest profile measures",
            "marsh definition": "cells with returns, at or below marsh "
                                "median + 0.3 m",
            "noise floor": f"{NOISE} m marsh agreement RMSE; {GRIDPHASE} m "
                           "grid-phase sensitivity",
            "crest mask": f"vendor > marsh median + {CREST_ABOVE} m",
            "crest axis": "first principal component of crest cell "
                          "coordinates; the levee runs NE-SW so no row or "
                          "column transect follows it",
            "crest bin": f"{BIN} m along that axis, max elevation per bin",
            "hypsometry step": "0.05 m, from p1 to p99 of ground elevation",
            "NOT computed": "flow accumulation, watersheds, stream networks "
                            "-- see part 1",
        },
    ):
        z, ds = load(FINAL)
        v, _ = load(VENDOR)
        a05, _ = load(COUNTS)
        a3 = agg(np.nan_to_num(a05), 6)
        H = min(z.shape[0], a3.shape[0])
        W = min(z.shape[1], a3.shape[1])
        z, v, a3 = z[:H, :W], v[:H, :W], a3[:H, :W]
        marsh_z = float(np.nanmedian(v))
        marsh = (a3 > 0) & (np.nan_to_num(v, nan=-9999) <= marsh_z + 0.3)

        # ---------------- Part 1: is D8 meaningful here? --------------
        print("=" * 74)
        print("PART 1  Does gradient-based flow routing apply?")
        print("=" * 74)
        D = neighbour_drops(z)
        best = np.nanmax(D, axis=2)
        srt = np.sort(D, axis=2)
        gap = srt[:, :, -1] - srt[:, :, -2]
        m = marsh & np.isfinite(best) & np.isfinite(gap)
        bd, gp = best[m], gap[m]
        print(f"marsh cells analysed: {int(m.sum()):,}\n")
        print("steepest descent to any of 8 neighbours (m):")
        for q in (10, 25, 50, 75, 90):
            print(f"    p{q:<3} {np.percentile(bd, q):.4f}")
        print("\ngap between steepest and SECOND steepest -- this is what")
        print("decides WHICH neighbour the flow is assigned to (m):")
        for q in (25, 50, 75, 90):
            print(f"    p{q:<3} {np.percentile(gp, q):.4f}")
        print()
        print(f"marsh cells whose steepest descent < {NOISE} m noise floor: "
              f"{100*np.mean(bd < NOISE):.1f}%")
        print(f"                              < {GRIDPHASE} m grid phase   : "
              f"{100*np.mean(bd < GRIDPHASE):.1f}%")
        print(f"cells whose DIRECTION-DECIDING gap < {NOISE} m: "
              f"{100*np.mean(gp < NOISE):.1f}%")
        print(f"""
VERDICT: the direction assignment is made from differences a median
{np.percentile(gp,50):.4f} m across, against a {NOISE} m noise floor. D8 output here
would be a map of the noise, and would look entirely plausible.
""")

        # ---------------- Part 2: stage-area hypsometry ---------------
        print("=" * 74)
        print("PART 2  Stage-area hypsometry")
        print("=" * 74)
        valid = np.isfinite(z)
        lo, hi = np.nanpercentile(z[valid], [1, 99])
        stages = np.arange(np.floor(lo * 20) / 20, hi + 0.05, 0.05)
        total_ha = valid.sum() * CELL_AREA / 10000.0
        print(f"tile area with data: {total_ha:.1f} ha "
              f"({int(valid.sum()):,} cells)\n")
        print(f"{'stage (m)':>10} {'inundated ha':>13} {'% of tile':>10} "
              f"{'ha per cm':>11}")
        print("-" * 48)
        prev = None
        rows = []
        for s in stages:
            a = float((z[valid] <= s).sum()) * CELL_AREA / 10000.0
            rate = (a - prev) / 5.0 if prev is not None else np.nan
            rows.append((s, a, 100 * a / total_ha, rate))
            prev = a
        for (s, a, pc, r) in rows:
            if abs(s * 10 - round(s * 10)) < 1e-6:   # every 0.10 m
                print(f"{s:>10.2f} {a:>13.1f} {pc:>9.1f}% "
                      f"{r if np.isfinite(r) else 0:>11.2f}")
        peak = max((r for r in rows if np.isfinite(r[3])), key=lambda r: r[3])
        print(f"\nmost sensitive stage: {peak[0]:.2f} m, "
              f"{peak[3]:.2f} ha flooded per additional cm")
        for frac in (0.25, 0.50, 0.75, 0.90):
            s = float(np.percentile(z[valid], frac * 100))
            print(f"  {frac*100:.0f}% of the tile lies below {s:.3f} m")
        np.save(DEM / "hypsometry.npy", np.array(rows))

        # ---------------- Part 3: levee crest profile -----------------
        print("\n" + "=" * 74)
        print("PART 3  Levee crest profile and low points (VENDOR surface)")
        print("=" * 74)
        crest = np.nan_to_num(v, nan=-9999) > (marsh_z + CREST_ABOVE)
        rr, cc = np.where(crest)
        xs = ds.bounds.left + (cc + 0.5) * CELL
        ys = ds.bounds.top - (rr + 0.5) * CELL
        pts = np.column_stack([xs, ys])
        ctr = pts.mean(axis=0)
        u, s_, vt = np.linalg.svd(pts - ctr, full_matrices=False)
        axis = vt[0]
        t = (pts - ctr) @ axis
        elev = v[rr, cc]
        print(f"crest cells: {len(t):,}")
        print(f"axis bearing: {(np.degrees(np.arctan2(axis[0], axis[1])) % 180):.1f} deg")
        print(f"crest length along axis: {t.max()-t.min():.0f} m\n")
        edges = np.arange(t.min(), t.max() + BIN, BIN)
        prof = []
        for i in range(len(edges) - 1):
            sel = (t >= edges[i]) & (t < edges[i + 1])
            if sel.sum() >= 3:
                prof.append((0.5 * (edges[i] + edges[i + 1]),
                             float(np.max(elev[sel])), int(sel.sum())))
        prof = np.array([(a, b, c) for a, b, c in prof])
        pe = prof[:, 1]
        print(f"crest elevation along the levee, {len(prof)} bins of {BIN:g} m:")
        print(f"  max    {pe.max():.3f} m   ({pe.max()-marsh_z:+.3f} above marsh)")
        print(f"  median {np.median(pe):.3f} m")
        print(f"  min    {pe.min():.3f} m   ({pe.min()-marsh_z:+.3f} above marsh)")
        print(f"  range along crest: {pe.max()-pe.min():.3f} m")
        order = np.argsort(pe)
        print(f"\nthree lowest points on the crest (first to overtop):")
        for i in order[:3]:
            print(f"  {prof[i,1]:.3f} m at {prof[i,0]:+.0f} m along axis "
                  f"({prof[i,1]-pe.max():.3f} m below crest max, "
                  f"{int(prof[i,2])} cells in bin)")
        print(f"""
Read as freeboard, not as absolute overtopping risk: this is a bare-earth
surface with no gauge tie, and the low points say where the barrier is
weakest relative to itself. Computed on the VENDOR surface because our own
truncates the crown by a median 0.911 m -- using it here would report a
known processing deficiency as terrain.
""")
        np.save(DEM / "crest_profile.npy", prof)


if __name__ == "__main__":
    main()
