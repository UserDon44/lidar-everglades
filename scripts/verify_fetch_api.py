#!/usr/bin/env python3
"""
Verification for fetch_api.py, run against the live APIs.

The central test REPRODUCES this project's actual near-miss: a wide-bbox
TNM query whose first page is a fraction of the true match count, from
which "no 3DEP coverage for S-151" was wrongly concluded.

Tests, in order:

  1. The naive single-page read is still incomplete on a realistic
     query (so the hazard is live, not a fixed upstream bug), and we
     report whether it would have missed the covering project.
  2. fetch_api returns the complete set from that same query and finds
     the covering project.
  3. A pager whose pages go permanently empty RAISES rather than
     returning short. This matters as much as test 2: the guarantee is
     not "we page correctly," it is "we cannot silently fail to."
  4. A query broader than the caller's budget RAISES QueryTooBroadError
     instead of quietly returning the first page.
  5. The ArcGIS backend still resolves S-151, exercising the separate
     returnCountOnly=true completeness path.

Run:  python scripts/verify_fetch_api.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_api  # noqa: E402
from fetch_api import (  # noqa: E402
    TruncatedResultError, QueryTooBroadError, tnm_products, arcgis_query,
)

# S-151, from SFWMD's AHED Structures layer (see CLAUDE.md).
S151_LON, S151_LAT = -80.509853, 26.011511

# Realistic search bbox: ~0.1 deg around the site, 509 LPC products at
# time of writing -- the same order as the 694 that produced the false
# negative, so the test reproduces the real bug rather than a toy.
PAD = 0.10
SEARCH_BBOX = (S151_LON - PAD, S151_LAT - PAD, S151_LON + PAD, S151_LAT + PAD)

# Deliberately huge: ~35,000 products. Used only to prove the too-broad
# refusal fires instead of a silent first-page return.
HUGE_BBOX = (-81.6, 25.2, -80.0, 26.9)

# Tight bbox containing only S-151: the independent ground truth for
# what actually covers the point.
TPAD = 0.004
TIGHT_BBOX = (S151_LON - TPAD, S151_LAT - TPAD, S151_LON + TPAD, S151_LAT + TPAD)

LPC = "Lidar Point Cloud (LPC)"
PAGE = 100


def titles(items):
    return {it.get("title") or it.get("projectName") or "" for it in items}


def rule(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    failures = []

    # ------------------------------------------------------------------
    rule("GROUND TRUTH: tight bbox on S-151")
    truth_items = tnm_products(bbox=TIGHT_BBOX, datasets=LPC)
    truth = titles(truth_items)
    print(f"\n  {len(truth_items)} products covering the structure:")
    for t in sorted(truth):
        print(f"    - {t}")
    assert truth_items, "tight bbox returned nothing -- no ground truth"

    # ------------------------------------------------------------------
    rule("TEST 1: naive single-page read (the original bug)")
    params = {
        "outputFormat": "JSON", "datasets": LPC,
        "bbox": ",".join(str(v) for v in SEARCH_BBOX),
        "max": PAGE, "offset": 0,
    }
    raw = fetch_api._get_json(fetch_api.TNM_URL, params)
    total = int(raw.get("total", 0))
    page1 = titles(raw.get("items", []))
    print(f"\n  reported total : {total:,}")
    print(f"  first page     : {len(page1):,}  <-- what a naive read uses")
    print(f"  sees {100.0*len(page1)/total:.1f}% of the result set")

    missed = sorted(t for t in truth if t not in page1)
    if missed:
        print(f"\n  covering products ABSENT from page 1:")
        for t in missed:
            print(f"    MISSING: {t}")
        print("\n  => a page-1 read concludes these do not cover S-151.")
    else:
        print("\n  (page 1 happened to include the covering products this time --")
        print("   the truncation is still real; which records land on page 1")
        print("   is just server-side ordering, and is not a guarantee.)")

    if len(page1) >= total:
        failures.append("TEST 1: query no longer truncates; pick a wider bbox")

    # ------------------------------------------------------------------
    rule("TEST 2: fetch_api pages the same query to completion")
    full = tnm_products(bbox=SEARCH_BBOX, datasets=LPC)
    full_titles = titles(full)
    print(f"\n  returned {len(full):,} items (reported total {total:,})")
    if len(full) != total:
        failures.append(f"TEST 2: got {len(full)} of {total}")
    if not truth <= full_titles:
        failures.append("TEST 2: complete set missing a known-covering product")
    else:
        print(f"\n  all {len(truth)} covering products present in the complete set:")
        for t in sorted(truth):
            mark = "   (missed by page 1)" if t in missed else ""
            print(f"    FOUND: {t}{mark}")

    # ------------------------------------------------------------------
    rule("TEST 3: a permanently-empty pager must RAISE, not return short")
    real_get = fetch_api._get_json
    state = {"n": 0}

    def crippled(url, params=None, **kw):
        """First request real; every later one returns an empty page --
        simulating a server that stops delivering mid-set."""
        state["n"] += 1
        resp = real_get(url, params, **kw)
        if state["n"] > 1 and "items" in resp:
            resp["items"] = []
        return resp

    fetch_api._get_json = crippled
    try:
        tnm_products(bbox=SEARCH_BBOX, datasets=LPC, verbose=False)
    except TruncatedResultError as exc:
        print("\n  RAISED as required:\n")
        for line in str(exc).splitlines():
            print(f"    {line}")
        print(f"\n  returned={exc.returned:,}  total={exc.total:,}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"TEST 3: wrong exception type {type(exc).__name__}: {exc}")
    else:
        failures.append("TEST 3: crippled pager did NOT raise -- guarantee broken")
    finally:
        fetch_api._get_json = real_get

    # ------------------------------------------------------------------
    rule("TEST 4: an over-broad query must REFUSE, not return page 1")
    try:
        tnm_products(bbox=HUGE_BBOX, datasets=LPC, max_items=1000, verbose=False)
    except QueryTooBroadError as exc:
        print("\n  RAISED as required:\n")
        for line in str(exc).splitlines():
            print(f"    {line}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"TEST 4: wrong exception type {type(exc).__name__}: {exc}")
    else:
        failures.append("TEST 4: over-broad query did NOT raise")

    # ------------------------------------------------------------------
    rule("TEST 5: ArcGIS backend (SFWMD AHED) -- S-151 resolves")
    layer = ("https://geoweb.sfwmd.gov/agsext1/rest/services/WaterManagementSystem/"
             "All_Structures/FeatureServer/4")
    # NOTE: the structure is named "S151" in this layer, with NO hyphen.
    # The originally-recorded query used 'S-151%' and matches zero rows --
    # see CLAUDE.md. Kept explicit here so the working query is executable
    # rather than remembered.
    try:
        feats = arcgis_query(layer, where="NAME='S151'", out_fields="*",
                              extra_params={"outSR": 4326})
        print(f"\n  {len(feats)} feature(s)")
        for f in feats:
            a = f.get("attributes", {})
            g = f.get("geometry", {})
            print(f"    NAME={a.get('NAME')}  TYPE={a.get('STRUCTURETYPE')}")
            print(f"    CANAL={a.get('CANAL')}  COMPONENTS={a.get('NUMBER_COMPONENTS')}")
            print(f"    geometry: x={g.get('x')}  y={g.get('y')}")
        if not feats:
            failures.append("TEST 5: S-151 not found")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"TEST 5: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    rule("RESULT")
    if failures:
        print("\n  FAILURES:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print(f"""
  All tests passed.

  The hazard is live: a page-1 read of a realistic {total:,}-item search
  sees {len(page1)} items ({100.0*len(page1)/total:.1f}%). fetch_api returns all
  {len(full):,}, and cannot fail silently -- a stalled pager raises with
  both counts, and an over-broad query is refused outright.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
