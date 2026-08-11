#!/usr/bin/env python3
"""
Paginated-API fetch helpers that cannot silently return a truncated
result set.

WHY THIS EXISTS
---------------
While selecting this project's site, a wide-bbox query to the USGS TNM
products API returned 300 of 694 matching items. Nothing about the
response looked wrong: HTTP 200, valid JSON, a well-formed list. The
list was read as complete, and the conclusion drawn from it was that no
3DEP project covers SFWMD structure S-151 -- for the one project that
does. It was caught only because a tighter bbox was run later for an
unrelated reason.

The dangerous property is not the truncation itself, it is the SHAPE of
the resulting error. A capped query produces a NEGATIVE result -- "no
coverage," "no marks in bounds," "no match" -- and a negative is exactly
what nothing downstream will contradict. A wrong positive gets caught
when someone opens the file; a wrong negative just quietly closes off a
line of inquiry.

So the rule these helpers enforce is: a result set is not a result until
its count has been checked against an authoritative total. Either every
page is fetched, or the call raises with BOTH numbers in the message.
There is deliberately no partial-return mode and no "warn and continue"
flag, because the whole failure mode is that a partial list is
indistinguishable from a complete one at the call site.

DESIGN NOTES
------------
1. Every backend is reduced to the same completeness check
   (len(items) == total), even though they report totals differently:

     - TNM returns "total" in every response body.
     - ArcGIS FeatureServer does NOT return a total with the data. It
       sets "exceededTransferLimit" when there is more. We therefore
       issue a separate returnCountOnly=true query FIRST and treat that
       as authoritative, rather than trusting a flag to be present.

   Collapsing both to one rule matters: two different notions of "done"
   is how one of them ends up subtly wrong.

2. Pagination advances by the number of records ACTUALLY RETURNED, never
   by the page size requested. ArcGIS silently clamps resultRecordCount
   to the layer's own maxRecordCount, so a client that assumes it got
   what it asked for will skip records. That assumption is the same
   class of bug this module exists to prevent.

3. A page that yields zero new records while the total is unmet RAISES
   rather than breaking the loop. Treating no-progress as "finished" is
   how a transient server-side failure becomes a short result set.

4. SFWMD's endpoint returns HTTP 403 without a browser-like User-Agent,
   so one is always sent.

Standing project rule (global CLAUDE.md, "Data integrity"): a paginated
API response is not a result set until the counts are checked.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

# SFWMD's ArcGIS gateway 403s the default urllib agent. Not optional.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Guards against an infinite loop if a server reports a total it will
# never serve. Generous: 694 items at 100/page is 7 requests.
MAX_PAGES = 500

# TNM intermittently returns an empty "items" list with HTTP 200 and a
# correct "total" -- observed live at offset 1,000 of 35,144, and NOT
# reproducible on a repeat of the identical request. Retrying the same
# offset recovers it. This constant is why the paginator does not treat
# an empty page as the end of the data.
EMPTY_PAGE_RETRIES = 4

# Courtesy pause between pages. Not rate-limit avoidance (none observed
# in a 14-request burst) -- just not hammering a public agency's API.
PAGE_DELAY = 0.25

# A total above this raises rather than issuing hundreds of requests.
# It is a REFUSAL, never a silent cap: the caller is told to narrow the
# query or to raise the limit deliberately. Overridable per call.
DEFAULT_MAX_ITEMS = 10_000


class QueryTooBroadError(RuntimeError):
    """Raised when a query matches more items than the caller allowed.

    Distinct from TruncatedResultError: nothing has gone wrong with the
    server or the paging. The query is simply broader than the caller
    budgeted for, and the honest options are to narrow it (usually by
    subdividing the bbox) or to raise max_items on purpose. What must
    NOT happen is quietly returning the first N.
    """

    def __init__(self, total, limit, label=""):
        super().__init__(
            f"QUERY TOO BROAD: {total:,} items match, limit is {limit:,}"
            f"{' [' + label + ']' if label else ''}.\n"
            "  Nothing is wrong with the API -- this is a refusal to page\n"
            "  through an unbounded result set. Narrow the query (subdivide\n"
            "  the bbox), or pass max_items explicitly to accept the cost.\n"
            "  Returning the first page instead is exactly the bug this\n"
            "  module exists to prevent."
        )
        self.total = total
        self.limit = limit


class TruncatedResultError(RuntimeError):
    """Raised when a paginated fetch cannot prove it retrieved everything.

    Carries the actual numbers so the caller sees the size of the gap
    rather than a bare "something went wrong" -- the TNM near-miss was
    300 of 694, and that ratio is the whole story.
    """

    def __init__(self, returned, total, context=""):
        self.returned = returned
        self.total = total
        pct = (100.0 * returned / total) if total else 0.0
        msg = (
            f"TRUNCATED RESULT SET: got {returned:,} of {total:,} items "
            f"({pct:.1f}%). Refusing to return a partial list."
        )
        if context:
            msg += f" [{context}]"
        msg += (
            "\n  A short list here reads exactly like a complete one, and "
            "the resulting error is usually a false negative. Fix the "
            "query or the paging before using this result."
        )
        super().__init__(msg)


def _get_json(url, params=None, timeout=60, retries=3):
    """GET returning parsed JSON, with retries on transport errors only.

    Retries never mask a count mismatch -- they exist so a flaky
    connection doesn't get mistaken for "no more pages," which would
    silently truncate.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"request failed after {retries} attempts: {url}\n  {last}")


def _paginate(fetch_page, total, page_size, label, verbose=True,
               empty_retries=EMPTY_PAGE_RETRIES, delay=PAGE_DELAY):
    """Shared paging loop. fetch_page(offset) -> list of records.

    `total` must be authoritative and known BEFORE paging starts. That is
    the point of the module: completeness is checked against an
    independent number, not inferred from the data running out.

    An empty page mid-set is RETRIED, not accepted. Measured against the
    live TNM API, an empty "items" list arrives intermittently alongside
    HTTP 200 and a correct "total" -- a transient hiccup that recovers on
    a repeat request to the very same offset. It is therefore neither a
    reason to stop (that silently truncates) nor an immediate failure
    (that makes the helper flaky). Only a persistent empty raises.

    Short non-empty pages are accepted without complaint: progress is
    what matters, and the final count is checked against `total` anyway.
    Paging advances by records ACTUALLY RECEIVED, never by the requested
    page size, since servers clamp that silently.
    """
    items = []
    pages = 0
    while len(items) < total:
        if pages >= MAX_PAGES:
            raise TruncatedResultError(
                len(items), total, f"{label}: hit MAX_PAGES={MAX_PAGES}"
            )

        offset = len(items)
        batch = None
        for attempt in range(empty_retries):
            candidate = fetch_page(offset)
            if candidate:
                batch = candidate
                break
            if verbose:
                print(f"    empty page at offset {offset:,} "
                      f"(attempt {attempt + 1}/{empty_retries}) -- retrying")
            time.sleep(1.5 * (attempt + 1))

        # Persistent zero progress against an unmet total is a failure,
        # never an exit condition.
        if not batch:
            raise TruncatedResultError(
                len(items), total,
                f"{label}: offset {offset:,} returned 0 records on "
                f"{empty_retries} consecutive attempts while "
                f"{total - len(items):,} remain",
            )

        items.extend(batch)
        pages += 1
        if verbose and (pages <= 3 or pages % 25 == 0 or len(items) >= total):
            print(f"    page {pages}: +{len(batch)} -> {len(items):,}/{total:,}")
        if delay and len(items) < total:
            time.sleep(delay)

    if len(items) != total:
        raise TruncatedResultError(len(items), total, label)
    if verbose:
        print(f"    COMPLETE: {len(items):,}/{total:,} in {pages} pages")
    return items


# ----------------------------------------------------------------------
# USGS The National Map -- products API
# ----------------------------------------------------------------------
TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"


def tnm_products(bbox=None, datasets=None, polygon=None, page_size=100,
                  extra_params=None, verbose=True, max_items=DEFAULT_MAX_ITEMS):
    """Fetch ALL matching TNM products, or raise.

    bbox: (xmin, ymin, xmax, ymax) in WGS84 decimal degrees.
    datasets: e.g. "Lidar Point Cloud (LPC)".

    TNM reports "total" in every response, so the authoritative count
    comes from the first page and paging continues until it is met.
    """
    params = {"outputFormat": "JSON", "max": page_size, "offset": 0}
    if bbox:
        params["bbox"] = ",".join(str(v) for v in bbox)
    if datasets:
        params["datasets"] = datasets
    if polygon:
        params["polygon"] = polygon
    if extra_params:
        params.update(extra_params)

    if verbose:
        print(f"  TNM query: bbox={params.get('bbox')} datasets={datasets!r}")

    first = _get_json(TNM_URL, params)
    if first.get("errors"):
        raise RuntimeError(f"TNM API returned errors: {first['errors']}")

    total = int(first.get("total", 0))
    items = list(first.get("items", []))
    if verbose:
        print(f"    reported total: {total:,}; first page: {len(items):,}")

    if total == 0:
        return []
    if max_items is not None and total > max_items:
        raise QueryTooBroadError(total, max_items, "TNM")

    # Already complete on page one.
    if len(items) >= total:
        return items[:total]

    def fetch_page(offset):
        # Page 0 is already in hand; don't re-request it.
        if offset == 0:
            return items
        p = dict(params)
        p["offset"] = offset
        page = _get_json(TNM_URL, p)
        if page.get("errors"):
            raise RuntimeError(f"TNM API returned errors at offset {offset}: {page['errors']}")
        # Re-check the total on every page. If the server's own count
        # moves under us, the completeness proof is void -- raise rather
        # than quietly adopting whichever number is convenient.
        page_total = int(page.get("total", total))
        if page_total != total:
            raise TruncatedResultError(
                offset, total,
                f"TNM total changed mid-pagination ({total:,} -> {page_total:,})",
            )
        return page.get("items", [])

    return _paginate(
        fetch_page,
        total=total,
        page_size=page_size,
        label="TNM",
        verbose=verbose,
    )


# ----------------------------------------------------------------------
# ArcGIS FeatureServer / MapServer -- query endpoint
# ----------------------------------------------------------------------
def arcgis_query(layer_url, where="1=1", out_fields="*", return_geometry=True,
                  geometry=None, geometry_type="esriGeometryPoint",
                  in_sr=4326, page_size=1000, extra_params=None, verbose=True,
                  max_items=DEFAULT_MAX_ITEMS):
    """Fetch ALL matching ArcGIS features, or raise.

    layer_url: .../FeatureServer/<n> (no trailing /query)

    ArcGIS does not report a total alongside the data -- only an
    "exceededTransferLimit" flag. We therefore ask for the count FIRST
    with returnCountOnly=true and treat that as authoritative, so this
    backend obeys the same len(items)==total rule as TNM rather than
    trusting a flag to be present and correct.
    """
    query_url = layer_url.rstrip("/") + "/query"
    base = {"where": where, "f": "json"}
    if geometry is not None:
        base["geometry"] = geometry if isinstance(geometry, str) else json.dumps(geometry)
        base["geometryType"] = geometry_type
        base["inSR"] = in_sr
        base["spatialRel"] = "esriSpatialRelIntersects"
    if extra_params:
        base.update(extra_params)

    if verbose:
        print(f"  ArcGIS query: {layer_url}")
        print(f"    where: {where}")

    # 1. Authoritative count, independent of the data request.
    count_params = dict(base)
    count_params["returnCountOnly"] = "true"
    count_resp = _get_json(query_url, count_params)
    if "error" in count_resp:
        raise RuntimeError(f"ArcGIS count query failed: {count_resp['error']}")
    total = int(count_resp.get("count", 0))
    if verbose:
        print(f"    authoritative count: {total:,}")
    if total == 0:
        return []
    if max_items is not None and total > max_items:
        raise QueryTooBroadError(total, max_items, "ArcGIS")

    # 2. Page the data until that count is met.
    data_params = dict(base)
    data_params["outFields"] = out_fields
    data_params["returnGeometry"] = "true" if return_geometry else "false"
    data_params["resultRecordCount"] = page_size

    def fetch_page(offset):
        p = dict(data_params)
        p["resultOffset"] = offset
        resp = _get_json(query_url, p)
        if "error" in resp:
            raise RuntimeError(f"ArcGIS query failed at offset {offset}: {resp['error']}")
        return resp.get("features", [])

    # Determine the server's REAL page size from the first response: it
    # clamps resultRecordCount to the layer's maxRecordCount without
    # saying so, and paging by the requested size would skip records.
    first_batch = fetch_page(0)
    if len(first_batch) >= total:
        return first_batch[:total]

    effective_page = len(first_batch)
    if verbose and effective_page != page_size:
        print(f"    NOTE: server clamped page size {page_size} -> {effective_page}")

    def fetch_rest(offset):
        return first_batch if offset == 0 else fetch_page(offset)

    return _paginate(
        fetch_rest,
        total=total,
        page_size=effective_page,
        label="ArcGIS",
        verbose=verbose,
    )


if __name__ == "__main__":
    import sys
    print(__doc__)
    print("This module is a library. Import tnm_products / arcgis_query.")
    sys.exit(0)
