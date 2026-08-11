#!/usr/bin/env python3
"""
Are the bright pixels along the western levee crown real ground returns,
or interpolation artifacts?

WHY THIS IS BEING CHECKED BEFORE IT IS DESCRIBED
================================================
fig06 shows isolated high pixels strung along a linear feature at 20x
vertical exaggeration. That is the same signature as the predecessor
project's retracted "sliced hill": a feature that appeared only at high
exaggeration, was reported as real by author and reviewer, and turned
out to be texture stretched across a steep face by the exaggeration
itself. One elevation transect would have settled it and was not run
until after the claim had been written down.

So this runs first, and nothing about the speckle goes in the memo until
it resolves.

THE TEST IS NOT VISUAL
======================
`writers.gdal` with output_type=idw fills a cell from surrounding points
when the cell itself holds none, out to window_size (6 cells = 18 m). So
a cell's elevation can be high without a single ground return in it.

  ground count > 0 in the cell -> the value is MEASURED
  ground count = 0 in the cell -> the value is INTERPOLATED, and a
                                  bright isolated pixel there is an
                                  artifact of the fill, not terrain

That distinction is a count, not a judgement, which is the point.

PARAMETERS
==========
  surface       : dem_w3_s0.05_t0.15.tif (delivered, 3 m)
  ground counts : count_ground_0.5m.tif, binmode, aggregated x6 -> 3 m
  crest mask    : vendor > marsh median + 2.0 m (same mask as the window
                  sweep, so results are comparable to it)
  western leg   : crest cells with X below the crest centroid, since the
                  embankment runs NE-SW and the reported speckle is on
                  the western/south-western limb
  transect      : perpendicular to the local crest axis, sampled every
                  3 m, reporting elevation AND ground count together
"""
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import Dump  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
FINAL = DEM / "dem_w3_s0.05_t0.15.tif"
VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"
CREST_ABOVE = 2.0


def load(p, to_nan=True):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    if to_nan and ds.nodata is not None:
        a[a == ds.nodata] = np.nan
    return a, ds


def agg(a, f):
    h = (a.shape[0] // f) * f
    w = (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).sum(axis=(1, 3))


def main():
    with Dump(
        "crown_speckle_check",
        "Are bright pixels on the levee crown measured ground, or IDW fill?",
        {
            "surface": FINAL.name,
            "ground counts": "count_ground_0.5m.tif (binmode) aggregated x6",
            "crest mask": f"vendor > marsh median + {CREST_ABOVE} m",
            "decisive test": "ground count in the cell: >0 measured, "
                             "=0 interpolated by writers.gdal IDW",
            "IDW reach": "window_size 6 cells = 18 m, so a cell with no "
                         "ground return can still be filled",
            "why not visual": "the predecessor project's retracted hill "
                              "artifact was confirmed by two people looking "
                              "at a render; a transect settled it in under a "
                              "minute and was run only afterwards",
        },
    ):
        z, ds = load(FINAL)
        v, _ = load(VENDOR)
        gc05, _ = load(DEM / "count_ground_0.5m.tif", to_nan=False)
        gc = agg(np.nan_to_num(gc05), 6)

        h = min(z.shape[0], gc.shape[0])
        w = min(z.shape[1], gc.shape[1])
        z, v, gc = z[:h, :w], v[:h, :w], gc[:h, :w]

        marsh = float(np.nanmedian(v))
        crest = np.nan_to_num(v, nan=-9999) > (marsh + CREST_ABOVE)

        rows, cols = np.where(crest)
        col_mid = cols.mean()
        west = crest.copy()
        west[:, int(col_mid):] = False
        east = crest & ~west

        print(f"marsh datum {marsh:.3f} m")
        print(f"crest cells {int(crest.sum()):,}  "
              f"(west {int(west.sum()):,}, east {int(east.sum()):,})\n")

        print("=" * 74)
        print("IS THE ELEVATION MEASURED OR INTERPOLATED?")
        print("=" * 74)
        print(f"{'region':<26} {'cells':>8} {'ground count = 0':>18} "
              f"{'median ground count':>20}")
        print("-" * 74)
        for name, m in (("crest, western limb", west),
                         ("crest, eastern limb", east),
                         ("crest, all", crest),
                         ("marsh (control)", ~crest & np.isfinite(v))):
            empty = 100.0 * np.mean(gc[m] == 0)
            print(f"{name:<26} {int(m.sum()):>8,} {empty:>17.2f}% "
                  f"{np.median(gc[m]):>20.1f}")
        print("=" * 74)

        # The speckle specifically: bright cells on the western limb.
        above = z - marsh
        bright = west & (above > 1.5)
        print(f"\nWESTERN-LIMB CELLS ABOVE marsh + 1.5 m  (the visible speckle)")
        print(f"  count                     : {int(bright.sum()):,}")
        if bright.sum():
            print(f"  of these, ground count = 0: "
                  f"{int(np.sum(gc[bright] == 0)):,} "
                  f"({100*np.mean(gc[bright] == 0):.1f}%)")
            print(f"  median ground count       : {np.median(gc[bright]):.1f}")
            print(f"  median elevation          : "
                  f"{np.median(z[bright]):.3f} m "
                  f"({np.median(above[bright]):.3f} m above marsh)")
            iso = []
            rr, cc = np.where(bright)
            for r, c in zip(rr, cc):
                r0, r1 = max(0, r - 1), min(h, r + 2)
                c0, c1 = max(0, c - 1), min(w, c + 2)
                nb = bright[r0:r1, c0:c1].sum() - 1
                iso.append(nb)
            iso = np.array(iso)
            print(f"  ISOLATED (no bright 8-neighbour): "
                  f"{int(np.sum(iso == 0)):,} of {len(iso):,} "
                  f"({100*np.mean(iso == 0):.1f}%)")
            print("    isolated + measured  : "
                  f"{int(np.sum((iso == 0) & (gc[bright] > 0))):,}")
            print("    isolated + INTERPOLATED: "
                  f"{int(np.sum((iso == 0) & (gc[bright] == 0))):,}")

        # ---- transects across the western crown -----------------------
        print("\n" + "=" * 74)
        print("TRANSECTS ACROSS THE WESTERN CROWN")
        print("(elevation and ground count together; an interpolated peak "
              "shows elevation without counts)")
        print("=" * 74)
        wr, wc = np.where(west)
        # three rows spanning the western limb
        for frac in (0.25, 0.50, 0.75):
            r = int(np.percentile(wr, 100 * frac))
            band = wc[wr == r]
            if band.size == 0:
                continue
            c0 = max(0, band.min() - 6)
            c1 = min(w, band.max() + 7)
            print(f"\n  row {r} (northing {ds.bounds.top - (r+0.5)*3:.0f} m), "
                  f"columns {c0}-{c1-1}")
            print("    easting  elev(m)  above  gcount  source")
            for c in range(c0, c1):
                e = ds.bounds.left + (c + 0.5) * 3
                src = "measured" if gc[r, c] > 0 else "INTERPOLATED"
                mark = " <" if (z[r, c] - marsh) > 1.5 else ""
                print(f"    {e:>7.0f} {z[r,c]:>8.3f} {z[r,c]-marsh:>6.2f} "
                      f"{int(gc[r,c]):>7} {src}{mark}")

        print("\n" + "=" * 74)
        print("VERDICT")
        print("=" * 74)
        if bright.sum():
            frac_interp = float(np.mean(gc[bright] == 0))
            if frac_interp > 0.5:
                print("  The bright western-crown cells are predominantly "
                      "INTERPOLATED:\n  most contain no ground return at all. "
                      "They are an artifact of\n  IDW fill across the crown, "
                      "not surviving measurements.")
            elif frac_interp < 0.15:
                print("  The bright western-crown cells are predominantly "
                      "MEASURED:\n  they contain real ground returns. The "
                      "speckle is surviving crown\n  points, not an "
                      "interpolation artifact.")
            else:
                print(f"  MIXED: {100*frac_interp:.0f}% of bright crown cells "
                      "are interpolated.\n  Neither reading is clean; report "
                      "the split rather than a label.")


if __name__ == "__main__":
    main()
