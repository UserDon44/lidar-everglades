#!/usr/bin/env python3
"""
Split the tile by PointSourceId and test whether acquisition geometry
explains two anomalies visible in fig01.

WHAT PROMPTED THIS
==================
Reading the coverage figure, the user observed:

  1. All three panels -- all-return density, ground density, and the
     void classification -- are disrupted in the SAME bottom-right
     (south-east) corner. Three independently computed metrics anomalous
     in one place is a property of the source data, not a rendering
     artifact of any one product.
  2. The "returns but no ground" strips flanking the canal run
     continuously until the canal junction and then degrade, most
     visibly on the east leg. Real levee vegetation has no reason to
     change character at a junction; acquisition geometry does.

Both point at flight-line structure, which nothing in this project has
looked at yet.

WHY IT MATTERS BEYOND THE FIGURE
================================
The coverage numbers -- 47.04% of 1 m cells with no ground return, 6.07%
water dropout, 41.10% vegetation-blocked -- are tile-wide averages. If
part of the tile has degraded acquisition, those averages blend good and
bad data, and the cell-size sweep that set `cell = 3.0 m` inherits the
blend. Every parameter in the derivation rests on that sweep.

So this is not a cosmetic question about a figure. It asks whether the
foundation is stratified in a way nobody checked.

METHOD
======
  swath identity : PointSourceId, the standard per-flight-line tag
  overlap        : count of DISTINCT PointSourceIds per cell, which
                   distinguishes single-coverage from overlapped ground
  corner test    : the SE 300 m square vs the rest of the tile, chosen
                   from the visual anomaly BEFORE any statistic was
                   computed, so the region is not fitted to the result
  timing         : GpsTime per swath, and the gaps between swaths, to
                   distinguish a single continuous pass from separate
                   lifts or a turn
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import Dump  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILE = ROOT / "data" / "raw" / "USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz"

XMIN, YMIN, XMAX, YMAX = 1557000.0, 456000.0, 1558000.0, 457000.0
CELL = 10.0                     # coarse grid for swath geometry
CORNER = 300.0                  # SE square side, picked from the figure


def grid_index(x, y, cell):
    cols = ((x - XMIN) // cell).astype(int)
    rows = ((YMAX - y) // cell).astype(int)
    n = int((XMAX - XMIN) / cell)
    ok = (cols >= 0) & (cols < n) & (rows >= 0) & (rows < n)
    return rows, cols, ok, n


def main():
    import laspy

    with Dump(
        "swath_investigation",
        "Flight-line structure, and whether it explains the SE-corner "
        "anomaly and the canal-strip degradation",
        {
            "tile": TILE.name,
            "swath identity": "PointSourceId",
            "overlap metric": "count of distinct PointSourceIds per "
                              f"{CELL:g} m cell",
            "corner region": f"SE {CORNER:g} m square "
                             f"(X >= {XMAX-CORNER:.0f}, Y <= {YMIN+CORNER:.0f})",
            "why that region": "chosen from the visual anomaly in fig01 "
                               "BEFORE computing any statistic, so it is not "
                               "fitted to the answer",
            "timing": "GpsTime range per swath and gaps between swaths",
            "prompted by": "three independent metrics disrupted in the same "
                           "corner, plus canal strips degrading at the "
                           "junction -- both suggest geometry, not terrain",
        },
    ):
        las = laspy.read(TILE)
        x = np.asarray(las.x, dtype="float64")
        y = np.asarray(las.y, dtype="float64")
        psid = np.asarray(las.point_source_id)
        cls = np.asarray(las.classification)
        gps = np.asarray(las.gps_time, dtype="float64")

        ids, counts = np.unique(psid, return_counts=True)
        order = np.argsort(-counts)

        print(f"total points {len(x):,}")
        print(f"distinct PointSourceId values: {len(ids)}\n")
        print(f"{'PSID':>7} {'points':>12} {'share':>7} {'X range':>21} "
              f"{'Y range':>21} {'ground%':>8}")
        print("-" * 82)
        for i in order:
            pid = ids[i]
            m = psid == pid
            gpct = 100.0 * np.mean(cls[m] == 2)
            print(f"{pid:>7} {counts[i]:>12,} {100*counts[i]/len(x):>6.2f}% "
                  f"{x[m].min():>10.0f}-{x[m].max():<10.0f} "
                  f"{y[m].min():>10.0f}-{y[m].max():<10.0f} {gpct:>7.2f}%")

        # ---- GPS timing ------------------------------------------------
        print("\nGPS timing per swath (seconds, adjusted-standard GPS time):")
        print(f"{'PSID':>7} {'t_start':>16} {'t_end':>16} {'duration':>10}")
        print("-" * 54)
        spans = []
        for i in order:
            pid = ids[i]
            m = psid == pid
            t0, t1 = gps[m].min(), gps[m].max()
            spans.append((t0, t1, pid))
            print(f"{pid:>7} {t0:>16.2f} {t1:>16.2f} {t1-t0:>9.1f}s")
        spans.sort()
        print("\ngaps between consecutive swaths, by start time:")
        for a, b in zip(spans[:-1], spans[1:]):
            gap = b[0] - a[1]
            note = ""
            if gap > 60:
                note = "  <-- long gap: separate pass or turn"
            elif gap < 0:
                note = "  <-- overlapping in time (simultaneous coverage)"
            print(f"  PSID {a[2]} -> {b[2]}: {gap:+.1f}s{note}")

        # ---- spatial swath map ----------------------------------------
        rows, cols, ok, n = grid_index(x, y, CELL)
        nsw = np.zeros((n, n), dtype=np.int16)
        for pid in ids:
            m = ok & (psid == pid)
            g = np.zeros((n, n), dtype=bool)
            g[rows[m], cols[m]] = True
            nsw += g.astype(np.int16)

        print(f"\nswaths per {CELL:g} m cell:")
        for k in range(0, nsw.max() + 1):
            share = 100.0 * np.mean(nsw == k)
            print(f"  {k} swath(s): {share:6.2f}% of tile")

        # ---- corner vs rest -------------------------------------------
        cx = np.arange(n) * CELL + XMIN + CELL / 2
        cy = YMAX - (np.arange(n) * CELL + CELL / 2)
        CX, CY = np.meshgrid(cx, cy)
        corner = (CX >= XMAX - CORNER) & (CY <= YMIN + CORNER)

        pt_corner = (x >= XMAX - CORNER) & (y <= YMIN + CORNER)
        area_corner = CORNER ** 2
        area_tile = (XMAX - XMIN) * (YMAX - YMIN)

        print(f"\n{'':-^70}")
        print("SE CORNER vs REST OF TILE")
        print(f"{'':-^70}")
        print(f"{'metric':<34} {'SE corner':>16} {'rest of tile':>16}")
        print("-" * 70)
        n_c = int(pt_corner.sum())
        n_r = int((~pt_corner).sum())
        print(f"{'all-return density (pts/m2)':<34} "
              f"{n_c/area_corner:>16.2f} {n_r/(area_tile-area_corner):>16.2f}")
        gc = int(((cls == 2) & pt_corner).sum())
        gr = int(((cls == 2) & ~pt_corner).sum())
        print(f"{'ground density (pts/m2)':<34} "
              f"{gc/area_corner:>16.3f} {gr/(area_tile-area_corner):>16.3f}")
        print(f"{'ground share of points (%)':<34} "
              f"{100*gc/max(n_c,1):>16.2f} {100*gr/max(n_r,1):>16.2f}")
        print(f"{'mean swaths per cell':<34} "
              f"{nsw[corner].mean():>16.2f} {nsw[~corner].mean():>16.2f}")
        print(f"{'cells with 0 swaths (%)':<34} "
              f"{100*np.mean(nsw[corner]==0):>16.2f} "
              f"{100*np.mean(nsw[~corner]==0):>16.2f}")
        print(f"{'cells with 1 swath (%)':<34} "
              f"{100*np.mean(nsw[corner]==1):>16.2f} "
              f"{100*np.mean(nsw[~corner]==1):>16.2f}")

        psids_corner = np.unique(psid[pt_corner])
        print(f"\nPointSourceIds present in the SE corner: "
              f"{list(psids_corner)}")
        print(f"PointSourceIds present tile-wide          : {list(ids)}")
        missing = sorted(set(ids.tolist()) - set(psids_corner.tolist()))
        if missing:
            print(f"ABSENT from the corner                    : {missing}")

        # ---- coverage stratified by swath count ------------------------
        print(f"\n{'':-^70}")
        print("DOES COVERAGE DEPEND ON SWATH COUNT?")
        print("(the cell-size sweep averages across all of this)")
        print(f"{'':-^70}")
        r1, c1, ok1, n1 = grid_index(x, y, 1.0)
        gmask = cls == 2
        g1 = np.zeros((n1, n1), dtype=bool)
        g1[r1[ok1 & gmask], c1[ok1 & gmask]] = True
        a1 = np.zeros((n1, n1), dtype=bool)
        a1[r1[ok1], c1[ok1]] = True
        # upsample the coarse swath-count grid to 1 m
        up = np.kron(nsw, np.ones((int(CELL), int(CELL)), dtype=np.int16))
        up = up[:n1, :n1]
        print(f"{'swaths in cell':<18} {'cells':>10} {'no ground @1 m':>16} "
              f"{'no returns @1 m':>17}")
        print("-" * 66)
        for k in range(0, int(up.max()) + 1):
            m = up == k
            if m.sum() == 0:
                continue
            print(f"{k:<18} {int(m.sum()):>10,} "
                  f"{100*np.mean(~g1[m]):>15.2f}% "
                  f"{100*np.mean(~a1[m]):>16.2f}%")
        print(f"{'TILE-WIDE':<18} {g1.size:>10,} "
              f"{100*np.mean(~g1):>15.2f}% {100*np.mean(~a1):>16.2f}%")

        np.save(ROOT / "output" / "dem" / "swath_count_10m.npy", nsw)
        print(f"\nswath-count grid saved for figure use "
              f"(output/dem/swath_count_10m.npy, {CELL:g} m)")


if __name__ == "__main__":
    main()
