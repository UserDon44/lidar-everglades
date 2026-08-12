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
a median **2.374 m** where there is open water (cells with zero returns
at 3 m, aligned vendor surface). *Corrected 2026-08-11 from "~2.28 m",
which reproduces under no tested definition and whose method was never
recorded — see qc_memo §4.* Any deliverable must state that rather
than presenting an interpolated water surface as terrain.

## STATUS: complete (2026-08-11)

Deliverable standard reached. `output/reports/qc_report.pdf` (17 pp),
`README.md`, `qc_memo.md`, `parameter_derivation.md`, six figures, ten
measurement dumps, permission policy and two hooks. Public GitHub remote.

Nothing is half-finished. The two items not done are both deliberate and
recorded with reasons: the edge effect stays unquantified (see the scope
decision at the end of this file), and `scalar` remains inherited rather
than validated, labelled as such everywhere it appears.

If this project is picked up again, the honest next steps are: validate
`scalar` against this tile, or take the extent-matched edge measurement.
Neither is required for the deliverable to stand.

## Next steps, in order

**1. ~~Paginated-API helper~~ — DONE (2026-08-11).** See "RESOLVED:
paginated-API helper" below. `scripts/fetch_api.py` + a live verification
suite; use it for every API query from here.

**2. ~~Derive `window` / `slope` / `threshold`~~ — DONE (2026-08-11).**
Full derivation in `output/reports/parameter_derivation.md`; summary and
the retracted first attempt below.

**3. ~~QC against the vendor surface~~ — DONE (2026-08-11).**
`output/reports/qc_memo.md`. See "RESOLVED: QC" below.

**4. Next**: figures for the memo (`output/figures/`, scale bar, north
arrow, unit-labelled legend), then decide whether this becomes a PDF
deliverable like project one's.

## RESOLVED: QC vs. vendor (2026-08-11)

`scripts/qc_vs_vendor.py`. **Agreement between two classifications, NOT
accuracy** — there is no external control on this tile and no USGS
vertical accuracy report for this collection. Do not quote these as
RMSEz.

| region | cells | share | mean | median | RMSE |
|---|---|---|---|---|---|
| pooled | 110,889 | 100% | +0.032 | +0.038 | 0.111 |
| **marsh** | 104,947 | 94.6% | **+0.038** | +0.039 | **0.081** |
| crest | 706 | 0.64% | −0.710 | −0.911 | 0.963 |
| water | 5,236 | 4.72% | +0.027 | +0.028 | 0.069 |

**Marsh RMSE 0.081 m is the number.** The pooled row blends real ground
agreement with a known truncation and with two interpolations across
ground nobody measured — never quote it. The water row measures only
that two interpolations were computed similarly; the canal shows ~2.28 m
where there is open water, and must not be presented as bathymetry.

Regions are disjoint: water = zero returns of any kind (binmode count,
`count_allret_3m_aligned.tif`), crest = vendor > marsh + 2.0 m (same mask
as `measure_window_sweep.py`), marsh = the rest.

**Crown truncation ACCEPTED and documented** (user decision, 2026-08-11).
Crest sits a median 0.911 m / mean 0.710 m below vendor; median crest
height above marsh falls 2.369 → 1.612 m. The two requirements are
irreconcilable in one parameter set — marsh coverage needs `cell` ≥ 3 m
(47.04% of 1 m cells hold no ground return), a 6–8 m crown needs
`cell` ≤ 1.5 m — and that conflict **is the finding**, not a tuning
failure.

**No dual-cell composite.** It would trade a measured, bounded,
documented limitation for an undocumented seam along a boundary that
would itself need justifying — repeating project one's edge-effect
problem in a new form. Do not revisit this without a reason that
addresses the seam.

## RESOLVED: SMRF parameters (2026-08-11)

Working set — `dem_w3_s0.05_t0.15.tif`, md5 `ab0bebaf…`:
`cell` 3.0 m · `window` 3.0 m · `slope` 0.05 · `threshold` 0.15 m ·
`scalar` 1.25 (inherited) · ELM 10.0 m / 1.0 m · `res` 3.0 m.

Five of eight measured from this tile, one explicitly inherited without
validation, two reasoned defaults on a low-impact stage. Built by
`scripts/run_smrf.py` (local to this project — project one is frozen and
its outputs would land in its tree).

**A prediction was made and refuted; this is the important part.**
`window` was first derived from the embankment's recorded 32–46 m width,
predicting the levee would survive below 12 m and be destroyed above
25 m. The sweep showed it **already destroyed at the smallest window
tested** (6 m → 0.797 m crest against the vendor's 2.369 m), and moving
by only 0.12 m across an 8× range.

The mechanism was read correctly — 25 m and 50 m came back
**byte-identical**, putting convergence between 12 and 25 m exactly where
`ceil(window/cell)` says. It was applied to the wrong number. The
32–46 m figure was thresholded 0.3–1.5 m above marsh, i.e. the levee's
**base**; opening acts on width *at the height being cut*, and a levee is
a wedge. Measured properly the crown is **6.0–8.5 m** at 2.5–2.75 m
height — 2–3 px at `cell = 3 m`, narrower than SMRF's smallest possible
structuring element (9 m). **No window at this cell size can preserve
it.** Same class of error as project one's retracted seam finding, and
findable only because the original width measurement had its threshold
recorded alongside it.

**The competing explanation was tested, and split.** Re-derived from the
crown, `w3` (cell 3) and `w3` (cell 1.5) were predicted and both hit —
1.612 m / 72.4% and 1.989 m / 99.6%. Since a confirmed prediction is not
verification, the rival hypothesis (a smaller SE simply under-filters
everywhere) was measured over marsh cells with the embankment plus a
30 m buffer excluded:

| | marsh bias | marsh RMSE | marsh >0.15 m |
|---|---|---|---|
| window 3→50 m | +0.0414–0.0416 m | 0.048–0.050 m | 0.10–0.15% |
| **cell 1.5 m** | **+0.0637 m** | **0.0760 m** | **2.34%** |

**Rejected for `window`** — identical to four decimals across an 8×
range, so the effect is genuinely confined to SE scale. **Confirmed for
`cell`** — the finer cell buys its crown back with a 15× increase in
marsh cells sitting above the vendor surface (2.34% vs 0.15%). Its crest number alone
would have recommended it.

**Four limitations, none tunable away**: levee crown truncated ~0.76 m
(resolution floor); bank flanks classified non-ground (`slope` set from
the marsh, surface is bimodal); ground/vegetation overlap irreducible
(40.6% of unclassified within 0.15 m of ground); open water is absence,
not error (6.07%, interpolated across — must not be shown as measured
terrain).

**Grid alignment fixed here too.** `dem_VENDOR_3m.tif` was sized from its
own point extent (335×334) and is not cell-aligned to the SMRF runs
(333×333 on an explicit origin). `scripts/build_vendor_aligned.py`
rebuilds it on the identical grid — rebuilt rather than warped, to avoid
resampling the surface the crest mask is derived from. Use
`dem_VENDOR_3m_aligned.tif` for any comparison.

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


## RESOLVED: the characterization reproduces (2026-08-11)

`scripts/characterize_vendor.py` re-derives the vendor baseline from the
point cloud and checks every value against what the memo claims, rather
than silently recomputing. Dump: `output/reports/vendor_characterization.txt`.

**22 of 25 match.** The foundation of this project — the cell-size sweep,
the two void classes, the density and relief figures — reproduces
exactly. Three did not, and none was a mistake in the underlying work:

| quantity | memo | re-derived | cause |
|---|---|---|---|
| slope p90 | 2.33% | 2.318% | computed on the **original** 335×334 grid, not the aligned 333×333 |
| slope max | 50.8% | 51.088% | same |
| canal elevation | 2.28 m | **2.374 m** | **does not reproduce** — no recorded method |

The slope figures are correct *for the grid they were computed on*; both
grids are now reported and the memo says which. The canal figure is a
genuine loss: median 2.374, mean 2.365, largest-body 2.381, p25 2.344 —
none is 2.28, and its definition was never written down. Same failure as
the predecessor project's CHM cluster count.

**A wrong-baseline error was caught by the number audit**, not by review:
the memo claimed cell 1.5 m produced a "23× increase" in marsh cells
above vendor. 23× is 2.34% ÷ 0.10%, but 0.10% is the `w6`–`w50` tail —
the delivered run is `w3`, tail 0.15%, giving **15×**. Corrected
everywhere. The conclusion stands; only its magnitude was inflated.

## The deliverable-number audit was INERT for this project's whole life

**Every deliverable in this repo was produced without the automated
number check running.** Discovered 2026-08-12.

The hook was built here, tested here, and found four real defects in
itself here — and it was then wired in a way that never executed. Both
hooks were invoked as `"$CLAUDE_PROJECT_DIR/.claude/hooks/x.py"`, relying
on the `#!/usr/bin/env python3` shebang. On this machine that resolves to
the Windows Store stub: `"Python was not found"`, exit 49. A `PreToolUse`
hook exiting non-2 is a *non-blocking* error, so `guard_destructive.py`
silently did not guard either.

`.claude/hooks/last_number_audit.txt` does exist in this repo, which
looks like evidence the hook ran. **It is not.** It was written by
running the script by hand during development, not by the hook firing.

**This does not invalidate the audits — they were run.** The 172-number
sweep happened and its findings stand. The `23×` → `15×` baseline error
(wrong denominator: the `w6`–`w50` tail at 0.10% instead of the delivered
run's 0.15%) was caught by a **manual** run of the audit, not by the hook
firing on save. Same for the `58%` → `53%` fix in
`parameter_derivation.md`.

So: the coverage was real but **manual and one-off**, not automatic and
per-write. Recording it so no later session assumes otherwise.

Fixed by invoking an explicit interpreter path. Verified firing live
afterwards, not merely configured.

## Gitignore does not apply to already-tracked files

Found 2026-08-11 in the portfolio repo. `.claude/` had been gitignored
for the whole project, yet `.claude/settings.local.json` was in version
control — committed in `8013a91` before the ignore rule existed. Once a
path is tracked, `.gitignore` is irrelevant to it, silently and forever.

What was in there: 40+ one-off allow rules accumulated by clicking
through permission prompts, including **`Read(//c//**)`** — permission to
read the entire C: drive — sitting in a repository intended to be shown
to employers.

The general trap: adding an ignore rule does not retroactively untrack
anything, and `git status` stays clean, so nothing ever surfaces it. Use
`git ls-files <path>` to check whether a supposedly-ignored path is
actually tracked; `git rm --cached` to untrack while keeping the file.
Worth doing for any path that accumulates machine-generated local state.


## The reference is what keeps being wrong

Three failures across both projects share one shape, and it is worth
naming because none of them was bad arithmetic or invention — every
measurement was computed correctly and compared against the wrong thing:

- the retracted seam finding: baseline pooled across the tile instead of
  per-side, when the east half is flat agriculture and the west has hills
- the `window` derivation: the embankment's **base** width (32–46 m)
  instead of its **crown** (6–8 m), when opening cuts at the height in
  question
- the "23×" vegetation cost: the `w6`–`w50` tail (0.10%) instead of the
  **delivered** `w3` tail (0.15%), which makes it 15×

All three survived review, because review checks the computation and the
computation was fine. The reference sits in the sentence as an
unexamined given. The standing rule now lives in `~/.claude/CLAUDE.md`:
any ratio or delta must justify its denominator, not merely state it.

## The canal figure: a number that could not be adjudicated

`2.28 m` was published for the interpolated canal surface. It reproduces
under no definition tried — median 2.374, mean 2.365, largest-body
2.381, p25 2.344 — and because no mask, statistic or surface was ever
recorded beside it, there is no way to establish whether it was a spot
reading, a different definition, or simply wrong.

That makes it strictly worse than a wrong number: a wrong number gets
corrected, this one could only be discarded and replaced. Recorded here
because the temptation is to treat it as a rounding quibble; it is not.
It is the second instance in this work of exactly this loss, after the
predecessor project's CHM cluster count of 13 with no search radius.


## A confident reading is not a measurement (second instance)

2026-08-11. Looking at the rendered figures, the reviewer proposed that
the green "returns, none ground" strips flanking the canal in fig01 were
the levee crown — the crown truncation seen in classification space
rather than elevation space. It was a good hypothesis: the strips sit
where fig06 shows the embankment, and it would have tied two figures into
one finding.

**Measured and refuted.** Only 6 of 706 crest cells are green (0.85%),
green cells sit at **+0.073 m** above marsh against the crown's
**+2.369 m**, and the crest is *less* green than the tile average (0.8%
vs 3.6%) — the vendor classifies ground on the crown readily, at a median
41 returns per cell. The strips are the vegetated toe and berm flanking
the levee, enriched 9–51 m out from the crest but at marsh elevation.

**How the error was made, since that is the reusable part**: it was
asserted from *spatial proximity across two figures* — the strips are
near where the embankment is — rather than from any measurement relating
the two. That is the same shape as the retracted hill artifact: a
plausible reading of a render, held confidently, never checked against
the underlying data.

This is the second instance of that specific failure, and it is worth
noting the reviewer made it this time and the author made it last time.
Neither direction is protective. **Reviewer confidence is not evidence**,
and "it lines up in the picture" is a hypothesis, not a result. In the
same session the reviewer's *other* two readings — the SE corner being
S-151, and the crown speckle being suspect — were both worth acting on,
and one was confirmed. Good instincts still need the measurement.


## Claude can see images; the limitation is reliability, not perception

Corrected 2026-08-11. This file and the predecessor project's both said,
in effect, "you can't see a hillshade and I can." That is **false** —
images can be read directly with the Read tool, and doing so immediately
caught two defects in fig01 that had survived several rounds of review:
a legend box overprinting the scale bar, and a caption calling a
full-width density band an "SE corner".

The framing was wrong but the *practice* it produced was roughly right,
for a different reason. What is unreliable is not perception, it is
**visual inference**:

- Gross, unambiguous defects — overlapping elements, wrong labels,
  missing colourbars, a blank panel — are caught reliably by looking,
  and looking is much faster than reasoning about the plotting code.
- Structural readings — "this band is the swath boundary", "these
  strips are the levee crown" — are HYPOTHESES. Two have now been wrong:
  the retracted hill artifact and the green-strip reading. Both were
  confident, both were about spatial relationships, both needed one
  measurement to settle.
- Subtle comparisons between similar images are the worst case and
  should not be attempted at all. The predecessor project's two
  hillshades were BYTE-IDENTICAL and were confidently described as
  differing. Use checksums.

So the rule becomes: **look at every figure produced, before sending
it** — it is cheap and catches real defects. But treat anything inferred
from looking exactly as one would treat a reviewer's impression: worth
acting on, never sufficient on its own. The measurement still decides.


## SCOPE DECISION: the edge effect stays unquantified (2026-08-11)

Deliberate, not an oversight. Recording the reasoning so a later session
does not "fix" it.

The tile-edge effect could be measured with an extent-matched design:
inject dummy points at the extended bounding-box corners of both the
buffered and unbuffered runs, classified 7 so SMRF ignores them, so both
see identical extents and identical internal grid phase, leaving the
neighbour points as the only difference. That would work. It was not
built.

**Why not.** What the memo currently says is that buffered and unbuffered
runs are not comparable cell-by-cell, because `filters.smrf` and
`filters.elm` anchor their internal rasters to the extent of the points
they receive — demonstrated by shifting the extent 1.5 m with no buffer
at all and changing 93.1% of cells more than 200 m away. That is a
*measured mechanism*, and it is a stronger statement than a number would
be. Compare the predecessor project, which asserted an edge-effect
limitation it had never tested and then justified not testing it with a
claim that turned out to be false.

Adding a magnitude to something already honestly characterised buys
little: the reader already knows the effect exists, knows why it cannot
be read off a naive comparison, and knows SMRF carries an intrinsic
0.055 m sensitivity to where the tile boundary falls. The number would
be nice to have and changes no decision.

**Revisit if** a deliverable ever needs a stated edge tolerance, or if
multiple adjacent tiles are mosaicked for real — at which point the
extent-matched design above is the way to get it.


## RESOLVED: hydrology — D8 ruled out by measurement (2026-08-11)

`scripts/analyze_hydrology.py`, dump `output/reports/hydrology.txt`,
memo section 8.

**D8 does not apply here, and that is the finding.** The quantity that
decides which neighbour a cell drains to is the gap between its steepest
and second-steepest descent. Across 99,581 marsh cells that gap has a
**median of 0.004 m**, and **99.6%** of cells fall below the 0.081 m
marsh noise floor. The steepest descent itself is median 0.017 m, with
92.5% below the noise floor and 84.0% below the 0.055 m grid-phase
sensitivity alone.

So a flow network here would be computed from differences an order of
magnitude below the surface's own uncertainty. It would look entirely
plausible — dendritic, connected, confident — and be a map of noise.

**This ties directly to §7.6.** The 0.055 m grid-phase sensitivity
exceeds the steepest descent at 84% of marsh cells, so shifting the tile
boundary 1.5 m would rearrange the network. A result that moves when the
tile boundary moves is not a property of the landscape.

**The structural argument is worse than the precision one.** S-151 is a
culvert: its whole function is passing water *through* the levee, under
control, in whichever direction operations require. A DEM shows an
unbroken barrier, so terrain routing would send flow around the one
feature the site exists for. Flow direction is set by gates, not
gradient, and can reverse; and the canal bed is unmeasured because water
absorbs the pulse, so conveyance capacity is unavailable rather than
uncertain.

**What was run instead**, both of which survive because they need the
elevation *distribution* rather than local gradients:

- **Stage-area hypsometry.** The system is a knife edge: 30 cm of stage
  (2.30 → 2.60 m) takes the tile from 5% to 94% inundated, peaking at
  2.40 m where each additional centimetre floods 6.90 ha. Half the tile
  lies below 2.407 m and three quarters below 2.489 m — 25% of the area
  inside an 82 mm band. Not tied to a gauge: NAVD88/Geoid12B against
  SFWMD's NGVD29 is ~1.5 ft and deserves separate deliberate treatment.
- **Levee crest profile, on the VENDOR surface.** 625 m of crest, varying
  0.719 m, minimum 4.569 m. Computed on the vendor's classification
  because ours truncates the crown by a median 0.911 m (§7.1) — which is
  exactly what a crest profile measures. Using the better input for one
  specific analysis, and stating why, is the correct call.

**Do not add D8 later to match project one's structure.** The absence is
the result.


## Environment bootstrap is a shared module, not a copy-paste

`scripts/env_bootstrap.py`. Import it **before** numpy, rasterio or
matplotlib:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_bootstrap  # noqa: F401  -- MUST precede numpy/rasterio
```

Without it, this env's python.exe fails at the first native-extension
import with **exit 127 and no traceback** — a loader-level DLL resolution
failure, not a Python exception, so the script prints nothing and looks
like it did nothing. Python 3.8+ on Windows ignores PATH for extension
DLLs, so `os.add_dll_directory` is required; PATH is still set because
the GDAL/PDAL command-line tools and subprocess calls need it.

It is a bare import with a side effect rather than a function to call,
because a function would be too late if the caller had already imported
numpy above it.

**Extracted after the fourth independent rediscovery** — render_figures,
render_3d, render_personal, analyze_hydrology — each added only after
that script silently exited 127, in one case after a full analysis had
been written and appeared to produce nothing. Both repos now carry the
same module. The env path is hardcoded for this machine; resolving it
from `sys.executable` is the portable version and is deferred rather
than guessed.

---

# PROJECT COMPLETE

Nothing further is being added. Final state:

**Deliverables** — `output/reports/qc_report.pdf` (23 pp), `README.md`,
`qc_memo.md` (9 sections), `parameter_derivation.md`, eleven figures,
eleven measurement dumps. Public-ready; repo is private pending a
visibility flip.

**What the project actually demonstrates**, since the retractions
outnumber the clean results and could read as chaos rather than method:
a defensible bare-earth surface with agreement quantified by region,
limitations measured rather than hedged, and every published number
traceable to a dump recording the choices behind it.

**Four findings worth carrying forward:**

1. Coverage, not density, sets resolution — 16.89 pts/m² of returns
   against 1.26 pts/m² of ground, and cell size derived from a sweep.
2. The crown truncation is a resolution floor, not a tuning failure, and
   the two requirements behind it are irreconcilable.
3. SMRF anchors its internal grid to the input extent, so a 1.5 m
   boundary shift changes 93.1% of cells 200 m away.
4. D8 does not apply here, measured: a 0.004 m median direction-deciding
   gap against a 0.081 m noise floor.

**Three retractions, each caught by a different mechanism** — a checksum
(the `window` derivation), an automated audit (23× → 15×), and a
re-derivation script written to test the foundation (the 2.28 m canal
figure, which could only be discarded). All share one shape: a correct
measurement compared against the wrong reference.

**Deliberately not done**, with reasons recorded: the edge-effect
magnitude (a measured mechanism beats an asserted number), `scalar`
validation (inherited, labelled as such), and the NGVD29 gauge tie
(~1.5 ft offset deserving its own treatment).

---

## POST-COMPLETION RECORD (2026-08-11, after the closeout above)

Nothing in the deliverable changed. These are state and boundary facts a
later session needs.

### Repository is public

`github.com/UserDon44/lidar-everglades`, flipped from private after the
PDF was assembled. Verified by an **anonymous** API call rather than from
a logged-in page: a private repo 404s to an unauthenticated request, so
the call succeeding is itself the proof. `private: false`,
`visibility: public`, default branch `main`. Project one is public too.
Confirmed the README, the PDF and all eleven measurement dumps are
visible to a stranger, and that origin and local sit at the same commit.

The repo description field is still unset. It is what shows under the
name in search results and on the profile — left alone because it is a
presentation choice rather than a technical one.

### Personal renders: the boundary, and what it does NOT mean

A standalone toolkit now lives at `C:/Users/ryans/terrain-renders/` —
`render.py`, `animate.py`, `env_bootstrap.py`, `out/`. It sits outside
both repos, imports nothing from them, writes nothing into them, and
takes any GeoTIFF via `--dem`, so it can read project data without the
projects depending on it. Personal renders go there from now on.

**`scripts/render_personal.py` and `render_personal_batch.py` stay in
both repos deliberately.** I proposed removing them, reasoning that
personal work should not sit in a portfolio repo. That was wrong, and the
correction is the part worth keeping: **it is a rendering engine, not
personal content.** The looks, light rigs, void trimming and
camera-relative lighting are generally useful, including for accurate
project work. What made the *output* non-deliverable was the exaggeration
and disclosure choices, not the tool that produced them. Do not remove
these later on tidiness grounds.

`output/renders_personal/README.md` remains the marker on the output
side, and `render_3d.py` remains the documentary renderer with mandatory
VE disclosure. **The separation is about disclosure, not about which
directory a script sits in.**

### PyVista: never call enable_ssao() inside a frame loop

Found while building an animated flyaround. `enable_ssao()` rebuilds the
render-pass stack and **silently resets the camera**, so all 180 frames of
an orbit came out byte-identical. Pillow then collapsed them into a
single-frame GIF, which made the symptom look like an encoder bug rather
than a camera one. The file was valid, opened fine, and was small — but
small is exactly what a correctly-encoded dark-background GIF looks like,
so size was not diagnostic either.

Configure SSAO once before the loop; per frame set lights and camera and
call `pl.render()`. **Verify animations by frame hash, not by file size
or by the file opening.** Any future animated figure built on
`render_3d.py` would hit the same thing.

### Backups

Both repos mirror to OneDrive (`lidar-portfolio-backup` ~1,775 MB,
`lidar-everglades-backup` ~456 MB) via `xcopy /E /I /H /Y`, which is
additive — it never deletes, so a few superseded files persist there:
two pre-rename `master` refs in each, and one replaced figure in project
two. Git is the authoritative record; the drift is known and accepted.
