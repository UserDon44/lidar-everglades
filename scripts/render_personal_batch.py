#!/usr/bin/env python3
"""
Batch driver for the PERSONAL / NON-DELIVERABLE render set (Everglades).

The L-67A corridor is 3.2 m of relief over 348 m -- 0.9% true slope. It
needs exaggeration an order of magnitude beyond anything defensible, which
is exactly what this folder is for. Nothing here may be cited; see
output/renders_personal/README.md.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_personal import render, OUT_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "output" / "dem"

CORR = DEM / "corridor_L67A_3m.tif"
VEND = DEM / "corridor_L67A_VENDOR_3m.tif"
FULL = DEM / "dem_w3_s0.05_t0.15.tif"

JOBS = [
    (CORR, "ember",   25, 205, 10, 1.45, 1, True, "corridor_ember_ve25_az205"),
    (CORR, "magma",   35, 160,  7, 1.40, 1, True, "corridor_magma_ve35_az160"),
    (CORR, "noir",    30, 250,  6, 1.40, 1, True, "corridor_noir_ve30_az250"),
    (CORR, "golden",  22,  20, 14, 1.50, 1, True, "corridor_golden_ve22_az20"),
    (CORR, "ice",     28, 300,  9, 1.45, 1, True, "corridor_ice_ve28_az300"),
    # the vendor surface, for the same corridor -- sharper crest
    (VEND, "ember",   25, 205, 10, 1.45, 1, True, "corridor_vendor_ember_ve25_az205"),
    # whole tile, absurd exaggeration, canals as canyons
    (FULL, "magma",   45, 200, 11, 1.35, 1, True, "fulltile_magma_ve45_az200"),
    (FULL, "noir",    60, 250,  6, 1.30, 1, True, "fulltile_noir_ve60_az250"),
    (FULL, "verdant", 40, 120, 16, 1.40, 1, True, "fulltile_verdant_ve40_az120"),
]


def main():
    t0 = time.time()
    ok = fail = 0
    for (dem, look, ve, az, el, dist, dec, trim, name) in JOBS:
        if not Path(dem).exists():
            print(f"  SKIP {name}: missing {Path(dem).name}")
            continue
        try:
            render(Path(dem), look, ve, az, el, dist, dec,
                   [2200, 1400], OUT_DIR / f"{name}.png", trim=trim)
            ok += 1
        except Exception as exc:
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
            fail += 1
    print("")
    print(f"{ok} rendered, {fail} failed, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
