#!/usr/bin/env python3
"""
Measure the embankment's width AS A FUNCTION OF HEIGHT above marsh.

WHY
---
The window sweep refuted the prediction that `window` controls whether
the L-67A embankment survives SMRF. The prediction was derived from a
recorded width of 32-46 m -- but that figure was measured by thresholding
at 0.3-1.5 m above marsh, which captures the embankment's BASE, where it
is widest.

Morphological opening does not act on the base. A diamond structuring
element of radius r erodes a raised feature once it no longer fits
within the feature AT THE HEIGHT BEING CUT. For a levee -- a trapezoid
in cross-section -- the relevant scale is the CROWN width, which is much
narrower than the base and is what a small window actually has to
preserve.

So the derivation used a real measurement of the wrong quantity. This
script measures width at a ladder of heights so the crown scale is a
number rather than an inference.

METHOD / PARAMETERS
-------------------
  reference : output/dem/dem_VENDOR_3m_aligned.tif (vendor class-2, 3 m)
  marsh datum : median of all valid cells (2.364 m)
  for each height h in HEIGHTS:
      mask = cells more than h above the marsh datum
      keep only the largest connected component (the levee itself,
      excluding isolated spoil piles and noise)
      width = 2 * max Euclidean distance-transform value within it,
              i.e. twice the inscribed radius -- the diameter of the
              largest disk that fits inside the feature at that height

Twice the inscribed radius is used rather than a bounding box because
the feature is diagonal and elongated: a bbox measures its LENGTH, not
its width. The inscribed disk is orientation-independent, which is the
property needed here.

The SMRF-relevant comparison is then: a diamond SE of radius r pixels
spans 2r+1 pixels, so it fits at height h only while
width(h) >= (2r+1) * cell.
"""
import numpy as np
import rasterio
from pathlib import Path
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "output" / "dem" / "dem_VENDOR_3m_aligned.tif"
CELL = 3.0

HEIGHTS = [0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75]


def main():
    ds = rasterio.open(VENDOR)
    a = ds.read(1).astype("float64")
    a[a == ds.nodata] = np.nan
    marsh = float(np.nanmedian(a))
    print(f"reference   : {VENDOR.name}")
    print(f"marsh datum : {marsh:.3f} m")
    print(f"cell        : {CELL} m\n")

    print(f"{'height above':>13} {'cells':>7} {'largest':>8} "
          f"{'inscribed':>10} {'width':>8}   SE that still fits")
    print(f"{'marsh (m)':>13} {'':>7} {'comp':>8} {'radius px':>10} {'(m)':>8}")
    print("-" * 78)

    rows = []
    for h in HEIGHTS:
        mask = np.nan_to_num(a, nan=-9999) > (marsh + h)
        n = int(mask.sum())
        if n == 0:
            print(f"{h:>13.2f} {0:>7} {'-':>8} {'-':>10} {'-':>8}")
            continue
        lab, nlab = ndimage.label(mask)
        sizes = ndimage.sum(mask, lab, range(1, nlab + 1))
        biggest = int(np.argmax(sizes)) + 1
        comp = lab == biggest
        ncomp = int(comp.sum())

        # Inscribed radius in pixels: largest disk fitting in the feature.
        dt = ndimage.distance_transform_edt(comp)
        r_px = float(dt.max())
        width_m = 2.0 * r_px * CELL

        # Largest diamond SE radius that still fits (spans 2r+1 px).
        r_fit = int((width_m / CELL - 1) // 2)
        rows.append((h, width_m, r_fit))
        print(f"{h:>13.2f} {n:>7} {ncomp:>8} {r_px:>10.2f} {width_m:>8.1f}"
              f"   r <= {r_fit} px  (window <= {r_fit * CELL:.0f} m)")

    print("-" * 78)
    print(f"""
INTERPRETATION

  Base width (the 32-46 m figure previously recorded) is measured near
  the bottom of this ladder. The crown -- what a structuring element
  must fit inside to preserve the top of the levee -- is the width at
  the HIGH end.

  A window of W metres gives max_radius = ceil(W / {CELL:.0f}) px, and the
  SE spans 2*max_radius+1 px. The embankment top survives only while
  that span stays under width(h) at the height in question.
""")
    return rows


if __name__ == "__main__":
    main()
