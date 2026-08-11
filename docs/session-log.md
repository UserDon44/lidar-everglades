# Session Log — Everglades / S-151

Chronological, newest last. `CLAUDE.md` holds current technical state and
exact numbers; this is a diary of what happened and why.

---

## 2026-08-10 — project 2 opened

**Locating the site.** Started from a description rather than a
coordinate: SFWMD structure S-151 at the L-67A / Miami Canal
intersection. Found SFWMD's AHED Structures feature service via an ArcGIS
Online search (their own REST root and open-data portal both returned
nothing useful; the working endpoint also 403s without a browser
User-Agent). Queried it directly rather than triangulating the canal
crossing off a basemap.

The returned record corroborates the site description independently
instead of merely matching a name — `STRUCTURETYPE=CULVERT`, `CANAL=MIAMI
CANAL`, and `NUMBER_COMPONENTS=6`, matching the six 84-inch culverts.
That was the check worth having: a name match alone would not have
distinguished the right structure from a similarly-numbered one.

**Coverage: no vintage choice exists.** Only one 3DEP LPC tile in
existence contains S-151, from the 2018 Southeast collection. The 2024
Miami-Dade collection comes within about half a mile, but its footprints
step eastward going north and the point lands in the gap — almost
certainly the acquisition stopping at the county line and the WCA-3
boundary. Established by testing each tile footprint against the point
rather than assuming tiles tile contiguously.

One methodological trap caught here: a wide-bbox TNM query returned 300
of 694 items and consequently reported "no coverage" for the very project
that does cover the site. A truncated page is not an absence. The tight
bbox is authoritative.

**Three inherited assumptions, all wrong.** Checked CRS, units and datum
before touching the data, per the standing rule. All three differ from
project 1:

- EPSG:6350 Conus Albers, in **metres** — not a state plane zone at all.
  Florida East (ftUS) was the natural guess and would have been wrong.
  Project 1's rule was "never assume metres"; here the trap is exactly
  inverted, which argues the rule is really *check*, not "assume feet."
- NAVD88 via **Geoid12B**, not Arizona's 12A — and declared in the
  header, unlike San Xavier where it took a sealed survey report to
  establish.
- Ground is **7.4%** of points against San Xavier's 70.9%, while
  all-return density is 4.5× higher. Denser data, far less usable ground.
  Density alone would have been actively misleading.

Also found that excluding noise classes 7/18 does **not** recover a sane
Z range here — it still leaves 1,270 m of apparent relief; only filtering
to ground does. That is a direct contrast with the Tucson tile, where
dropping 7/18 was exactly the fix. The technique does not transfer, which
is worth recording so it isn't re-attempted from memory.

**A portability defect the inventory missed.** Before any SMRF run,
`run_dem.py`'s `build_pipeline()` turned out to hardcode ELM as
`cell=33.0, threshold=3.3` — feet values, inside a function project 1's
portability inventory had classified as "generic." Against a metre CRS
those silently request a 33 m cell and a 3.3 m threshold: no error, just
a wrong surface discovered much later, if ever. Fixed in project 1 as
parameters rather than a per-project override, so project three inherits
the fix, and the rest of `build_pipeline()` was audited for the same
class of defect at the same time (`mean_k`/`multiplier` are a count and a
sigma multiple, `window_size` is in cells — all unit-free, so ELM was the
only unit-bearing literal). Verified the defaults still reproduce San
Xavier's DEM byte-for-byte.

The general lesson: "generic" needs testing against a genuinely different
CRS, not inferring from a script's structure. Reading the code said
generic; metric data said otherwise.

**Vendor baseline and what it showed.** Built the vendor class-2 DEM at
1 m and 3 m, then characterized coverage per cell with `binmode: true`
from the outset — project 1's radius-counting bug inflated density ~6×,
which at 1.26 pts/m² would have been badly misleading. Raster total
matched the header class-2 count exactly, confirming true binning rather
than assuming it.

47.11% of 1 m cells hold zero ground points. The cell-size sweep gives
the actual answer — **3–5 m** — and shows why: the vegetation-driven gap
closes by then while the water floor does not, the two curves nearly
converging at 5 m. San Xavier's 3.3 ft cell would have produced a
47%-empty surface.

The more useful finding was that "void" is two different failures. 6.07%
of the tile receives no returns at all (water — 95.7% of that area in
clusters over 100 m², i.e. the canals) while 41.10% receives returns but
has none classified ground (vegetation at ground level). They need
different handling and should never be reported as one number: one is a
classification problem SMRF can attack, the other is irreducible absence.
Also noted that the vendor DEM at 3 m interpolates straight across the
canal, presenting open water as terrain at 2.28 m — a caveat any
deliverable has to state rather than quietly ship.

**Parameter derivation started, deliberately not finished.** Measured
what should drive window/slope/threshold rather than scaling San Xavier's
values down: bimodal slope (median 0.489%, p99 20.4% — flat marsh plus
engineered banks), vegetation obstruction reach (p99 3.16 m), embankment
cross-section (32–46 m wide, 2.91 m above marsh), and the
ground/vegetation vertical overlap (ground residual std 0.072 m against
40.6% of unclassified returns sitting below 0.15 m — the populations
genuinely overlap, which is a property of sawgrass, not of the
parameter).

Connected-component sizing of vegetation clumps failed the same way San
Xavier's pad-footprint measurement did: everything merges into a single
493 m network, making "largest object" meaningless. Switched to
distance-to-nearest-ground, which is well posed regardless of
connectivity. Worth noting the failure recurred in a completely different
environment — it is a property of the method, not of that terrain.

Stopped before setting the parameters. `window` in particular cannot be
settled by measurement alone: vegetation needs ~3 m of reach while the
embankment is 32–46 m wide, and whether that embankment is a feature to
erode or terrain to keep decides which side of the transition `window`
belongs on. Per project 1's SMRF mechanism finding, a sweep is only
informative if the tested values straddle that transition, and the
outputs must be checksummed rather than eyeballed.

**Session ended here by request.** No SMRF run has been made and no
parameter values are set. Next session's first task is deriving
window/slope/threshold from the measurements above.
