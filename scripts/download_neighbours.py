#!/usr/bin/env python3
"""
Download the four edge-sharing neighbours of e1557n0456.

URLs are not hardcoded: they come from the TNM query in
check_neighbours.py, so the download provenance and the existence
evidence are the same query. Sizes are printed before anything is
fetched.

Corners are deliberately skipped. They share a single point with the
centre tile and contribute essentially nothing to an edge-effect
measurement, at full download and processing cost -- the same call the
prior project made for the same reason.
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_neighbours import main as find_neighbours  # noqa: E402
from fetch_api import USER_AGENT  # noqa: E402

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main():
    edge = find_neighbours()
    if not edge:
        raise SystemExit("no edge-sharing neighbours to download")

    RAW.mkdir(parents=True, exist_ok=True)
    total = sum((it.get("sizeInBytes") or 0) for _, _, it in edge)
    print(f"\nDownloading {len(edge)} tiles, {total/1e6:.1f} MB total, to {RAW}\n")

    for pos, key, it in edge:
        url = it.get("downloadURL") or it.get("urls", {}).get("LAZ", "")
        dest = RAW / url.rsplit("/", 1)[-1]
        if dest.exists():
            print(f"  {pos:<3} {key}  already present ({dest.stat().st_size/1e6:.1f} MB)")
            continue
        print(f"  {pos:<3} {key}  fetching {(it.get('sizeInBytes') or 0)/1e6:.1f} MB ...",
              end="", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        tmp = dest.with_suffix(".partial")
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as fh:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
        tmp.rename(dest)
        print(f" done ({dest.stat().st_size/1e6:.1f} MB)")

    print("\nAll neighbours present.")


if __name__ == "__main__":
    main()
