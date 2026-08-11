# Vendor baseline characterization — S-151 / Miami Canal at L-67A

Tile `USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz`
(FL_Southeast_2018_D18_SUPPLEMENTAL, acquired 2018, published 2019-10-15).
1 km x 1 km, 16,889,632 points.

**Site**: SFWMD structure S-151, -80.509853, 26.011511 (WGS84), from SFWMD's
AHED Structures layer. Record corroborates independently: STRUCTURETYPE=CULVERT,
CANAL=MIAMI CANAL, NUMBER_COMPONENTS=6 (the six 84-inch culverts), SFWMD-owned,
active.

**Coverage**: this is the ONLY 3DEP LPC tile in existence containing S-151.
The 2024 `FL_MiamiDade_D23` collection reaches within ~0.5 mi but its coverage
steps eastward going north and S-151 falls in the gap -- consistent with the
acquisition stopping at the county line / WCA-3 boundary. Remaining coverage is
2007. There is no vintage choice at this site.

## CRS and datum -- none of Arizona's assumptions carry over

| | Project 1 (San Xavier) | Here |
|---|---|---|
| Horizontal | EPSG:6405 Arizona Central, International FEET | **EPSG:6350 NAD83(2011) Conus Albers, METRES** |
| Vertical | NAVD88 / Geoid12A (undeclared in header, sourced from sealed report) | **NAVD88 / Geoid12B, declared in the header** |

Conus Albers is an equal-area continental projection, not a state plane zone --
Florida East ftUS was the natural guess and would have been wrong.

## Relief -- the header is useless, ground is what matters

| Measure | Value |
|---|---|
| Header Z range (all points) | -10.08 .. 1276.11 m (1286 m) |
| Excluding noise classes 7/18 | 1.55 .. 1272.04 m -- still meaningless |
| **GROUND (class 2) only** | **1.63 .. 5.36 m (3.73 m range)** |
| **Ground p1-p99** | **2.05 .. 4.86 m = 2.81 m (9.2 ft) across the whole tile** |

Noise-class filtering alone does NOT recover a sane range here; only filtering
to ground does. Recording that because the Tucson tile's equivalent problem WAS
solved by dropping classes 7/18, and the same move fails on this tile.

## Classification -- the inversion

| Class | Count | Share |
|---|---|---|
| 1 unclassified | 15,630,210 | 92.543% |
| 2 ground | 1,255,203 | **7.432%** |
| 20 (reserved/other) | 2,025 | 0.012% |
| 9 water | 1,566 | 0.009% |
| 7 low noise | 468 | 0.003% |
| 18 high noise | 160 | 0.001% |

San Xavier was 70.9% ground. Here it is 7.4%. All returns are 16.89 pts/m2
(QL1-class, 4.5x denser than San Xavier) but **ground is only 1.26 pts/m2** --
denser data, far less usable ground.

Returns: 24.74% multi-return, mean NumberOfReturns 1.2659, 87.33% last/only.

## Per-cell ground coverage (binmode=true)

`binmode: true` used from the outset -- project 1 found PDAL's default
radius-based counting inflates density ~6x, which at 1.26 pts/m2 would be
badly misleading. Raster total (1,255,203) matches the header class-2 count
exactly, confirming true binning.

At 1 m cells: mean 1.253, median 1.0, max 22.
- 47.11% of cells hold **zero** ground points
- 69.02% hold <= 1
- 81.80% hold <= 2

## Why cells are empty -- two different failures

| Cause | Share of tile |
|---|---|
| No returns at all (water dropout) | 6.07% |
| Returns present, none classified ground (vegetation) | 41.10% |
| Ground present | 52.89% |

These are not one "void" class and should not be treated as one. 95.7% of
dropout area sits in clusters >100 m2 (largest 36,752 m2) -- water bodies, i.e.
the canals, not scattered noise. Of the 1,566 water-class points, 79.6% fall in
cells with no ground.

## Cell size vs coverage -- this sets the SMRF parameters

| cell | no ground point | median pts/cell | cells with >=3 | no returns at all |
|---|---|---|---|---|
| 0.5 m | 76.79% | 0.0 | 1.5% | 7.24% |
| 1.0 m | 47.04% | 1.0 | 18.3% | 6.06% |
| 2.0 m | 18.11% | 3.0 | 56.6% | 5.29% |
| 3.0 m | **8.31%** | 8.0 | 79.2% | 4.72% |
| 5.0 m | **4.63%** | 22.0 | 93.9% | 3.79% |
| 10.0 m | 2.21% | 89.0 | 97.4% | 1.98% |

The vegetation-driven gap closes by 3-5 m. The water floor does not -- it is
irreducible, and by 5 m the two curves nearly converge (4.63% vs 3.79%), meaning
almost every remaining empty cell is genuine water rather than missing ground.

**Consequence for SMRF**: San Xavier's cell of 3.3 ft (~1.0 m) would leave 47%
of cells with no ground point. A 3-5 m cell is the defensible range here, chosen
from measured coverage rather than carried over.

## Is the vendor surface usable?

Conditionally. At 1 m it is not -- half the cells are interpolated from nothing
nearby. At 3-5 m it is usable across ~95% of the tile, with the residual being
open water where no bare-earth surface exists to measure. Any deliverable must
state that distinction rather than presenting an interpolated water surface as
terrain.
