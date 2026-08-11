#!/usr/bin/env python3
"""
Establish whether 3DEP LPC tiles adjacent to e1557n0456 exist.

WHY THIS SCRIPT EXISTS RATHER THAN A ONE-OFF QUERY
--------------------------------------------------
In the prior project, "this project has zero pairs of spatially-adjacent
tiles, so there is nothing to buffer from" was written into CLAUDE.md,
restated in each document as though it were a property of the data, and
went unchallenged for the entire project. It was false: all eight
adjacent tiles were public the whole time on the same server path. The
limitation had been inherited from the initial download scope and then
laundered into a fact.

So the claim in the QC memo (section 5.5) that edge effects are
"unquantified" must be settled by a query whose result is recorded and
re-runnable, not by an assumption. Either neighbours exist -- in which
case the edge effect is measurable and should be measured -- or they
genuinely do not, in which case that is a real limitation and this
script is the evidence for it.

Uses fetch_api so a truncated page cannot masquerade as "no neighbours."
That failure mode is exactly how a negative like this goes wrong: the
query succeeds, the JSON parses, and the absence looks authoritative.

TILE NAMING
-----------
`e1557n0456` encodes the SW corner in kilometres of EPSG:6350 (Conus
Albers, metres): X 1,557,000 / Y 456,000, on a 1 km grid. The eight
neighbours are therefore e1556-e1558 x n0455-n0457. Verified against the
centre tile's actual LAZ header bounds rather than trusted from the
naming scheme.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_api import tnm_products  # noqa: E402

from pyproj import Transformer

LPC = "Lidar Point Cloud (LPC)"

# Centre tile SW corner, EPSG:6350 metres, from the LAZ header.
CX, CY = 1557000, 456000
STEP = 1000

# Pad the 3x3 ring outward slightly so edge-touching footprints are
# certainly intersected rather than exactly abutted.
PAD = 200


def main():
    xmin, xmax = CX - STEP - PAD, CX + 2 * STEP + PAD
    ymin, ymax = CY - STEP - PAD, CY + 2 * STEP + PAD

    tf = Transformer.from_crs("EPSG:6350", "EPSG:4326", always_xy=True)
    lon0, lat0 = tf.transform(xmin, ymin)
    lon1, lat1 = tf.transform(xmax, ymax)
    # Corners of a projected box do not map to a lat/lon box; take the
    # envelope of all four so nothing is clipped.
    corners = [tf.transform(x, y) for x in (xmin, xmax) for y in (ymin, ymax)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    bbox = (min(lons), min(lats), max(lons), max(lats))

    print("3x3 ring around e1557n0456")
    print(f"  EPSG:6350 box : X {xmin}-{xmax}  Y {ymin}-{ymax}")
    print(f"  WGS84 bbox    : {bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f}\n")

    items = tnm_products(bbox=bbox, datasets=LPC)
    print(f"\n{len(items)} LPC products intersect the ring\n")

    # Expected neighbour names.
    wanted = {}
    for i, dx in enumerate((-1, 0, 1)):
        for j, dy in enumerate((-1, 0, 1)):
            e = (CX + dx * STEP) // 1000
            n = (CY + dy * STEP) // 1000
            wanted[f"e{e:04d}n{n:04d}"] = (dx, dy)

    found = {}
    for it in items:
        title = it.get("title", "")
        for key in wanted:
            if key in title:
                found.setdefault(key, []).append(it)

    label = {(-1, 1): "NW", (0, 1): "N", (1, 1): "NE",
             (-1, 0): "W", (0, 0): "CENTRE", (1, 0): "E",
             (-1, -1): "SW", (0, -1): "S", (1, -1): "SE"}

    print(f"{'position':<8} {'tile':<14} {'status':<12} {'size':>10}  project")
    print("-" * 90)
    edge_sharing = []
    for key, (dx, dy) in sorted(wanted.items(), key=lambda kv: (-kv[1][1], kv[1][0])):
        pos = label[(dx, dy)]
        if key in found:
            it = found[key][0]
            size = it.get("sizeInBytes") or 0
            proj = it.get("projectName") or ""
            print(f"{pos:<8} {key:<14} {'PRESENT':<12} "
                  f"{size/1e6:>8.1f} MB  {proj}")
            if abs(dx) + abs(dy) == 1:
                edge_sharing.append((pos, key, it))
        else:
            print(f"{pos:<8} {key:<14} {'absent':<12} {'':>10}")
    print("-" * 90)

    print(f"\nEdge-sharing neighbours present: {len(edge_sharing)} of 4")
    for pos, key, it in edge_sharing:
        url = it.get("downloadURL") or it.get("urls", {}).get("LAZ", "")
        print(f"  {pos:<3} {key}  {url}")

    if not edge_sharing:
        print("""
  NO edge-sharing neighbours exist in 3DEP for this tile. The edge-effect
  limitation in the QC memo is therefore REAL, not inherited from a
  download scope -- and this query is the evidence. Record the bbox above
  alongside the claim.""")
    else:
        print("""
  Edge-sharing neighbours DO exist. The memo must not call the edge
  effect merely "unquantified" -- it is measurable, and the prior
  project's mistake was to leave exactly this untested.""")

    return edge_sharing


if __name__ == "__main__":
    main()
