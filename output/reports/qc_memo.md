# QC Memo — Bare-Earth DEM, S-151 / Miami Canal at L-67A

**Site**: SFWMD structure S-151, L-67A / Miami Canal intersection,
Water Conservation Area 3, Broward / Miami-Dade county line, Florida
**Source**: USGS 3DEP, `FL_Southeast_2018_D18_SUPPLEMENTAL`, tile
`e1557n0456`, acquired 2018, published 2019-10-15
**CRS**: EPSG:6350 — NAD83(2011) / Conus Albers, **metres**
**Vertical**: NAVD88, **Geoid12B** (declared in the LAS header)
**Date**: 2026-08-11

---

## 1. Scope, and what this document does not claim

This memo reports a bare-earth DEM produced from raw returns, and its
**agreement** with the vendor's delivered ground classification.

**It is not an accuracy assessment.** No external vertical control was
used: no NGS marks were sought on this tile, and USGS published no
vertical accuracy report for this collection comparable to the sealed
survey documents available for other projects. Every difference statistic
below compares two independent classifications of the *same* point cloud.
Both could be biased identically and nothing here would reveal it.

A Non-Vegetated Vertical Accuracy figure in the sense of the **ASPRS
Positional Accuracy Standards for Digital Geospatial Data** cannot be
computed from this tile alone; it would require new field survey. The
agreement statistics in §4 are reported as agreement, and should not be
quoted as RMSEz.

## 2. Why this site

The site was selected to invert, rather than repeat, the conditions of a
prior desert project. Figures in the left-hand column are
**[cited: lidar-portfolio CLAUDE.md]** — they were derived in that
project and are quoted here, not re-derived from this tile. Right-hand
figures are measured from this tile.

| | prior site (Sonoran desert) [cited: lidar-portfolio CLAUDE.md] | **this site** |
|---|---|---|
| horizontal units | International feet | **metres** |
| geoid | 12A, undeclared in header | **12B, declared** |
| ground share of returns | 70.9% | **7.4%** |
| all-return density | 3.74 pts/m² | **16.89 pts/m²** |
| **ground** density | ~2.6 pts/m² | **1.26 pts/m²** |
| relief across tile | 50 m | **2.81 m** (p1–p99) |

Denser data, far less usable ground, and 2.81 m of total relief. Aggregate
point density satisfies **USGS LiDAR Base Specification** QL1 thresholds,
but aggregate density is the wrong statistic here: the operative
constraint is *ground* return density at 1.26 pts/m², which is what
drives every parameter in §3.

## 3. Method and parameters

PDAL 2.10.0. Vendor classification is discarded and re-derived, so the
result is independent of the vendor's decisions:

```
readers.las
  -> filters.assign        Classification[:]=0     (strip vendor classes)
  -> filters.elm           cell 10.0 m, threshold 1.0 m
  -> filters.outlier       statistical, mean_k 8, multiplier 3.0
  -> filters.smrf          cell 3.0 m, window 3.0 m, slope 0.05,
                           threshold 0.15 m, scalar 1.25
  -> filters.range         Classification[2:2]
  -> writers.gdal          IDW, 3.0 m, fixed grid 333x333 @ 1557000/456000
```

Five of the eight numeric parameters are measured from this tile; one is
inherited without independent validation and is flagged as such. Full
derivation, including a retracted first attempt at `window`, is in
`parameter_derivation.md`. In summary:

| parameter | value | basis |
|---|---|---|
| `cell` | 3.0 m | **measured** — coverage sweep (§5.1) |
| `window` | 3.0 m | **measured** — crown width vs. structuring element |
| `slope` | 0.05 | **measured** — marsh slope vs. vegetation height |
| `threshold` | 0.15 m | **measured** — ground residual σ vs. vegetation height |
| `scalar` | 1.25 | **inherited, not validated** |
| ELM cell / threshold | 10.0 m / 1.0 m | reasoned; low-impact stage |

Every run writes its pipeline JSON to `scripts/pipelines/` as an audit
trail, and outputs are compared by checksum rather than by eye — two
parameter settings past SMRF's convergence point produce byte-identical
rasters, which neither summary statistics nor a hillshade will reveal.

## 4. Agreement with the vendor surface

`dem_w3_s0.05_t0.15.tif` minus `dem_VENDOR_3m_aligned.tif`, both on an
identical 333×333 grid at 3 m. 100% of cells valid in both.

The tile is not homogeneous, and a pooled statistic blends three
populations that answer different questions. Regions are disjoint and
cover the tile; "water" is cells with **zero returns of any kind**
(binmode count, not a radius search).

| region | cells | share | mean | median | std | RMSE | \|d\|>0.15 m |
|---|---|---|---|---|---|---|---|
| pooled | 110,889 | 100% | +0.032 | +0.038 | 0.106 | 0.111 | 2.16% |
| **marsh** | 104,947 | 94.6% | **+0.038** | +0.039 | 0.072 | **0.081** | 1.79% |
| crest (levee top) | 706 | 0.6% | −0.710 | −0.911 | 0.651 | 0.963 | 59.9% |
| water | 5,236 | 4.7% | +0.027 | +0.028 | 0.063 | 0.069 | 1.74% |

**The marsh row is the meaningful one.** Across 94.6% of the tile the two
independent classifications agree to **0.081 m RMSE**, with a small
positive bias (+0.038 m) — this surface sits marginally above the
vendor's, consistent with a slightly more permissive ground call.

**The pooled row should not be quoted.** It averages real ground
agreement together with a known truncation and with two interpolations
across ground nobody measured.

**The water row measures nothing about terrain.** Neither surface
observed the canal bed; both interpolate across it. That the two
interpolations agree to 0.069 m says only that they were computed
similarly. The delivered surface must not be read as bathymetry, and the
canal surface is interpolated at a median **2.374 m** (cells with zero
returns at 3 m, sampled on the aligned vendor surface) where there is in
fact open water.

*Correction, 2026-08-11*: this figure previously read "roughly 2.28 m".
That value does not reproduce under any tested definition -- median
2.374, mean 2.365, largest-water-body 2.381, p25 2.344 --
and its method was never recorded, so it cannot be checked. It is
replaced by a value whose definition is stated. Same failure as the
predecessor project's CHM cluster count, which also had no recorded
search radius and also did not reproduce.

## 5. Limitations

### 5.1 The L-67A crown is truncated by ~0.76 m — accepted and documented

**The delivered surface truncates the L-67A embankment crown.** Crest
cells sit a median **−0.911 m** (mean −0.710 m) relative to the
vendor surface;
equivalently, median crest height above the marsh datum falls from
**2.369 m to 1.612 m, a 0.757 m reduction**. This affects 706 cells,
0.64% of the tile.

**The measured reason.** SMRF removes a raised feature by morphological
opening once its diamond structuring element no longer fits inside the
feature *at the height being cut*. A levee is a wedge, so the governing
width is the crown, not the base:

| height above marsh | width |
|---|---|
| 0.30 m | 45.7 m |
| 1.00 m | 32.3 m |
| 2.00 m | 18.0 m |
| **2.50 m** | **8.5 m** |
| **2.75 m** | **6.0 m** |

At `cell = 3.0 m` the smallest structuring element SMRF can form
(radius 1) already spans **9 m**, which exceeds the crown above roughly
2.4 m. `window` is therefore already at its floor — any value ≤ `cell`
yields radius 1 — and **no window setting at this cell size preserves the
crown**. This is a resolution floor, not a tuning failure.

**Both competing requirements, quantified.** They are irreconcilable
within one parameter set:

| requirement | needs | measured basis |
|---|---|---|
| ground coverage in marsh | `cell` **≥ 3 m** | at 1 m, **47.04%** of cells contain no ground return; at 3 m, 8.31% |
| resolving the 6–8 m crown | `cell` **≤ 1.5 m** | crown is 2–3 px at 3 m, narrower than the minimum structuring element |

**The finer cell is not a free improvement — this was tested.** Cell
1.5 m does preserve the crown (99.6% retained, crest 1.989 m above
marsh). But measured over marsh cells only, with the embankment and a
30 m buffer excluded so the feature under test cannot contaminate its own
control, it also under-filters vegetation:

| | marsh mean bias | marsh RMSE | marsh cells >0.15 m above vendor |
|---|---|---|---|
| `cell` 3.0 m (delivered) | +0.0416 m | 0.0497 m | **0.15%** |
| `cell` 1.5 m | +0.0637 m | 0.0760 m | **2.34%** |

A **15× increase** in marsh cells sitting above the vendor surface
(2.34% vs 0.15%), and a 53% higher marsh RMSE, across the 94.6% of the
tile that is the actual deliverable.

*Correction, 2026-08-11*: this read "23×" until the deliverable-number
audit flagged it. 23× is 2.34% ÷ 0.10%, but 0.10% is the tail for
`w6`–`w50`; the delivered configuration is `w3`, whose tail is 0.15%.
The comparison was against the wrong baseline — the same failure class
as the retracted embankment-width derivation in `parameter_derivation.md`.
The conclusion is unchanged; only its magnitude was overstated. The crown is bought by degrading everything else.

**Decision: accept the truncation.** The alternative — a dual-cell
composite, fine near the levee and coarse in the marsh — would trade a
measured, bounded, documented limitation for an undocumented seam along a
boundary that would itself need justifying. Tile-edge discontinuity of
exactly that kind was a real and quantified defect in the prior project.
A known 0.76 m truncation on 0.64% of the tile is the better outcome, and
it is stated here rather than discovered downstream.

### 5.7 Bank flanks are classified non-ground

Terrain slope on this tile is **bimodal**: median 0.489%, p90 2.334%, but
p99 **20.372%** and max 50.796% — a flat marsh plane plus engineered
banks. Measured by `gdaldem slope -p` on the vendor 3 m surface **as
originally gridded** (335x334, point-derived extent). On the aligned
333x333 grid the same measurement gives 0.490 / 2.318 / 20.442 / 51.088:
the difference is grid phase, not disagreement, and is the same effect
quantified in §5.5.
`slope = 0.05` is set from the marsh, because setting it from the banks
would put the radius-1 cutoff at 0.6 m, above the 90th percentile of
vegetation height, and almost nothing would be removed. The cost is that
steep bank flanks exceed the cutoff and are rejected. One parameter
cannot serve both populations.

### 5.8 Ground and vegetation overlap irreducibly

Class-2 ground residual about the 3 m surface has std **0.072 m**
(p5–p95 spread 0.133 m). Unclassified returns sit at p25 +0.050 m and
p50 +0.240 m — but **40.6% fall below 0.15 m** above ground, 56.1% below
0.30 m, 70.3% below 0.50 m. The two populations genuinely overlap and no
elevation threshold separates them cleanly. This is a property of
sawgrass in a metre-relief marsh, not a parameter left untuned.
`threshold = 0.15 m` is placed at roughly 2σ of genuine ground scatter,
deliberately trading one error against the other.

### 5.9 Open water is absence, not error

**6.07%** of the tile returns nothing at all; 95.7% of that area lies in
clusters larger than 100 m², i.e. the canals rather than scattered
dropout. This is water absorbing the 1064 nm pulse [cited: sensor class specification] — irreducible, not a
classification problem. See §4 on why the interpolated canal surface must
not be presented as measured terrain.

### 5.5 Acquisition: two flight lines, flown 19.8 hours apart

The tile is covered by **two** flight lines — `PointSourceId` 34012
(north) and 34101 (south) — with GPS times 71,229 s apart, so the passes
are on different days rather than one continuous lift. Coverage at 10 m
is **48.8% single-swath, 49.2% double, 2.0% uncovered**.

**Measured inter-swath offset: −0.0027 m** (marsh, 21,723 cells observed
by both), RMSE 0.0287 m. Method: vendor class-2 points split by
`PointSourceId`, each rasterized on the identical explicit grid with no
IDW fallback, compared only where both swaths actually observed ground.
SMRF was deliberately not re-run per swath — it anchors its internal grid
to the input extent, and two swaths have different extents (§5.6).

An overnight gap was expected to produce a *larger* offset than the
predecessor project's +0.124 ft (37.8 mm) single-day figure, since GNSS
conditions and wetland water level both change overnight. It did not:
2.7 mm, an order of magnitude smaller.

**This bears on §4.** The 0.0287 m inter-swath RMS is present in the
vendor surface and this one alike, since both are built from all returns
regardless of swath. It is therefore a component of the 0.081 m marsh
agreement figure that is **not** classification disagreement — roughly
13% of its variance. The remainder is genuinely classification.

**Coverage is not stratified by acquisition.** Single-swath cells are
44.24% no-ground and double-swath cells 47.69%, against the tile-wide
47.04% — a small spread running *opposite* to "degraded single
coverage". Dropout behaves as expected: 5.23% no-returns at one swath
versus 3.11% at two. So the cell-size sweep in §5.1 is not an average
across good and bad acquisition.

### 5.6 Single tile, no adjacent context

Classification near the tile edge lacks neighbourhood context from
outside the tile, and no buffering from adjacent tiles was implemented
here. The effect is bounded by SMRF's reach — at `window = 3 m`,
`ceil(window/cell) = 1` cell — so it is far smaller than in the prior
project, where a 122 ft reach [cited: lidar-portfolio CLAUDE.md]
produced measurable seam discontinuity.
Not measured on this tile; noted as unquantified.

## 6. Deliverables

| file | description |
|---|---|
| `output/dem/dem_w3_s0.05_t0.15.tif` | bare-earth DEM, 3 m, IDW (md5 `ab0bebaf…`) |
| `output/dem/dem_VENDOR_3m_aligned.tif` | vendor class-2 reference, identical grid |
| `output/dem/count_allret_3m_aligned.tif` | all-return count, binmode (water mask) |
| `output/reports/parameter_derivation.md` | full derivation incl. retracted attempt |
| `output/reports/vendor_baseline_characterization.md` | coverage / void analysis |
| `scripts/pipelines/*.json` | one pipeline per run, audit trail |

Reproduce with `scripts/run_smrf.py`; re-derive every table above with
`measure_window_sweep.py`, `measure_embankment_profile.py`,
`check_veg_cost.py` and `qc_vs_vendor.py`. Each states its measurement
parameters in its own docstring.
