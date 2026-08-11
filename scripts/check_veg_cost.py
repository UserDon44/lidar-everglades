#!/usr/bin/env python3
"""
Independent mechanism check on the window/cell result.

THE COMPETING EXPLANATION
-------------------------
The crest measurement shows small windows (and a finer cell) preserve the
levee crown, exactly as the opening-scale mechanism predicts. But a
prediction coming true is not verification -- this project has already
been burned once by a correct-looking prediction that a bug happened to
satisfy.

The obvious rival explanation here: a smaller structuring element filters
LESS EVERYWHERE. If so, the crown survives not because the SE fits inside
it, but because the run is simply retaining more non-ground points across
the whole tile -- vegetation included. That would make the "good" setting
a worse bare-earth surface wearing a better crest number.

The two explanations differ in a way that is directly measurable:

  opening-scale : the effect is CONFINED to features near SE scale.
                  Marsh, where vegetation sits ~0.24 m above ground and
                  clumps are ~6 m wide, should be largely unaffected.

  under-filtering : the effect is TILE-WIDE. The marsh surface should sit
                    measurably higher, biased upward by retained
                    vegetation, and the high-bias tail should grow.

So: compare each run against the vendor ground surface over the whole
tile, and specifically over marsh cells AWAY from the embankment.

PARAMETERS
----------
  reference   : dem_VENDOR_3m_aligned.tif (vendor class-2, same grid)
  marsh datum : median of valid vendor cells
  embankment  : vendor > marsh + 0.3 m, dilated by DILATE cells, then
                EXCLUDED -- so the marsh statistics cannot be
                contaminated by the very feature under test
  DILATE = 10 cells (30 m), comfortably wider than the 45.7 m base
           half-width plus the largest SE tested

A run that retains vegetation shows a positive mean bias and a fatter
upper tail over the marsh-only mask. A run that merely preserves the
crown shows marsh statistics indistinguishable from the others.
"""
import numpy as np
import rasterio
from pathlib import Path
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"
DILATE = 10

TAGS = [
    "w3_s0.05_t0.15", "w6_s0.05_t0.15", "w12_s0.05_t0.15",
    "w25_s0.05_t0.15", "w50_s0.05_t0.15", "c1.5_w3_s0.05_t0.15",
]


def load(p):
    ds = rasterio.open(p)
    a = ds.read(1).astype("float64")
    a[a == ds.nodata] = np.nan
    return a


def main():
    v = load(VENDOR)
    marsh_z = float(np.nanmedian(v))

    emb = np.nan_to_num(v, nan=-9999) > (marsh_z + 0.3)
    emb_wide = ndimage.binary_dilation(emb, iterations=DILATE)
    marsh_only = (~emb_wide) & np.isfinite(v)

    print(f"reference : {VENDOR.name}")
    print(f"marsh datum : {marsh_z:.3f} m")
    print(f"embankment+{DILATE*3} m buffer excluded : "
          f"{int(emb_wide.sum()):,} cells")
    print(f"marsh-only mask : {int(marsh_only.sum()):,} cells "
          f"({100*marsh_only.sum()/v.size:.1f}% of tile)\n")

    print("Difference from vendor ground surface, MARSH ONLY "
          "(embankment excluded):")
    print("=" * 82)
    print(f"{'tag':<24} {'mean':>8} {'median':>8} {'RMSE':>8} "
          f"{'>0.15m':>8} {'>0.30m':>8}")
    print("=" * 82)
    for tag in TAGS:
        p = DEM / f"dem_{tag}.tif"
        if not p.exists():
            print(f"{tag:<24} MISSING")
            continue
        a = load(p)
        d = (a - v)[marsh_only]
        d = d[np.isfinite(d)]
        print(f"{tag:<24} {d.mean():>+8.4f} {np.median(d):>+8.4f} "
              f"{np.sqrt((d**2).mean()):>8.4f} "
              f"{100*np.mean(d > 0.15):>7.2f}% {100*np.mean(d > 0.30):>7.2f}%")
    print("=" * 82)
    print("""
READING THIS

  If the small-window / fine-cell runs are simply under-filtering, their
  marsh mean bias and high tails grow visibly relative to the large-window
  runs. If the effect really is confined to the SE scale, these rows are
  near-identical and the crest difference stands on its own.
""")


if __name__ == "__main__":
    main()
