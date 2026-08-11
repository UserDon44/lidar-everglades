#!/usr/bin/env python3
"""
Measure whether the L-67A embankment survives each SMRF `window` setting.

WHY A FIXED MASK RATHER THAN A TRANSECT
---------------------------------------
The embankment runs diagonally (NE-SW) across the tile, so no row- or
column-aligned transect crosses it perpendicularly, and a hand-placed
oblique transect would be an unrecorded choice sitting under every
number. Instead the crest is defined ONCE, from the vendor baseline, as
a fixed set of cells, and every sweep output is sampled at exactly those
cells. The mask is a recorded parameter, identical across runs, so the
comparison is like-for-like by construction.

MEASUREMENT PARAMETERS (all fixed here, none tuned per run)
-----------------------------------------------------------
  reference surface : output/dem/dem_VENDOR_3m.tif (vendor class-2, 3 m)
  marsh datum       : median of all valid vendor cells
  crest mask        : vendor cells > marsh + CREST_ABOVE (2.0 m)
  marsh mask        : vendor cells within +/- 0.15 m of the marsh median,
                      used as the "did the flat terrain move?" control

CREST_ABOVE = 2.0 m is chosen to sit above the measured crest height
(2.91 m above marsh) minus a margin, and well above marsh roughness
(class-2 residual std 0.072 m). It selects the embankment top, not its
flanks -- flanks are where SMRF's slope term bites, and including them
would blend two different effects into one number.

WHAT THE NUMBERS MEAN
---------------------
If `window` stays below the erosion scale, crest cells keep their real
elevation and `crest_above_marsh` stays near 2.9 m. Once the diamond
structuring element exceeds the embankment width, the crest is opened
away, those points are classified non-ground, and the raster fills the
gap by IDW from surrounding marsh -- so `crest_above_marsh` collapses
toward 0. The marsh control should barely move in either case; if it
does, something other than the embankment is changing and the crest
number cannot be read on its own.

Checksums are reported because two `window` values past the convergence
point produce byte-identical output, and neither summary statistics nor
a hillshade will reveal that (project one was misled by exactly this,
twice).
"""
import hashlib
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
DEM_DIR = ROOT / "output" / "dem"
# The ALIGNED vendor raster, rebuilt on the same explicit grid the SMRF
# runs use. dem_VENDOR_3m.tif is 335x334 on its own point-derived extent
# and is NOT cell-aligned to them -- masking one against the other is a
# shape error at best and a silent half-cell offset at worst.
VENDOR = DEM_DIR / "dem_VENDOR_3m_aligned.tif"

CREST_ABOVE = 2.0    # m above marsh median defining the crest mask
MARSH_BAND = 0.15    # m either side of marsh median defining the control


def load(path):
    ds = rasterio.open(path)
    a = ds.read(1).astype("float64")
    a[a == ds.nodata] = np.nan
    return a


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(tags):
    from dump import Dump
    dump = Dump(
        "window_sweep",
        "SMRF `window` sweep -- does the L-67A embankment crown survive?",
        {
            "reference": VENDOR.name,
            "crest mask": f"vendor > marsh median + {CREST_ABOVE} m",
            "why that threshold": "selects the crown, not the flanks; flanks "
                                  "are where SMRF's slope term bites and would "
                                  "blend two effects into one number",
            "marsh control": f"|vendor - marsh median| <= {MARSH_BAND} m",
            "why a control": "if flat terrain also moves, the crest number "
                             "cannot be read on its own",
            "kept% definition": "fraction of crest cells retaining >50% of "
                                "their vendor height above marsh",
            "checksums": "reported because two windows past SMRF convergence "
                         "give byte-identical output, invisible to stats",
        })
    dump.__enter__()
    vendor = load(VENDOR)
    marsh_z = float(np.nanmedian(vendor))
    crest = vendor > (marsh_z + CREST_ABOVE)
    marsh = np.abs(vendor - marsh_z) <= MARSH_BAND

    print(f"reference : {VENDOR.name}")
    print(f"marsh datum (vendor median) : {marsh_z:.3f} m")
    print(f"crest mask : vendor > marsh + {CREST_ABOVE} m  -> "
          f"{int(crest.sum()):,} cells ({100*crest.sum()/crest.size:.2f}% of tile)")
    print(f"marsh mask : |vendor - marsh| <= {MARSH_BAND} m -> "
          f"{int(marsh.sum()):,} cells")
    print(f"vendor crest height above marsh : "
          f"{float(np.nanmedian(vendor[crest]) - marsh_z):.3f} m")

    print("\n" + "=" * 88)
    print(f"{'tag':<22} {'crest z':>9} {'above':>8} {'kept%':>7} "
          f"{'marsh z':>9} {'drift':>8}  md5")
    print("=" * 88)

    rows = []
    for tag in tags:
        path = DEM_DIR / f"dem_{tag}.tif"
        if not path.exists():
            print(f"{tag:<22} MISSING")
            continue
        a = load(path)

        cz = float(np.nanmedian(a[crest]))
        above = cz - marsh_z
        # Fraction of the crest that retained most of its height -- a
        # median can stay high while half the crest is destroyed.
        vendor_above = vendor[crest] - marsh_z
        run_above = a[crest] - marsh_z
        with np.errstate(invalid="ignore"):
            kept = float(np.nanmean(run_above > 0.5 * vendor_above)) * 100.0

        mz = float(np.nanmedian(a[marsh]))
        drift = mz - marsh_z

        rows.append((tag, above, kept, drift, md5(path)))
        print(f"{tag:<22} {cz:>9.3f} {above:>8.3f} {kept:>6.1f}% "
              f"{mz:>9.3f} {drift:>+8.3f}  {rows[-1][4]}")

    print("=" * 88)

    # Byte-identity check: the failure mode that fooled project one twice.
    seen = {}
    dupes = []
    for tag, _, _, _, h in rows:
        seen.setdefault(h, []).append(tag)
    for h, group in seen.items():
        if len(group) > 1:
            dupes.append(group)
    if dupes:
        print("\nBYTE-IDENTICAL OUTPUTS (window had NO effect between these):")
        for g in dupes:
            print(f"  {' == '.join(g)}")
        print("  A window sweep only tests something where outputs differ.")
    else:
        print("\nAll outputs are byte-distinct: every window value changed the result.")

    return rows


if __name__ == "__main__":
    tags = sys.argv[1:] or [
        "w6_s0.05_t0.15", "w12_s0.05_t0.15",
        "w25_s0.05_t0.15", "w50_s0.05_t0.15",
    ]
    main(tags)
