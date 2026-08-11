# SMRF parameter derivation — Everglades / S-151

**Tile**: `USGS_LPC_FL_Southeast_2018_D18_SUPPLEMENTAL_e1557n0456.laz`
**CRS**: EPSG:6350, NAD83(2011) Conus Albers — **metres**
**Date**: 2026-08-11

Every parameter below is labelled **MEASURED** (derived from this tile's
own data, with the measurement stated) or **INHERITED** (carried from
project one without independent validation here). Nothing is scaled
proportionally from San Xavier's values; that shortcut is what produced
a retracted finding in project one.

---

## 1. The mechanism these parameters act through

Read from PDAL 2.10.0 source (`filters/SMRFilter.cpp`,
`progressiveFilter()` and `classifyGround()`), not from CLI help text:

```
max_radius = ceil(window / cell)                    # in PIXELS
for radius in 1 .. max_radius:
    erode by 1 (cumulative), then dilate by radius  # diamond SE
    threshold = slope * cell * radius               # progressive cutoff
...
thresh = threshold + scalar * surface_slope         # final classification
```

Two consequences drive everything below.

**Opening removes an elevated feature once the structuring element no
longer fits inside it.** A diamond SE of radius *r* pixels fits within a
feature of width *W* pixels while `W >= 2r + 1`; the feature is eroded
away once `2r + 1 > W`. So a feature of width *W* survives all windows
below roughly `W / 2` and is destroyed above it.

**`window` therefore converges.** Once `max_radius` exceeds the largest
real non-ground feature present, further increases change nothing and
produce byte-identical output. A sweep that does not straddle a real
feature scale tests nothing — project one recorded a `window` finding
twice on this exact mistake, and both were retracted.

---

## 2. `cell` = 3.0 m — **MEASURED**

From the vendor-baseline coverage sweep (see
`vendor_baseline_characterization.md`): share of cells containing no
ground return, by cell size.

| cell | no ground point | no returns at all |
|---|---|---|
| 0.5 m | 76.79% | 7.24% |
| 1.0 m | 47.04% | 6.06% |
| 2.0 m | 18.11% | 5.29% |
| **3.0 m** | **8.31%** | 4.72% |
| 5.0 m | 4.63% | 3.79% |
| 10.0 m | 2.21% | 1.98% |

The vegetation-driven gap closes by 3–5 m while the water floor does
not; by 5 m the two curves nearly converge, meaning almost every
remaining empty cell is genuine open water. 3.0 m is taken as the
working value — the low end of the measured range, preserving the most
detail while keeping ground-empty cells under 10%.

San Xavier's 3.3 ft (≈1.0 m) would leave **47%** of cells with no ground
point here. This is the clearest single case for deriving rather than
carrying over.

## 3. `window` = the question the sweep answers — **MEASURED**

Two feature scales matter, and they are measured, not assumed:

| feature | measured width | eroded once window exceeds |
|---|---|---|
| vegetation clumps | ~6.3 m (2 × 3.16 m p99 distance-to-ground) | ~3 m |
| **L-67A embankment** | **32–46 m** (crest 2.91 m above marsh) | **~16–23 m** |

The scales are separated by roughly 5×, so a window exists that erodes
vegetation while never reaching embankment scale.

**The embankment must be KEPT.** It is a constructed levee — earth, not
vegetation or structure — and a bare-earth DEM of this site that omits
it is wrong. This is a design decision, stated rather than buried: it is
the reason window is bounded above at all.

At `cell = 3.0 m`, `max_radius = ceil(window / 3)` pixels and the SE
spans `2r + 1` pixels:

| window | max_radius | SE span | vs. 32–46 m embankment |
|---|---|---|---|
| 6 m | 2 px | 15 m | well inside — crest survives |
| 12 m | 4 px | 27 m | inside — crest survives |
| 25 m | 9 px | 57 m | exceeds — crest destroyed |
| 50 m | 17 px | 105 m | far exceeds — crest destroyed |

**Prediction, recorded before the runs**: 6 m and 12 m preserve the
embankment; 25 m and 50 m destroy it; 25 m and 50 m may be
byte-identical to each other if both sit past convergence.

### RESULT: the prediction was WRONG, and the error was the input, not the arithmetic

Measured with `scripts/measure_window_sweep.py` (crest mask fixed from
the aligned vendor raster; parameters in that script's docstring):

| window | crest above marsh | crest kept | marsh drift | md5 |
|---|---|---|---|---|
| *vendor* | *2.369 m* | — | — | — |
| 6 m | 0.797 m | 41.1% | +0.034 m | `70b1f8b4…` |
| 12 m | 0.679 m | 30.3% | +0.034 m | `4a3f0eb0…` |
| 25 m | 0.688 m | 29.6% | +0.034 m | `576d7559…` |
| 50 m | 0.688 m | 29.6% | +0.034 m | `576d7559…` |

The embankment is **already destroyed at the smallest window tested**.
Window moves the crest by 0.12 m across an 8× range while the vendor
surface sits 2.37 m above marsh. The marsh control is flat at +0.034 m
throughout, so this is the crest specifically and not a global shift.

Two parts of the prediction *did* hold, which is precisely why the
headline being wrong matters: 25 m and 50 m are **byte-identical**, so
convergence sits between 12 and 25 m exactly where
`max_radius = ceil(window/cell)` says it should. The mechanism was read
correctly. It was applied to the wrong number.

**The error**: the recorded 32–46 m width was measured by thresholding
0.3–1.5 m above marsh — that is the embankment's **base**. Morphological
opening acts on whatever width exists *at the height being cut*, and a
levee is a wedge. Measured properly
(`scripts/measure_embankment_profile.py`, inscribed-disk diameter so the
diagonal orientation doesn't inflate it):

| height above marsh | width | largest SE that fits |
|---|---|---|
| 0.30 m | 45.7 m | window ≤ 21 m |
| 1.00 m | 32.3 m | window ≤ 12 m |
| 1.50 m | 25.5 m | window ≤ 9 m |
| 2.00 m | 18.0 m | window ≤ 6 m |
| 2.25 m | 13.4 m | window ≤ 3 m |
| 2.50 m | **8.5 m** | none at cell 3 m |
| 2.75 m | **6.0 m** | none at cell 3 m |

The crown is **6–13 m wide** — 2–4 px at `cell = 3 m`. SMRF's smallest
structuring element (radius 1) already spans 3 px = 9 m, which exceeds
the crown above ~2.4 m. **No window at cell = 3 m can preserve the top
of this levee**, because the constraint binds at the resolution floor,
not at the window.

This is the same class of error as project one's retracted seam finding:
a correct mechanism, a real measurement, and a comparison against the
wrong reference quantity. Recording the *parameters* of the original
width measurement — "thresholded at 0.3–1.5 m" — is what made the error
findable at all.

### Re-derived from the crown, then tested

With the crown width in hand, two further runs were predicted **before**
being run: `window = 3 m` at cell 3 m (max_radius 1 px, SE spans 9 m —
holds while width ≥ 9 m, i.e. to ~2.45 m) and the same at cell 1.5 m
(max_radius 2 px, SE spans 7.5 m — holds to ~2.55 m).

| run | crest above marsh | crest kept | predicted | md5 |
|---|---|---|---|---|
| **w3, cell 3.0** | **1.612 m** | 72.4% | 1.5–2.0 m ✓ | `ab0bebaf…` |
| w6, cell 3.0 | 0.797 m | 41.1% | — | `70b1f8b4…` |
| c1.5, w3 | 1.989 m | 99.6% | 1.8–2.2 m ✓ | `45d2c79a…` |

Both hit. **Which is exactly when this project's rule says to stop and
check the mechanism instead of writing it up.**

### The competing explanation, tested and half-confirmed

A smaller structuring element filters less *everywhere*. If that were the
cause, the crown would survive not because the SE fits inside it but
because the run retains more non-ground points tile-wide — vegetation
included. The two explanations differ measurably: opening-scale effects
are confined to features near SE scale, under-filtering is tile-wide.

Measured with `scripts/check_veg_cost.py` over marsh cells only, with
the embankment plus a 30 m buffer excluded so the feature under test
cannot contaminate its own control (77,987 cells, 70.3% of tile):

| run | marsh mean bias | marsh RMSE | marsh >0.15 m high |
|---|---|---|---|
| w3 | +0.0416 m | 0.0497 m | 0.15% |
| w6 / w12 / w25 / w50 | +0.0414 m | 0.0481 m | 0.10% |
| **c1.5, w3** | **+0.0637 m** | **0.0760 m** | **2.34%** |

**For `window`: rejected.** Across an 8× range the marsh statistics are
identical to four decimals. The window effect is genuinely confined to
structuring-element scale, so `w3`'s better crest is not bought by
retaining vegetation. The mechanism is verified independently of the
prediction that proposed it.

**For `cell`: confirmed.** Cell 1.5 m shows a 23× increase in marsh cells
more than 0.15 m above the vendor surface and a 58% higher RMSE. Its
99.6% crown preservation is substantially bought by retaining non-ground
returns. Its crest number alone would have recommended it.

## 3b. `window` = 3.0 m — **MEASURED**, with a stated residual limitation

At `cell = 3.0 m`, `max_radius = ceil(window / cell)`, so **any window
≤ 3 m yields radius 1** — the minimum SMRF can use. The site's feature
scales drive this parameter to its floor.

**Residual limitation, stated rather than buried**: even at the minimum,
the recovered crest is 1.612 m above marsh against the vendor's 2.369 m.
**The top ~0.76 m of the levee is not recoverable at this cell size**,
because the crown above ~2.4 m is narrower (6.0–8.5 m) than the smallest
structuring element SMRF can form (9 m). This is a resolution floor, not
a tuning failure, and no window value addresses it.

The available remedies both cost more than they return here: a finer cell
resolves the crown but retains marsh vegetation (measured above), and a
region-specific parameter set would mean two surfaces mosaicked along a
boundary that itself has to be justified. Neither is taken; the
truncation is documented instead.

## 4. `slope` = 0.05 — **MEASURED**

Terrain slope from the vendor ground surface at 3 m (`gdaldem slope -p`):

| percentile | slope |
|---|---|
| median | 0.489% |
| p75 | 1.10% |
| p90 | 2.33% |
| p95 | 4.96% |
| p99 | **20.4%** |
| max | 50.8% |

The distribution is **bimodal**: a nearly flat marsh plane plus
engineered banks. One value must serve both, and that tension is real
rather than a tuning nuisance.

`slope = 0.05` is set from the marsh, not the banks. At radius 1 the
progressive cutoff is `0.05 × 3 × 1 = 0.15 m`, which sits just above
the measured class-2 residual scatter (std 0.072 m, p5–p95 spread
0.133 m) and just below the median vegetation height above ground
(+0.240 m) — so it rejects typical vegetation without flagging real
ground noise. Setting it from the p99 bank slope instead (0.2) would put
the radius-1 cutoff at 0.6 m, above the *90th percentile* of vegetation
height, and almost nothing would be removed.

**Known cost, not hidden**: at this value the steep bank flanks exceed
the cutoff and will be flagged non-ground. The crest is protected by
`window`, not by `slope`. Flank treatment is a genuine limitation of a
single-parameter fit to a bimodal surface.

## 5. `threshold` = 0.15 m — **MEASURED**

The final classification base threshold, from the measured overlap
between the two populations:

- class-2 ground residual about the 3 m surface: **std 0.072 m**,
  p5–p95 spread 0.133 m
- unclassified returns above ground: p25 **+0.050 m**, p50 **+0.240 m**,
  with **40.6% below 0.15 m**, 56.1% below 0.30 m, 70.3% below 0.50 m

0.15 m ≈ 2σ of genuine ground scatter, so it accepts real ground while
sitting below the median vegetation return.

**The populations genuinely overlap and no threshold separates them.**
40.6% of unclassified returns sit within 0.15 m of ground — that is a
property of sawgrass in a metre-scale-relief marsh, not a parameter yet
to be tuned. Any value here trades one error against the other; this one
is placed at the measured ground-noise ceiling deliberately.

## 6. `scalar` = 1.25 — **INHERITED, NOT VALIDATED**

Carried from project one, where it was itself never independently
validated. It scales the final threshold by local surface slope
(`thresh = threshold + scalar × surface_slope`), so on this tile it
mostly matters on the bank flanks — the one place the parameter set is
already known to be weakest.

Stated as inherited rather than presented as derived. Testing it is a
reasonable follow-on and has not been done.

## 7. ELM `cell` = 10.0 m, `threshold` = 1.0 m — **REASONED, low stakes**

ELM removes low outliers before classification. This tile carries 468
class-7 low-noise points (0.003%), so the stage is low-impact by
construction.

10 m / 1.0 m are the metric equivalents of PDAL's own defaults, used
deliberately here rather than converted from project one's feet values —
those were the literals that turned out to be hardcoded (`33.0` /
`3.3` ft) inside a function labelled generic, which would have become a
33 m cell and 3.3 m threshold against this CRS.

1.0 m is kept conservative against 2.81 m of total relief: the canal
banks drop 2+ m over short distances and a tighter threshold risks
eating real bank returns.

---

## 8. Summary

**Working parameter set** — `dem_w3_s0.05_t0.15.tif`, md5 `ab0bebaf…`:

| parameter | value | basis |
|---|---|---|
| `cell` | 3.0 m | **MEASURED** — coverage sweep (§2) |
| `window` | 3.0 m | **MEASURED** — crown width vs. SE span (§3, §3b) |
| `slope` | 0.05 | **MEASURED** — marsh slope vs. vegetation height (§4) |
| `threshold` | 0.15 m | **MEASURED** — ground residual σ vs. vegetation height (§5) |
| `scalar` | 1.25 | **INHERITED — not validated** (§6) |
| ELM `cell` | 10.0 m | reasoned (PDAL metric default) |
| ELM `threshold` | 1.0 m | reasoned, conservative vs. bank relief |
| output `res` | 3.0 m | matches `cell` |

Five of eight are measured from this tile. One is explicitly inherited
without validation. Two are reasoned defaults on a low-impact stage.

**Known limitations of this set**, none of them tunable away:

1. **The levee crown is truncated ~0.76 m** (§3b). The crown is narrower
   than SMRF's smallest structuring element at this cell size.
2. **Bank flanks are classified non-ground** (§4). `slope = 0.05` is set
   from the marsh; the surface is bimodal and one value cannot serve
   both populations.
3. **Ground and vegetation overlap irreducibly** (§5). 40.6% of
   unclassified returns sit within 0.15 m of ground — sawgrass, not a
   threshold yet to be found.
4. **Open water is absence, not error** (§2). 6.07% of the tile returns
   nothing; the surface interpolates across the canal and must not be
   presented as measured terrain there.

Reproduce any run with `scripts/run_smrf.py`; every run writes its
pipeline JSON to `scripts/pipelines/`. Re-derive the tables above with
`measure_window_sweep.py`, `measure_embankment_profile.py` and
`check_veg_cost.py` — each states its own parameters in its docstring.
