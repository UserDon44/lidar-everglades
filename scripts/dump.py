#!/usr/bin/env python3
"""
Write a measurement to output/reports/ as a durable, self-describing dump.

WHY PARAMETERS ARE MANDATORY HERE
---------------------------------
Saving the numbers is not enough. This project has now been taught the
same lesson from both directions:

  The embankment width was recorded as "32-46 m" WITH its threshold
  ("measured 0.3-1.5 m above marsh"). That parameter is the only reason
  a wrong derivation built on it could be diagnosed rather than merely
  disbelieved -- it revealed the figure described the levee's base, not
  its crown.

  The S-151 coordinates were recorded WITHOUT a working query. The
  numbers were correct to eight decimals and completely unverifiable;
  re-running the documented query returned zero rows.

So a number saved without the choices that produced it is traceable but
not verifiable, which is a weaker guarantee than it looks. `Dump`
refuses to write a file with no parameters -- the check is mechanical
because remembering has already failed.

USAGE
-----
    with Dump("qc_vs_vendor",
               "Agreement between the SMRF surface and vendor ground",
               {"reference": "dem_VENDOR_3m_aligned.tif",
                "crest mask": "vendor > marsh + 2.0 m",
                "why 2.0 m": "above marsh roughness, selects crown not flanks"}):
        print(...)          # goes to the terminal AND the dump

Every `print` inside the block is teed to output/reports/<name>.txt.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "output" / "reports"


def _git_commit():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "unknown"


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            s.flush()


class Dump:
    """Context manager teeing stdout into a parameter-stamped report file."""

    def __init__(self, name, description, params):
        if not params:
            raise ValueError(
                f"Dump('{name}') requires a non-empty params mapping. A number "
                "saved without the choices that produced it is traceable but "
                "not verifiable -- see this module's docstring."
            )
        self.name = name
        self.description = description
        self.params = params
        self.path = REPORTS / f"{name}.txt"
        self._fh = None
        self._old = None

    def __enter__(self):
        REPORTS.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8")
        w = self._fh.write
        w(f"{self.description}\n")
        w("=" * 78 + "\n")
        w(f"generated : {datetime.now().isoformat(timespec='seconds')}\n")
        w(f"script    : scripts/{Path(sys.argv[0]).name}\n")
        w(f"git commit: {_git_commit()}\n")
        w("\nPARAMETERS -- the choices that define this measurement\n")
        w("-" * 78 + "\n")
        width = max(len(str(k)) for k in self.params)
        for k, v in self.params.items():
            w(f"  {str(k):<{width}} : {v}\n")
        w("-" * 78 + "\n")
        w("A number here without its parameters above is not reproducible.\n")
        w("=" * 78 + "\n\n")
        self._fh.flush()
        self._old = sys.stdout
        sys.stdout = _Tee(self._old, self._fh)
        return self

    def __exit__(self, *exc):
        sys.stdout = self._old
        if self._fh:
            self._fh.close()
        print(f"\n  [dump] wrote {self.path.relative_to(ROOT)}")
        return False
