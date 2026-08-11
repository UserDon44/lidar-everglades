#!/usr/bin/env python3
"""
PERSONAL / NON-DELIVERABLE terrain renders. Optimised to look good.

This script exists outside the project's figure discipline ON PURPOSE.
Output goes to output/renders_personal/, which is marked non-deliverable
in its own README. Nothing here may be cited, captioned into a report, or
used as evidence:

  - vertical exaggeration is heavy and NOT disclosed on the image
  - colormaps are chosen for drama, not perceptual uniformity
  - colour scales are per-render, so nothing is comparable
  - lighting is fabricated: multiple coloured key/fill/rim lights at
    angles no sun occupies
  - ambient occlusion darkens creases beyond anything physical

Every one of those is disqualifying for a deliverable and fine here. The
separation is the folder plus its README; if an image from this set ever
needs to go in a report, it must be re-rendered by render_3d.py under the
real rules rather than relabelled.

Unlike render_3d.py this does NOT drape a hillshade. The mesh is lit by
real light sources in the scene, so form comes from geometry and shading
rather than from a baked raster -- which is what makes rig changes and
PBR do anything at all.
"""
import argparse
import os
import sys
from pathlib import Path

_ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
for _d in (_ENV / "Library" / "bin", _ENV / "Library" / "mingw-w64" / "bin",
            _ENV / "Scripts", _ENV):
    if _d.is_dir():
        try:
            os.add_dll_directory(str(_d))
        except (AttributeError, OSError):
            pass
os.environ["PATH"] = os.pathsep.join(
    [str(_ENV), str(_ENV / "Library" / "bin"), str(_ENV / "Scripts"),
     os.environ.get("PATH", "")])
os.environ.setdefault("GDAL_DATA", str(_ENV / "Library" / "share" / "gdal"))
os.environ.setdefault("PROJ_LIB", str(_ENV / "Library" / "share" / "proj"))

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output" / "renders_personal"


# ----------------------------------------------------------------------
# LOOKS. Each is a full art direction: palette, background, material and
# a light rig. Lights are (azimuth OFFSET FROM CAMERA, elevation, colour,
# intensity).
#
# The offsets are camera-relative on purpose. An absolute rig only works
# from the one camera bearing it was tuned for -- swing the camera round
# and the key light ends up behind the terrain, which is how the first
# mosaic render came out nearly black. Relative offsets mean a look keeps
# its intent (raking key from the left, cool fill opposite, warm rim
# behind) at any bearing.
# ----------------------------------------------------------------------
LOOKS = {
    "golden": dict(
        clim_shift=0.18, cmap="afmhot", bg="#1a1206", bg_top="#4a2f14",
        metallic=0.22, roughness=0.62, ambient=0.22,
        lights=[(-50, 6, "#ffd9a0", 1.6),     # low warm key, raking
                (130, 34, "#3a5f8f", 0.42),     # cool sky fill
                (200, 15, "#ff8c42", 0.55)],   # warm rim
        ssao=dict(radius=14, bias=0.4, kernel_size=256, blur=True)),
    "ember": dict(
        clim_shift=0.38, cmap="inferno", bg="#000000", bg_top="#1b0206",
        metallic=0.42, roughness=0.44, ambient=0.20,
        lights=[(-40, 4, "#ff7a3f", 2.1),
                (150, 8, "#b23a5d", 1.0),
                (90, 55, "#2b1b4a", 0.35)],
        ssao=dict(radius=18, bias=0.3, kernel_size=256, blur=True)),
    "ice": dict(
        clim_shift=0.05, cmap="bone", bg="#0b1b2b", bg_top="#9fc4de",
        metallic=0.15, roughness=0.35, ambient=0.28,
        lights=[(-45, 22, "#eaf6ff", 1.25),
                (140, 12, "#5f9ecf", 0.55),
                (0, 72, "#ffffff", 0.40)],
        ssao=dict(radius=12, bias=0.5, kernel_size=256, blur=True)),
    "verdant": dict(
        clim_shift=0.1, cmap="gist_earth", bg="#0d1a12", bg_top="#7fb7c9",
        metallic=0.10, roughness=0.70, ambient=0.25,
        lights=[(-55, 28, "#fff2d6", 1.20),
                (125, 20, "#7fb7c9", 0.50),
                (185, 8, "#c9a227", 0.35)],
        ssao=dict(radius=13, bias=0.45, kernel_size=256, blur=True)),
    "noir": dict(
        clim_shift=0.22, cmap="gray", bg="#050505", bg_top="#161616",
        metallic=0.55, roughness=0.30, ambient=0.20,
        lights=[(-62, 3, "#ffffff", 2.2),      # single hard raker
                (115, 40, "#101820", 0.25)],
        ssao=dict(radius=22, bias=0.25, kernel_size=256, blur=True)),
    "magma": dict(
        clim_shift=0.34, cmap="magma", bg="#07030c", bg_top="#2a0f3a",
        metallic=0.35, roughness=0.50, ambient=0.20,
        lights=[(-58, 9, "#ffc79a", 1.9),
                (120, 25, "#8a5ac0", 0.85),
                (205, 45, "#ffe9c7", 0.30)],
        ssao=dict(radius=16, bias=0.35, kernel_size=256, blur=True)),
}


def clean_inset(nan_mask, max_frac=0.06):
    """Smallest symmetric inset with no voids. Reprojected tiles carry a
    ragged nodata fringe that renders as striped vertical curtains at the
    domain edge -- unmistakable at high exaggeration and ugly even by the
    loose standards of this folder."""
    n = min(nan_mask.shape)
    for t in range(0, int(n * max_frac)):
        if t == 0:
            if not nan_mask.any():
                return 0
            continue
        if not nan_mask[t:-t, t:-t].any():
            return t
    return None


def load(dem_path, decimate, trim_voids=True):
    with rasterio.open(dem_path) as ds:
        z = ds.read(1).astype(np.float64)
        nodata, res, bounds = ds.nodata, ds.res[0], ds.bounds
    z = np.where((z == nodata) | ~np.isfinite(z), np.nan, z)
    if trim_voids:
        t = clean_inset(np.isnan(z))
        if t:
            z = z[t:-t, t:-t]
            bounds = rasterio.coords.BoundingBox(
                bounds.left + t * res, bounds.bottom + t * res,
                bounds.right - t * res, bounds.top - t * res)
    if decimate > 1:
        z = z[::decimate, ::decimate]
        res *= decimate
    nrows, ncols = z.shape
    xs = bounds.left + (np.arange(ncols) + 0.5) * res
    ys = bounds.top - (np.arange(nrows) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    return X, Y, z, res


def build(X, Y, z, ve):
    import pyvista as pv
    zmin = np.nanmin(z)
    zd = zmin + (z - zmin) * ve
    nan = np.isnan(zd)
    grid = pv.StructuredGrid(X, Y, np.where(nan, zmin, zd))
    grid.dimensions = (X.shape[1], X.shape[0], 1)
    grid["elev"] = np.where(nan, zmin, z).ravel(order="C")
    if nan.any():
        bad = (nan[:-1, :-1] | nan[1:, :-1] | nan[:-1, 1:] | nan[1:, 1:])
        grid.hide_cells(bad.ravel(order="C"), inplace=True)
    return grid


def cam(bounds, az, el, dist):
    x0, x1, y0, y1, z0, z1 = bounds
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    diag = float(np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2))
    d = diag * dist
    a, e = np.radians(az), np.radians(el)
    return [(cx + d * np.cos(e) * np.sin(a), cy + d * np.cos(e) * np.cos(a),
             cz + d * np.sin(e)), (cx, cy, cz), (0, 0, 1)]


def light_at(bounds, az, el, colour, intensity):
    import pyvista as pv
    x0, x1, y0, y1, z0, z1 = bounds
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    diag = float(np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2))
    d = diag * 2.2
    a, e = np.radians(az), np.radians(el)
    pos = (cx + d * np.cos(e) * np.sin(a), cy + d * np.cos(e) * np.cos(a),
           cz + d * np.sin(e))
    lt = pv.Light(position=pos, focal_point=(cx, cy, cz), color=colour)
    lt.intensity = intensity
    lt.positional = False
    return lt


def render(dem, look, ve, az, el, dist, decimate, size, out, trim=True):
    import pyvista as pv
    pv.OFF_SCREEN = True
    spec = LOOKS[look]

    X, Y, z, res = load(dem, decimate, trim_voids=trim)
    grid = build(X, Y, z, ve)
    mesh = grid.extract_surface(algorithm='dataset_surface').compute_normals(
        cell_normals=False, point_normals=True, split_vertices=False)

    pl = pv.Plotter(off_screen=True, window_size=list(size), lighting="none")
    # Shift the low end of the colour range BELOW the data minimum so the
    # terrain occupies the bright part of the ramp instead of the black
    # floor. Purely cosmetic, which is the point of this folder.
    ev = mesh["elev"]
    lo, hi = float(np.nanmin(ev)), float(np.nanmax(ev))
    shift = spec.get("clim_shift", 0.0) * (hi - lo)
    pl.add_mesh(mesh, scalars="elev", cmap=spec["cmap"], show_scalar_bar=False,
                clim=(lo - shift, hi),
                pbr=True, metallic=spec["metallic"], roughness=spec["roughness"],
                ambient=spec["ambient"], smooth_shading=True,
                specular=0.6, specular_power=18)
    for (la, le, lc, li) in spec["lights"]:
        pl.add_light(light_at(grid.bounds, az + la, le, lc, li))
    pl.set_background(spec["bg"], top=spec.get("bg_top", spec["bg"]))
    pl.camera_position = cam(grid.bounds, az, el, dist)
    try:
        pl.enable_ssao(**spec["ssao"])
    except Exception as exc:
        print(f"    (ssao unavailable: {exc})")
    try:
        pl.enable_anti_aliasing("ssaa")
    except Exception:
        pass
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(out))
    pl.close()
    print(f"  {out.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dem", type=Path, required=True)
    ap.add_argument("--look", required=True, choices=sorted(LOOKS))
    ap.add_argument("--ve", type=float, default=6.0)
    ap.add_argument("--azimuth", type=float, default=300.0)
    ap.add_argument("--elev", type=float, default=14.0)
    ap.add_argument("--distance", type=float, default=1.9)
    ap.add_argument("--no-trim", action="store_true")
    ap.add_argument("--decimate", type=int, default=2)
    ap.add_argument("--size", type=int, nargs=2, default=[2000, 1250])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    render(a.dem, a.look, a.ve, a.azimuth, a.elev, a.distance,
           a.decimate, a.size, a.out, trim=not a.no_trim)


if __name__ == "__main__":
    main()
