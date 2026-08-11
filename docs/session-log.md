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
parameter values are set.

**One addition at close**, and it displaces the parameter work as next
session's first task: write a paginated-API helper that cannot return a
truncated result set silently — page to completion or raise with the
returned and total counts. This comes directly from the TNM near-miss
above. The reason it earns priority over the DEM work is the shape of
the failure rather than its size: the query succeeded, the JSON parsed,
the list was well-formed, and the wrong answer arrived as a *negative* —
"this project does not cover S-151" — which nothing downstream would
ever contradict. Site selection was one tighter bbox away from being
founded on it, and that bbox was run for an unrelated reason. Every
remaining data source here is paginated too.

So: helper first, then derive window/slope/threshold from the
measurements above.

---

## 2026-08-11 — the helper, and what building it turned up

Wrote `scripts/fetch_api.py` and its live verification suite before any
other API call, as planned. Two things came out of it that were not the
plan.

**The empty-page discovery.** The first full-scale test raised
`TruncatedResultError` at 1,000 of 35,144 items — offset 1,000 returned
zero records with HTTP 200 and a correct `total`. The obvious reading
was a server-side offset cap, which would have meant "TNM cannot be
paged past 1,000, subdivide always." That reading was wrong, and
checking it rather than designing around it was the right call: probing
offsets individually returned 100 records every time, and a 14-request
burst across offsets 0–1,300 produced no empties at all. Two runs, no
delay and paced, both clean.

So the empty page was a transient hiccup, not a limit. That matters more
than it sounds. It means TNM will, occasionally and unreproducibly, hand
back a well-formed empty page mid-set — which is the silent-truncation
failure mode in its purest form. A paginator treating "empty page =
finished" would have returned 1,000 of 35,144 and reported success.
The loop now retries the same offset four times before raising, so it is
robust to the hiccup without ever treating it as completion.

Worth noting the sequence: the helper's *first real act* was to catch a
failure mode nobody had hypothesized, and the reason it caught it is
that it refuses to infer completeness from the data running out. Had it
been written the ordinary way it would have passed its own test.

**The provenance defect.** Test 5 exercises the SFWMD ArcGIS endpoint,
and returned count 0 for S-151. Last night's record says the structure
was found with `NAME LIKE 'S-151%'`. That query matches **zero rows**.
The layer names it `S151`, no hyphen — only two of 1,178 structures
match `%151%` at all, the other being `G151W` on canal L-2W near
Clewiston, 40 miles away.

Everything recorded *about* S-151 was correct — coordinates to eight
decimals, CULVERT, MIAMI CANAL, six components, Fort Lauderdale. Only
the query string written beside them was wrong, which means the
provenance did not actually re-derive. That is this project's own
re-derivability rule failing in miniature, and it failed in the
now-familiar direction: a wrong query string returns a *negative*, and a
negative is what nothing downstream contradicts. Same family as the
truncation bug, discovered by the tool built for the truncation bug.

Corrected in `CLAUDE.md`, and the working query is now executable in
test 5 rather than remembered — which is the stronger fix. A recorded
parameter that no one ever runs is a claim; one wired into a test is a
measurement.

**Also learned and recorded**: TNM clamps `max` to 1,000 (asking 2,000
yields 1,000), ArcGIS clamps `resultRecordCount` to `maxRecordCount`
(2,000 on this layer), and neither says so — hence paging by records
received rather than requested. An over-broad query now raises
`QueryTooBroadError` rather than grinding through 352 requests or, worse,
returning page one.

Next: derive window/slope/threshold from the feature scales already
measured.

---

## 2026-08-11 (later) — SMRF parameters, and a prediction that failed usefully

Derived the parameter set. Four of the eight values fell out of
measurements already in hand; the interesting half of the session was
`window`, which I got wrong in a way worth recording.

**The wrong derivation.** I read the mechanism from PDAL source rather
than the CLI help -- diamond structuring element, `max_radius =
ceil(window/cell)`, feature eroded once the SE no longer fits inside it
-- and combined it with the recorded embankment width of 32-46 m. That
gave a clean prediction: the levee survives below ~12 m and is destroyed
above ~25 m, with the two scales (vegetation ~6 m, embankment ~32-46 m)
separated by enough room for a window to sit between them. I wrote the
prediction down before running, which is the one thing that went right.

The sweep refuted it. The levee was already gone at the smallest window
tested, and an 8x window range moved the crest by 0.12 m against a
2.37 m feature.

**Why it was diagnosable.** Half the prediction held exactly: windows 25
and 50 m came back byte-identical, putting convergence between 12 and 25
where the arithmetic said. So the mechanism was right and the input was
wrong -- which is a much easier thing to chase than a wholesale failure.
The 32-46 m width had been measured by thresholding 0.3-1.5 m above
marsh. That is the levee's *base*. Opening acts on the width at the
height being cut, and a levee is a wedge. Measured as a ladder of
heights, the crown is 6.0-8.5 m -- two or three pixels at a 3 m cell,
narrower than the smallest structuring element SMRF can form. No window
was ever going to preserve it.

This is project one's retracted-seam error in a new costume: correct
mechanism, real measurement, wrong reference quantity. It was findable
only because whoever recorded "32-46 m" also recorded the threshold used
to get it. A bare number would have looked perfectly sound.

**The part I nearly got wrong twice.** Re-derived from the crown, I
predicted two more runs and both hit within their stated ranges. That is
exactly the moment this project's most expensive rule applies -- a
prediction coming true is not verification -- so instead of writing it
up I tested the obvious rival explanation: that a smaller structuring
element just filters less everywhere, and the crown survives as a side
effect of retaining vegetation.

The test split the two results cleanly. Across an 8x window range the
marsh statistics are identical to four decimal places, so `window` is
exonerated and its effect really is confined to SE scale. But the finer
1.5 m cell showed a 23x increase in marsh cells sitting more than 0.15 m
above the vendor surface. Its 99.6% crown preservation is substantially
bought by retaining non-ground returns.

Both runs "looked good" on the crest metric. One was a genuine win and
one was a trade, and the crest number could not tell them apart. Had I
stopped at "both predictions hit," I would have recommended the finer
cell on the strength of the better-looking number.

**Also fixed**: the vendor DEM was sized from its own point extent
(335x334) and is not cell-aligned to the SMRF runs (333x333 on an
explicit origin) -- project one's grid-alignment bug arriving here on
schedule. Rebuilt on the identical grid rather than warped, so the
surface the crest mask derives from is not resampled.

Four limitations are documented rather than tuned away, the first being
that the levee crown is truncated ~0.76 m by a resolution floor. That is
a real property of the site: the cell size needed for ground coverage in
the marsh (3-5 m) is too coarse to resolve a 6-8 m engineered crown, and
those two requirements point in opposite directions.
