#!/usr/bin/env python3
"""
Make the conda env's native DLLs resolvable. IMPORT THIS FIRST.

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import env_bootstrap  # noqa: F401  -- MUST precede numpy/rasterio

    import numpy as np
    import rasterio

WHY THIS EXISTS AND WHY IT MUST BE FIRST
========================================
Running this environment's python.exe without an activated shell fails at
the first native-extension import with **exit code 127 and no traceback**.
It is a DLL resolution failure inside the loader, not a Python exception,
so nothing is raised, nothing is printed, and the script appears simply to
have done nothing. That symptom cost real debugging time in the
predecessor project and again here.

Python 3.8+ on Windows no longer searches PATH for extension-module DLLs,
so `os.add_dll_directory` is required -- setting PATH alone is NOT enough,
though PATH is still set because the GDAL/PROJ command-line tools and
subprocess calls rely on it.

Because the failure happens at import, this module has to run before the
first `import numpy` / `import rasterio` / `import matplotlib` in the
calling script. That is why it is a bare `import` with a side effect
rather than a function to call: a function would be too late if the caller
had already imported numpy above it.

HISTORY, so the next person does not re-derive it
=================================================
This block was copy-pasted into four scripts before being extracted:
render_figures.py, render_3d.py, render_personal.py and
analyze_hydrology.py. Each was added only after that script silently
exited 127 -- in analyze_hydrology.py's case after a full analysis had
been written and appeared to produce nothing. Four independent
rediscoveries of the same fifteen lines was enough evidence there would
be a fifth.

The env path is hardcoded because this is a single-machine project. A
portable version would resolve it from sys.executable; that change is
deferred rather than guessed at, and is flagged here so project three
inherits the note along with the module.
"""
import os
from pathlib import Path

ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")

# Extension-module DLLs: the only mechanism that works on Python 3.8+.
for _d in (ENV / "Library" / "bin",
           ENV / "Library" / "mingw-w64" / "bin",
           ENV / "Scripts",
           ENV):
    if _d.is_dir():
        try:
            os.add_dll_directory(str(_d))
        except (AttributeError, OSError):
            # AttributeError on non-Windows; OSError if the path vanished
            # between the is_dir() check and here. Neither is fatal --
            # an activated shell resolves these anyway.
            pass

# PATH still matters for subprocess calls to pdal.exe, gdal_translate.exe
# and gdaldem.exe, which this project makes from several scripts.
os.environ["PATH"] = os.pathsep.join(
    [str(ENV), str(ENV / "Library" / "bin"), str(ENV / "Scripts"),
     os.environ.get("PATH", "")])

# setdefault, not assignment: an activated shell has already set these
# correctly and should win. Without GDAL_DATA, gdalinfo emits a noisy but
# harmless "Cannot find gdalvrt.xsd" warning on every call.
os.environ.setdefault("GDAL_DATA", str(ENV / "Library" / "share" / "gdal"))
os.environ.setdefault("PROJ_LIB", str(ENV / "Library" / "share" / "proj"))


def tool(name):
    """Absolute path to a CLI tool in the env, for subprocess calls.

    The GDAL/PDAL executables live in Library/bin, not the env root, which
    is its own recurring trip-up in this project.
    """
    exe = ENV / "Library" / "bin" / (name if name.endswith(".exe")
                                     else name + ".exe")
    return str(exe)


def env():
    """A copy of os.environ suitable for passing to subprocess."""
    return dict(os.environ)
