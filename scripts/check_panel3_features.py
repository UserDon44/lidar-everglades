#!/usr/bin/env python3
"""
Test two proposed readings of fig01 panel 3 before either is captioned.

PROPOSED READINGS
=================
  A. The green "returns, none ground" strips flanking the canal are the
     levee crown -- i.e. the crown truncation seen in classification
     space rather than elevation space.
  B. The bottom-right disruption is the S-151 works.

Both are plausible from the image. Neither is captioned until measured,
because a caption that names a feature is a claim about what the data
contains, and this project has already had one figure caption assert a
difference between two byte-identical rasters.

TESTS
=====
  A: the green class is computed from the VENDOR classification
     (returns present, none of them class 2). If the strips were the
     crown, crest cells would be largely green. Measured directly as the
     overlap between the green mask and the crest mask, plus the
     distribution of green cells by distance from the crest.

  B: S-151's published coordinate is projected into EPSG:6350 and tested
     for containment in the anomalous corner. That is arithmetic on a
     sourced coordinate, which beats matching shapes by eye.

PARAMETERS
==========
  green mask : all-return count > 0 AND ground count == 0, at 3 m
  crest mask : vendor > marsh median + 2.0 m (same as the window sweep)
  corner     : SE 300 m square, the region used in the swath check
  S-151      : -80.50985262, 26.01151058 (WGS84), from SFWMD AHED
"""
import sys
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import Dump  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"
VENDOR = DEM / "dem_VENDOR_3m_aligned.tif"
XMIN, YMIN, XMAX, YMAX = 1557000.0, 456000.0, 1558000.0, 457000.0
CREST_ABOVE = 2.0
CORNER = 300.0
S151_LON, S151_LAT = -80.50985262, 26.01151058


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
        "panel3_feature_check",
        "What the green strips and the SE-corner disruption in fig01 "
        "panel 3 actually are",
        {
            "green mask": "all-return count > 0 AND ground count == 0, 3 m",
            "crest mask": f"vendor > marsh median + {CREST_ABOVE} m",
            "corner": f"SE {CORNER:g} m square",
            "S-151 coordinate": f"{S151_LON}, {S151_LAT} (WGS84, SFWMD AHED)",
            "reading A under test": "green strips are the levee crown",
            "reading B under test": "SE disruption is the S-151 works",
            "why measured first": "a caption naming a feature is a claim "
                                  "about the data; this project has already "
                                  "captioned a difference between two "
                                  "byte-identical rasters",
        },
    ):
        v, ds = load(VENDOR)
        g05, _ = load(DEM / "count_ground_0.5m.tif", to_nan=False)
        a05, _ = load(DEM / "count_allret_0.5m.tif", to_nan=False)
        g3 = agg(np.nan_to_num(g05), 6)
        a3 = agg(np.nan_to_num(a05), 6)
        h = min(v.shape[0], g3.shape[0]); w = min(v.shape[1], g3.shape[1])
        v, g3, a3 = v[:h, :w], g3[:h, :w], a3[:h, :w]

        marsh = float(np.nanmedian(v))
        crest = np.nan_to_num(v, nan=-9999) > (marsh + CREST_ABOVE)
        green = (a3 > 0) & (g3 == 0)

        print("READING A: are the green strips the levee crown?")
        print("=" * 70)
        print(f"crest cells                 : {int(crest.sum()):,}")
        print(f"green cells                 : {int(green.sum()):,}")
        overlap = int((crest & green).sum())
        print(f"cells that are BOTH         : {overlap:,} "
              f"({100*overlap/max(int(crest.sum()),1):.2f}% of crest, "
              f"{100*overlap/max(int(green.sum()),1):.2f}% of green)")

        dist = ndimage.distance_transform_edt(~crest) * 3.0
        print("\ngreen cells by distance from the crest:")
        for lo, hi in ((0, 3), (3, 9), (9, 21), (21, 51), (51, 10_000)):
            m = green & (dist >= lo) & (dist < hi)
            base = (dist >= lo) & (dist < hi)
            lbl = f"{lo}-{hi} m" if hi < 10_000 else f">{lo} m"
            print(f"  {lbl:<10} {int(m.sum()):>7,} green of "
                  f"{int(base.sum()):>7,} cells "
                  f"({100*m.sum()/max(base.sum(),1):>5.1f}% green)")

        print(f"\ntile-wide green rate: {100*green.mean():.1f}%")
        print(f"green rate ON crest : {100*green[crest].mean():.1f}%")

        if green[crest].mean() < 0.10:
            print("\n  VERDICT A: REFUTED. The crest is NOT green -- the "
                  "vendor classifies\n  ground there readily. The strips are "
                  "something else; see below.")
        else:
            print("\n  VERDICT A: supported.")

        # What ARE the green strips, then? Characterise by elevation.
        ge = v[green & np.isfinite(v)]
        ce = v[crest & np.isfinite(v)]
        print(f"\n  elevation of green cells : median {np.median(ge):.3f} m "
              f"({np.median(ge)-marsh:+.3f} vs marsh)")
        print(f"  elevation of crest cells : median {np.median(ce):.3f} m "
              f"({np.median(ce)-marsh:+.3f} vs marsh)")
        print(f"  green cells within 21 m of crest: "
              f"{100*np.mean(dist[green] < 21):.1f}%")

        print("\n\nREADING B: is the SE disruption the S-151 works?")
        print("=" * 70)
        tf = Transformer.from_crs("EPSG:4326", "EPSG:6350", always_xy=True)
        sx, sy = tf.transform(S151_LON, S151_LAT)
        print(f"S-151 projected to EPSG:6350 : {sx:.1f}, {sy:.1f}")
        print(f"tile bounds                  : X {XMIN:.0f}-{XMAX:.0f}, "
              f"Y {YMIN:.0f}-{YMAX:.0f}")
        inside = (XMIN <= sx <= XMAX) and (YMIN <= sy <= YMAX)
        print(f"inside the tile              : {inside}")
        in_corner = (sx >= XMAX - CORNER) and (sy <= YMIN + CORNER)
        print(f"inside the SE {CORNER:g} m corner    : {in_corner}")
        print(f"distance from SE corner point: "
              f"{np.hypot(sx - XMAX, sy - YMIN):.0f} m")

        if inside:
            col = int((sx - XMIN) // 3)
            row = int((YMAX - sy) // 3)
            r0, r1 = max(0, row - 17), min(h, row + 18)
            c0, c1 = max(0, col - 17), min(w, col + 18)
            loc = v[r0:r1, c0:c1]
            locg = g3[r0:r1, c0:c1]
            print(f"\n  100 m box centred on S-151 (row {row}, col {col}):")
            print(f"    elevation  median {np.nanmedian(loc):.3f} m  "
                  f"max {np.nanmax(loc):.3f} m  "
                  f"({np.nanmax(loc)-marsh:+.2f} above marsh)")
            print(f"    ground count/cell median {np.median(locg):.0f} "
                  f"(tile marsh median 7)")
            print(f"    cells >1 m above marsh: "
                  f"{100*np.nanmean(loc > marsh+1.0):.1f}%")

        print("\n" + "=" * 70)
        print("Both readings are now measured rather than inferred; the "
              "captions can\nstate whichever survived.")


if __name__ == "__main__":
    main()
