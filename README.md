# Bare-Earth DEM — S-151, Miami Canal at L-67A, Everglades

A bare-earth digital elevation model produced from raw LiDAR returns for
the SFWMD **S-151** structure, where the Miami Canal crosses the L-67A
levee in Water Conservation Area 3, Florida. Deliverable, QC memo and
full parameter derivation included.

**[→ Read the report (PDF, 17 pp)](output/reports/qc_report.pdf)**

---

## The short version

| | |
|---|---|
| **Deliverable** | 3 m bare-earth DEM, EPSG:6350 (Conus Albers, **metres**), NAVD88 / Geoid12B |
| **Source** | USGS 3DEP `FL_Southeast_2018_D18_SUPPLEMENTAL`, tile `e1557n0456`, 16.9 M points |
| **Agreement with vendor ground** | **0.081 m RMSE** across the marsh (94.6% of tile) |
| **Known limitation** | levee crown truncated by a median 0.911 m — irreducible at this site, see below |

**This is agreement, not accuracy.** No external vertical control exists
on this tile and USGS published no accuracy report for the collection, so
an ASPRS Non-Vegetated Vertical Accuracy figure cannot be computed. Every
statistic here compares two independent classifications of the same point
cloud; both could carry the same bias.

## The finding this site turns on

**Point density is high and almost useless.** The tile carries
**16.89 pts/m²** — QL1 by the USGS LiDAR Base Specification — but only
**1.26 pts/m²** of *ground*. Classifying every 1 m cell by what it
actually received:

| | share of tile |
|---|---|
| ground present | 52.9% |
| returns present, none reaching ground (sawgrass) | **41.0%** |
| no returns at all (open water) | **6.1%** |

Those two failures are different in kind and must not be summed.
Vegetation blocking is a classification problem — the returns exist.
Open water is irreducible absence: the pulse is absorbed, and no
processing choice recovers it.

**Cell size follows from coverage, not from density.** A measured sweep
set it at 3.0 m: the vegetation gap closes as cells grow (76.79% → 8.29%
of cells with no ground return) while the water floor barely moves
(7.24% → 4.72%). A 1 m cell — the value a comparable desert project used
— would leave **47.04%** of cells with no ground observation at all.

## The limitation, stated rather than worked around

The L-67A levee **crown is 6.0–8.5 m wide**, narrower than the smallest
structuring element SMRF can form at a 3 m cell (9 m span). The delivered
surface therefore truncates the crown by a median 0.911 m.

Two requirements collide and cannot both be met by one parameter set:

| requirement | needs | why |
|---|---|---|
| ground coverage in the marsh | cell **≥ 3 m** | at 1 m, 47.04% of cells hold no ground return |
| resolving the 6–8 m crown | cell **≤ 1.5 m** | the crown is 2–3 px at 3 m |

A finer cell does recover the crown — and costs a **15× increase** in
marsh cells sitting above the vendor surface, measured rather than
assumed. That trade was declined, and a dual-resolution composite was
declined too: it would exchange a measured, bounded limitation for an
undocumented seam.

## Pipeline

```
readers.las
  → filters.assign     strip vendor classification (result is independent of it)
  → filters.elm        cell 10.0 m, threshold 1.0 m
  → filters.outlier    statistical, mean_k 8, multiplier 3.0
  → filters.smrf       cell 3.0 m, window 3.0 m, slope 0.05,
                       threshold 0.15 m, scalar 1.25
  → filters.range      Classification[2:2]
  → writers.gdal       IDW, 3 m, fixed grid 333×333 @ 1557000/456000
```

Five of the eight numeric parameters are measured from this tile, one is
inherited without independent validation and labelled as such, two are
reasoned defaults on a low-impact stage. PDAL 2.10.0 / GDAL 3.12.

## Reproducing it

```bash
conda activate lidar
python scripts/download_neighbours.py     # source tiles, URLs from the TNM query
python scripts/build_vendor_aligned.py    # vendor reference on the fixed grid
python scripts/run_smrf.py --tag w3_s0.05_t0.15 \
    --window 3 --slope 0.05 --threshold 0.15 \
    --cell 3.0 --res 3.0 --elm-cell 10.0 --elm-threshold 1.0
python scripts/characterize_vendor.py     # coverage sweep + checks vs published values
python scripts/qc_vs_vendor.py            # agreement by region
python scripts/render_figures.py          # all six figures
python scripts/build_report.py            # the PDF
```

Every run writes its PDAL pipeline to `scripts/pipelines/`. Every
measurement script writes a dump to `output/reports/*.txt` carrying a
**mandatory parameters header** — `scripts/dump.py` refuses to write a
file without one, because a number saved without the choices that
produced it is traceable but not verifiable.

Data source: located via the TNM API, tight-bbox query on the site
coordinate. `scripts/fetch_api.py` will not return a truncated page —
a wide-bbox query returning 300 of 694 items once reported "no coverage"
for the only project that covers this site.

## Method notes — the retractions are the point

Three findings in this project were **published internally, then measured
and withdrawn**. They are kept in the record rather than tidied away,
because the corrections are the part worth reading:

- **The `window` derivation.** Predicted from the embankment's 32–46 m
  width that the levee would survive below `window` = 12 m. The sweep
  refuted it. The mechanism was right — two settings came back
  byte-identical exactly where convergence was predicted — but it was
  applied to the levee's *base* width when opening cuts at the *crown*.
  Full account in Appendix A of the report.
- **A "23× increase"** that was really 15× [cited: superseded value,
  retained to show the error], from comparing against the wrong
  baseline run. Caught by an automated check, not by review.
- **A canal elevation of 2.28 m** that reproduces under no definition
  tried. Its method was never recorded, so it could only be discarded,
  not corrected — which is worse than a wrong number.

Each failed the same way: a correct measurement compared against the
wrong reference. That pattern, and the checks now in place for it, are
documented in `CLAUDE.md`.

### The automated number check was inert while this project was written

`.claude/hooks/check_deliverable_numbers.py` audits every number written
into `output/reports/` and traces it back to an artifact that derives it.
It is real, it found four defects in itself during development, and it
caught the `23×` → `15×` baseline error before I did.

**It never ran as a hook.** From configuration until 2026-08-12 it was
invoked via its `#!/usr/bin/env python3` shebang, which on this machine
resolves to the Windows Store stub — `"Python was not found"`, exit 49.
A `PreToolUse` hook exiting non-2 is a *non-blocking* error, so the
companion `guard_destructive.py` silently did not guard either.

**`.claude/hooks/last_number_audit.txt` exists in this repo and is not
evidence the hook ran.** The script writes that file, and the script can
be run by hand — which is what produced it. An artifact that implies
coverage it never provided is worse than no artifact, so: the audits this
project cites were **manual and deliberate, not automatic per-write**.
Their findings stand. The coverage does not.

Fixed by invoking an explicit interpreter path, and verified firing live
afterwards rather than merely configured.

## Limitations

1. **Crown truncation**, median 0.911 m — resolution floor, see above.
2. **Bank flanks classified non-ground.** Terrain slope is bimodal
   (median 0.489%, p99 20.4%); one `slope` value cannot serve a flat
   marsh and engineered banks together.
3. **Ground and vegetation overlap irreducibly.** 40.6% of unclassified
   returns sit within 0.15 m of ground — a property of sawgrass, not a
   threshold yet to be found.
4. **Open water is interpolated, not measured.** The canal surface reads
   ~2.374 m where there is water. Not bathymetry.
5. **Coverage is banded.** Two flight lines flown 19.8 hours apart leave
   the north and south edges single-swath (11–14 pts/m²) against 19.6 in
   the overlapping middle. Inter-swath vertical offset measured at
   −0.0027 m.
6. **Tile-edge effects are unquantified**, deliberately. SMRF anchors its
   internal grid to the input extent, so buffered and unbuffered runs
   are not comparable cell-by-cell; the mechanism is measured and
   documented instead of a number being asserted.

## Layout

```
data/raw/          source tiles (gitignored, re-downloadable)
scripts/           pipeline, measurement and figure scripts
scripts/pipelines/ generated PDAL JSON, one per run
output/dem/        DEMs and count rasters (gitignored)
output/figures/    figures (gitignored, regenerable)
output/reports/    memo, derivation, PDF, measurement dumps  ← tracked
docs/              session log
```
