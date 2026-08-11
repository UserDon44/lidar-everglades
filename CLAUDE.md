# LiDAR Processing — Everglades / S-151, Miami Canal at L-67A

## What this project is
Second portfolio project, following `lidar-portfolio` (San Xavier, AZ —
complete). The claim here is **adapting the same pipeline to a
fundamentally different physical regime**, not a parameter sweep or a
method comparison: near-zero relief, engineered drainage cutting across
natural sheet flow, water bodies that produce *absence* of returns rather
than bad returns, and vegetation sitting centimetres above true ground.

Project 1 stays frozen. Its scripts are the starting point but must be
re-derived against this data, not carried over — see "What inverted".

## CRITICAL: units are METRES

Project 1's standing rule was "never assume metres." Here the trap is
**exactly inverted** — this data is metric and assuming feet would be the
error. The rule is *check*, not "assume feet."

- Horizontal: **EPSG:6350, NAD83(2011) / Conus Albers, metres.** Not a
  state plane zone at all. Florida East (ftUS) was the natural guess and
  would have been wrong.
- Vertical: **NAVD88 height, Geoid12B**, declared in the header.
  NOT Geoid12A (project 1's Arizona value). Declared here, unlike San
  Xavier where it was absent and had to be sourced from a sealed report.

## The site

**SFWMD structure S-151** at the L-67A / Miami Canal intersection,
~20 mi WNW of Miami, on the Broward/Miami-Dade line, bordering WCA-3.

**−80.50985262, 26.01151058** (WGS84), from SFWMD's AHED Structures layer
(`geoweb.sfwmd.gov/agsext1/rest/services/WaterManagementSystem/All_Structures/FeatureServer/4`).

**The working query is `NAME='S151'` — no hyphen.** This is a
correction: the query first recorded here was `NAME LIKE 'S-151%'`,
which matches **zero rows**. The coordinates and attributes recorded
alongside it were always right; the query string beside them was not, so
the provenance did not actually re-derive. Caught 2026-08-11 when
`verify_fetch_api.py` exercised this endpoint and got count 0. Note the
failure shape — a wrong query string returns a *negative*, the same
family as the truncation bug, which is why nothing flagged it. Re-derive
with `scripts/verify_fetch_api.py` (test 5) rather than by retyping.

The record corroborates the site description independently rather than
merely matching a name: `STRUCTURETYPE=CULVERT`, `CANAL=MIAMI CANAL`,
**`NUMBER_COMPONENTS=6`** (the six 84-inch culverts), `OWNER=SFWMD`,
`ISACTIVE=1`, `FIELDSTA=Fort Lauderdale`. Only two records in the
1,178-structure layer match `%151%` at all; the other is `G151W`, a
different culvert on canal L-2W near Clewiston, 40 mi away.

Two gotchas: the endpoint returns **403 without a browser User-Agent**,
and geometry comes back in the layer's own SR unless `outSR=4326` is
passed.

## The tile — and there is no vintage choice

`data/raw/USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz`
- 68 MB, LAS 1.4 point format 6, **16,889,632 points**
- 1 km × 1 km (X 1557000–1558000, Y 456000–457000, Conus Albers metres)
- Acquired 2018, published 2019-10-15

**This is the only 3DEP LPC tile in existence that contains S-151.**
Four projects cover the area: `FL_MiamiDade_D23` (2024 acquisition,
published 2025), `FL_Southeast_2018_D18_SUPPLEMENTAL`, and two 2007
collections. The 2024 collection reaches within ~0.5 mi but **its
coverage steps eastward going north and S-151 falls in the gap** —
consistent with the acquisition stopping at the county line / WCA-3
boundary. Verified by testing each tile footprint against the point, not
by assuming contiguity.

*Method note*: a wide-bbox TNM query returned 300 of 694 items and
therefore reported "no coverage" for the very project that does cover the
site. Always confirm containment with a tight bbox; a truncated page is
not an absence.

## What inverted, relative to San Xavier

| | San Xavier | Here |
|---|---|---|
| Horizontal units | International feet | **metres** |
| Geoid | 12A (undeclared) | **12B (declared)** |
| Ground share of points | 70.9% | **7.4%** |
| All-return density | 3.74 pts/m² | **16.89 pts/m²** (4.5× denser) |
| Ground density | ~2.6 pts/m² | **1.26 pts/m²** (less usable ground) |
| Relief across tile | 164 ft (50 m) | **2.81 m p1–p99** |

Denser data, far less usable ground. Density alone would have been
actively misleading here.

## Relief: only ground filtering recovers a sane range

| Filter | Z range |
|---|---|
| Header (all points) | −10.08 … 1276.11 m |
| Excluding noise classes 7/18 | 1.55 … 1272.04 m — still meaningless |
| **Ground (class 2) only** | **1.63 … 5.36 m** |
| **Ground p1–p99** | **2.05 … 4.86 m = 2.81 m** |

**Dropping classes 7/18 does NOT fix this**, which is a direct contrast
with the Tucson tile where that exact move *was* the fix. The technique
does not transfer; record it so it isn't re-attempted.

## Classification

| Class | Count | Share |
|---|---|---|
| 1 unclassified | 15,630,210 | 92.543% |
| 2 ground | 1,255,203 | 7.432% |
| 20 | 2,025 | 0.012% |
| 9 water | 1,566 | 0.009% |
| 7 low noise | 468 | 0.003% |
| 18 high noise | 160 | 0.001% |

Returns: 24.74% multi-return, mean NumberOfReturns 1.2659, 87.33%
last/only. Vendor gives ground vs unclassified only — no vegetation
breakout, same limitation as San Xavier.

## DONE: vendor baseline + characterization

`output/dem/dem_VENDOR_1m.tif`, `dem_VENDOR_3m.tif` — class-2 only, IDW,
`window_size` 6. Full writeup:
`output/reports/vendor_baseline_characterization.md`.

Density rasters use **`binmode: true`** from the outset — project 1 found
PDAL's default radius counting inflates density ~6×, which at 1.26 pts/m²
would be badly misleading. Verified: raster total (1,255,203) matches the
header class-2 count exactly.

### MEASURED: cell size 3–5 m is the answer

*Method, so this is re-derivable*: the two 1 m `binmode` count rasters
(`density_ground_1m.tif`, `density_allret_1m.tif`, both 1000×1000 over
the full tile) are block-summed by integer factors — 1 m cells aggregate
exactly into 2, 5 and 10 m, and 0.5/3 m were rasterized directly since
they are not integer multiples. "No ground point" is the share of cells
whose ground count is 0; "no returns at all" is the same on the
all-return raster. No interpolation is involved at any step, so these are
counts of observations, not of DEM cells.

| cell | no ground point | median pts/cell | ≥3 pts | no returns at all |
|---|---|---|---|---|
| 0.5 m | 76.79% | 0.0 | 1.5% | 7.24% |
| 1.0 m | 47.04% | 1.0 | 18.3% | 6.06% |
| 2.0 m | 18.11% | 3.0 | 56.6% | 5.29% |
| **3.0 m** | **8.31%** | 8.0 | 79.2% | 4.72% |
| **5.0 m** | **4.63%** | 22.0 | 93.9% | 3.79% |
| 10.0 m | 2.21% | 89.0 | 97.4% | 1.98% |

The vegetation gap closes by 3–5 m; the water floor does not. By 5 m the
two curves nearly converge (4.63% vs 3.79%), meaning almost every
remaining empty cell is genuine open water rather than missing ground.

**San Xavier's cell (3.3 ft ≈ 1.0 m) would leave 47% of cells with no
ground point.** This range is measured, not scaled down.

### MEASURED: two void classes, not one

| Cause | Share of tile |
|---|---|
| No returns at all — water dropout | **6.07%** |
| Returns present, none ground — vegetation | **41.10%** |
| Ground present | 52.89% |

95.7% of dropout area is in clusters >100 m² (largest 36,752 m²) — canals,
not scattered noise. Of 1,566 water-class points, 79.6% fall in cells with
no ground. These require different handling: vegetation is a
classification problem SMRF can attack, water is irreducible absence.

**The vendor DEM at 3 m interpolates straight across the canal**, giving
~2.28 m where there is open water. Any deliverable must state that rather
than presenting an interpolated water surface as terrain.

## Next steps, in order

**1. ~~Paginated-API helper~~ — DONE (2026-08-11).** See "RESOLVED:
paginated-API helper" below. `scripts/fetch_api.py` + a live verification
suite; use it for every API query from here.

**2. Derive `window` / `slope` / `threshold`** — the current task. See
the section below.

## RESOLVED: paginated-API helper (2026-08-11)

`scripts/fetch_api.py` — `tnm_products()` and `arcgis_query()`. Neither
can return a partial list: completeness is proved against an independent
total, or the call raises. `scripts/verify_fetch_api.py` exercises it
against the live APIs (5 tests, all passing).

*Why it was priority one*: a wide-bbox TNM query had returned 300 of 694
items and, on that basis, reported no 3DEP coverage for S-151 — the one
project that does cover it. Caught only because a tighter bbox was run
for an unrelated reason.

**Design decisions, and the measurements behind them:**

- **Both backends reduce to `len(items) == total`.** TNM reports `total`
  in every response; ArcGIS does not, so the helper issues a separate
  `returnCountOnly=true` query *first* and treats it as authoritative
  rather than trusting `exceededTransferLimit` to be present. Two
  different notions of "done" is how one of them ends up quietly wrong.
- **Paging advances by records actually received**, never by the page
  size requested. ArcGIS clamps `resultRecordCount` to its layer
  `maxRecordCount` (2,000 here) without saying so; TNM clamps `max` to
  1,000. A client that assumes it got what it asked for skips records.
- **An empty page is retried, not accepted.** This one is *measured, not
  defensive coding*: TNM returned an empty `items` list with HTTP 200
  and a correct `total` at offset 1,000 of 35,144, and the identical
  request succeeded on a later run — a 14-request burst covering offsets
  0–1,300 produced zero empties. So an empty page is transient, and
  treating it as end-of-data would have silently returned 1,000 of
  35,144 as "complete." Four retries, then raise.
- **An over-broad query is refused, not truncated** (`QueryTooBroadError`,
  default 10,000). A 1.7°-square bbox matches 35,144 LPC products = 352
  requests. Refusing with "narrow the bbox or raise max_items" is honest;
  returning page one is the original bug.

**Live-measured API facts** (re-derive with `verify_fetch_api.py`):

| | value |
|---|---|
| TNM `max` clamp | 1,000 (requesting 2,000 yields 1,000) |
| TNM offset cap | none observed through 1,300 |
| TNM empty-page hiccup | observed once at offset 1,000; not reproducible |
| ArcGIS `maxRecordCount` | 2,000 |
| AHED structures in layer | 1,178 |
| 0.1° bbox around S-151 | 509 LPC products — page 1 is 19.6% of it |

**The reproduction test is the point.** Test 1 confirms a naive page-1
read of a realistic 509-item search still misses all four tiles covering
S-151; test 2 shows the helper finds them from the identical query. Test
3 cripples the pager to prove it raises rather than returning short —
that test matters as much as test 2, because the guarantee is not "we
page correctly," it is "we cannot silently fail to."

## NOT YET DERIVED — the parameter work (step 2 above)

**`window`, `slope`, `threshold` and `scalar` are not set.** Do not carry
San Xavier's values (window 120 ft, slope 0.15, threshold 1.6 ft) or scale
them proportionally — proportional scaling from one number is the same
shortcut whose San Xavier equivalent later had to be retracted.

Measurements already taken to support the derivation:

- **Terrain slope is bimodal**: median 0.489%, p75 1.10%, p90 2.33%,
  p95 4.96%, but p99 **20.4%**, max 50.8%. A flat marsh plane plus
  engineered banks. One `slope` value must serve both; that tension is
  real, not a tuning nuisance.
- **Vegetation obstruction scale ~3 m**: distance from a ground-less cell
  to the nearest ground observation — vegetation-blocked p50 1.00, p90
  1.41, **p99 3.16 m**; water dropout p50 4.47, p90 10.63, p99 14.87 m.
  *Connected-component sizing of vegetation clumps failed* — everything
  merges into one 493 m network, the same failure mode as San Xavier's pad
  footprint. Distance-to-nearest-ground is well-posed regardless of
  connectivity; use it.
- **Features to KEEP**: embankment elongated (279 × 597 m bbox),
  **32–46 m wide**, crest **2.91 m above marsh**, stable across 0.3–1.5 m
  thresholds. Canal cross-section **~32 m** (inscribed radius of the
  dropout body).
- **Ground/vegetation overlap, the threshold problem**: class-2 residual
  about the 3 m surface is std **0.072 m**, p5–p95 spread 0.133 m. But
  unclassified returns sit at p25 +0.050, p50 +0.240 m, with **40.6%
  below 0.15 m** above ground, 56% below 0.30, 70% below 0.50.
  **The populations genuinely overlap** — no threshold separates them
  cleanly. That is a property of sawgrass, not of the parameter.

**`window` cannot be settled by measurement alone.** Vegetation needs
~3 m of reach; the embankment is 32–46 m wide. Whether the embankment is
a feature to erode or terrain to keep decides whether window belongs
below ~30 m or above ~50 m, and only a test answers it. Per project 1's
SMRF mechanism finding, a window sweep is only informative if the tested
values **straddle** that transition — values all on one side will look
like "window doesn't matter" whether or not it does. **Checksum the
outputs**; project 1 was misled twice by eyeballing hillshades.

**`scalar` has no measurement behind it** and would be inherited
(1.25/0.75 in project 1, never independently validated). Say so rather
than presenting it as derived.

## Environment

Same conda env as project 1: `lidar` (miniforge) at
`C:\Users\ryans\miniforge3\envs\lidar\`. Verified in use this session —
without activation there is no working Python on PATH at all (the bare
`python` is the Windows Store stub), so a silent fallback to a system
Python is not possible; anything unactivated fails loudly.

PDAL 2.10.0 · GDAL 3.12.3 · laspy 2.7.0 · rasterio 1.4.4 · pyproj 3.7.2 ·
numpy · scipy · geopandas · matplotlib · pyvista.

**Git Bash gotcha**: `$(pwd)` yields POSIX paths (`/c/Users/...`) that
PDAL cannot open. Generate pipeline JSON from Python with Windows paths.

## Carried from project 1

Scripts in `../lidar-portfolio/scripts/` resolve their root from file
location and are usable here, but:

**`run_dem.py`'s ELM defaults were hardcoded in FEET** (`cell=33.0`,
`threshold=3.3`) inside `build_pipeline()` — a function project 1's
portability inventory had called "generic". Against this metre CRS they
silently request a 33 m cell and 3.3 m threshold. Fixed in project 1
(commit `92b623b`) as **parameters** (`--elm-cell`, `--elm-threshold`,
per-tile keys in `tile_params.json`), not a special case, so project three
inherits the fix. Defaults unchanged and verified to reproduce San
Xavier's DEM byte-for-byte. The rest of `build_pipeline()` was audited at
the same time: `mean_k`/`multiplier` are a count and a sigma multiple,
`window_size` is in cells — all unit-free, so ELM was the only
unit-bearing literal.

Working rules live in `~/.claude/CLAUDE.md` and apply here unchanged.

## Layout

```
lidar-everglades/
  data/raw/            source tile — NEVER modify. Gitignored.
  scripts/pipelines/   generated PDAL JSON (audit trail)
  output/dem/          DEMs + density rasters. Gitignored.
  output/figures/      presentation figures. Gitignored.
  output/reports/      characterization + memos — TRACKED.
  docs/                session-log.md
```
