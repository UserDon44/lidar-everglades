#!/usr/bin/env python3
"""
3D perspective render of a DEM with its hillshade draped as a texture.

Defaults to the Tucson Mountains tile, whose 328 ft of relief over 251
acres is the only surface in this project with enough vertical range for a
perspective view to add anything over a plan-view hillshade.

VERTICAL EXAGGERATION: every render states its exaggeration factor in both
the output filename and a caption burned into the image. An exaggerated
terrain render that doesn't declare itself is misleading -- a viewer has no
way to distinguish real relief from a stretched Z axis, and this project's
figures are supposed to be checkable by someone who can't re-run them.
Renders at VE=1.0 say "no vertical exaggeration" rather than staying silent,
so the absence of a caption never has to be interpreted.

Examples
--------
  python scripts/render_3d.py                          # VE 2, from the SE
  python scripts/render_3d.py --ve 1                   # true scale
  python scripts/render_3d.py --azimuth 315 --elev 20  # low sun-like angle from NW
  python scripts/render_3d.py --ve 3 --decimate 1 --size 2400 1600   # print quality
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import env_bootstrap  # noqa: F401,E402  -- MUST precede numpy/rasterio

import numpy as np
import rasterio

# Project root, resolved from this file's own location so these scripts
# run from any checkout rather than one hardcoded directory.
ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "output" / "figures"

DEFAULT_DEM = ROOT / "output" / "dem" / "dem_tucson_lastreturn_w33_s0.6_t1.3.tif"
DEFAULT_HS = ROOT / "output" / "hillshade" / "hs_tucson_lastreturn_w33_s0.6_t1.3.tif"


def clean_inset(nan_mask, max_frac=0.05):
    """Smallest symmetric inset that leaves no voids, or None if none does.

    Reprojected tiles (this project's Tucson tile came from UTM metres) carry
    a ragged nodata fringe where the rotated source footprint meets the
    axis-aligned output grid -- here a wedge tapering from ~1,175 void cells
    in row 0 down to ~11 by row 10, plus a persistent 11-cell sliver on the
    left and right columns. That fringe is what produces the vertical
    'curtain' walls in a naive render: cells straddling the taper get
    dropped to the base elevation and drawn as cliffs. Trimming to the clean
    interior removes the cause rather than masking the symptom.
    """
    n = min(nan_mask.shape)
    for t in range(0, int(n * max_frac)):
        if t == 0:
            if not nan_mask.any():
                return 0
            continue
        if not nan_mask[t:-t, t:-t].any():
            return t
    return None


def load_grid(dem_path, hs_path, decimate, trim=None):
    """Returns the render-ready grid plus relief/width measured at FULL
    resolution on the same region that is actually rendered.

    Two things this deliberately does not do: take relief from the decimated
    array (decimation drops extremes and under-reports it), or take it from
    the untrimmed raster (which would describe terrain not in the picture).
    The caption quotes these numbers, so they have to describe what a viewer
    is looking at."""
    with rasterio.open(dem_path) as ds:
        z_full = ds.read(1).astype(np.float64)
        nodata, res_full, bounds = ds.nodata, ds.res[0], ds.bounds
    with rasterio.open(hs_path) as hs_ds:
        hs_full = hs_ds.read(1)

    z_full = np.where((z_full == nodata) | ~np.isfinite(z_full), np.nan, z_full)

    t = trim if trim is not None else clean_inset(np.isnan(z_full))
    if t is None:
        t = 0
        print("  WARNING: no symmetric inset clears all voids; edge artifacts possible")
    if t:
        z_full = z_full[t:-t, t:-t]
        hs_full = hs_full[t:-t, t:-t]
    print(f"  trimmed {t} cells from each edge "
          f"({int(np.isnan(z_full).sum()):,} voids remain)")

    relief = float(np.nanmax(z_full) - np.nanmin(z_full))
    width_ft = z_full.shape[1] * res_full

    z, hs, res = z_full, hs_full, res_full
    if decimate > 1:
        z = z_full[::decimate, ::decimate]
        hs = hs_full[::decimate, ::decimate]
        res = res_full * decimate

    nrows, ncols = z.shape
    xs = bounds.left + (t + np.arange(ncols) * decimate + 0.5) * res_full
    ys = bounds.top - (t + np.arange(nrows) * decimate + 0.5) * res_full
    X, Y = np.meshgrid(xs, ys)
    return X, Y, z, hs, res, relief, width_ft


def build_mesh(X, Y, z, ve):
    """StructuredGrid with Z exaggerated about the surface minimum, so the
    base of the terrain stays put and only relief is stretched.

    Void cells are blanked, not filled. Filling them at the base elevation
    produces vertical 'curtain' walls dropping from the tile edge that look
    like real cliffs -- a rendering artifact indistinguishable from terrain
    to anyone reading the image.
    """
    import pyvista as pv

    zmin = np.nanmin(z)
    z_disp = zmin + (z - zmin) * ve
    nan_mask = np.isnan(z_disp)
    filled = np.where(nan_mask, zmin, z_disp)   # geometry placeholder only

    grid = pv.StructuredGrid(X, Y, filled)
    # DO NOT override grid.dimensions. PyVista sets it from the array shape
    # as (nrows, ncols, 1) and lays points out with ROWS varying fastest --
    # Fortran order. Forcing (ncols, nrows, 1) reinterprets that same point
    # list under swapped axes and shreds the surface into horizontal
    # streaks. It is a no-op on a SQUARE grid, which is the only reason it
    # survived this long: every tile in this project is square. Verified
    # empirically -- for X of shape (3, 5), PyVista reports dimensions
    # (3, 5, 1) and emits points as (x0,y0), (x0,y1), (x0,y2), (x1,y0)...
    #
    # Everything indexed against those points must therefore ravel in F
    # order: the texture coordinates below and the hidden-cell mask. The
    # previous tile/repeat pair built C-order texture coordinates, which
    # skews the drape on any non-square grid the same way.
    nrows, ncols = z.shape
    U, V = np.meshgrid(np.linspace(0.0, 1.0, ncols),
                       np.linspace(1.0, 0.0, nrows))
    grid.active_texture_coordinates = np.column_stack(
        [U.ravel(order="F"), V.ravel(order="F")])

    if nan_mask.any():
        # a cell is invalid if ANY of its four corner points is void
        bad = (nan_mask[:-1, :-1] | nan_mask[1:, :-1] |
               nan_mask[:-1, 1:] | nan_mask[1:, 1:])
        grid.hide_cells(bad.ravel(order="F"), inplace=True)
    return grid


def camera_position(bounds_xyz, azimuth_deg, elev_deg, distance_mult):
    """Place the camera on a compass bearing (0=N, 90=E) at a given angle
    above the horizon, looking at the scene centre."""
    xmin, xmax, ymin, ymax, zmin, zmax = bounds_xyz
    cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2
    diag = float(np.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2))
    d = diag * distance_mult

    az, el = np.radians(azimuth_deg), np.radians(elev_deg)
    # bearing measured clockwise from north (+Y)
    pos = (cx + d * np.cos(el) * np.sin(az),
           cy + d * np.cos(el) * np.cos(az),
           cz + d * np.sin(el))
    return [pos, (cx, cy, cz), (0, 0, 1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    ap.add_argument("--hillshade", type=Path, default=DEFAULT_HS)
    ap.add_argument("--ve", type=float, default=2.0,
                    help="vertical exaggeration (1.0 = true scale). Default 2.0")
    ap.add_argument("--azimuth", type=float, default=135.0,
                    help="camera compass bearing, 0=N 90=E 180=S 270=W. Default 135 (SE)")
    ap.add_argument("--elev", type=float, default=30.0,
                    help="camera angle above horizon, degrees. Default 30")
    ap.add_argument("--distance", type=float, default=1.35,
                    help="camera distance as a multiple of scene diagonal. Default 1.35")
    ap.add_argument("--decimate", type=int, default=2,
                    help="sample every Nth cell; 1 = full resolution. Default 2")
    ap.add_argument("--trim", type=int, default=None,
                    help="cells to crop from each edge; default auto-detects the "
                         "smallest inset with no voids (see clean_inset)")
    ap.add_argument("--size", type=int, nargs=2, default=[1800, 1200], metavar=("W", "H"))
    ap.add_argument("--label", default="Tucson Mountains",
                    help="scene name used in the caption")
    ap.add_argument("--out", type=Path, default=None,
                    help="override output path (VE is still added to the caption)")
    ap.add_argument("--colormap", default=None,
                   help="matplotlib colormap for elevation colouring, "
                        "modulated by the hillshade. Omit for the plain "
                        "grayscale hillshade drape. Use a perceptually "
                        "uniform map (viridis, cividis, magma) -- rainbow "
                        "maps invent banding that reads as terrain steps.")
    ap.add_argument("--vmin", type=float, default=None,
                   help="fix the low end of the elevation colour scale. "
                        "REQUIRED when rendering a comparison pair: the "
                        "default per-render 2-98 percentile normalisation "
                        "means the same colour denotes DIFFERENT elevations "
                        "in two images, which silently defeats a height "
                        "comparison.")
    ap.add_argument("--vmax", type=float, default=None,
                   help="fix the high end of the elevation colour scale")
    ap.add_argument("--colorbar", action="store_true",
                   help="composite an elevation key onto the render. Without "
                        "it, brightness carries both height and illumination "
                        "and the colour ramp is not a readable scale.")
    ap.add_argument("--units", default="ft", choices=["ft", "m"],
                   help="linear unit of the DEM, for the caption only")
    ap.add_argument("--no-caption", action="store_true",
                    help="suppress the burned-in caption (the VE stays in the filename)")
    args = ap.parse_args()

    for p in (args.dem, args.hillshade):
        if not p.exists():
            sys.exit(f"missing input: {p}")
    if args.ve <= 0:
        sys.exit("--ve must be positive")

    import pyvista as pv
    pv.OFF_SCREEN = True

    X, Y, z, hs, res, relief, width_ft = load_grid(
        args.dem, args.hillshade, args.decimate, args.trim)
    print(f"  grid {z.shape[1]}x{z.shape[0]} at {res:.2f} ft/cell")

    grid = build_mesh(X, Y, z, args.ve)

    shade = hs[..., 0] if hs.ndim == 3 else hs
    if args.colormap:
        # Elevation colour modulated by the hillshade. The colour carries
        # height, the shading carries form; multiplying keeps both legible
        # without either inventing structure. Normalised on the 2nd-98th
        # percentile so a single outlier cell cannot flatten the ramp.
        import matplotlib
        from matplotlib.colors import Normalize
        lo = args.vmin if args.vmin is not None else float(np.nanpercentile(z, 2))
        hi = args.vmax if args.vmax is not None else float(np.nanpercentile(z, 98))
        rgba = matplotlib.colormaps[args.colormap](Normalize(lo, hi, clip=True)(z))
        col = rgba[..., :3]
        # 0.35 floor: pure multiplication drives shadowed faces to black and
        # destroys the elevation signal exactly where relief is steepest.
        rgb = col * (0.35 + 0.65 * (shade.astype(float) / 255.0))[..., None]
        rgb = np.clip(rgb * 255.0, 0, 255)
        rgb = np.nan_to_num(rgb, nan=255.0)
    else:
        rgb = np.dstack([shade] * 3)
    texture = pv.Texture(np.ascontiguousarray(rgb.astype(np.uint8)))

    pl = pv.Plotter(off_screen=True, window_size=list(args.size))
    pl.add_mesh(grid, texture=texture, ambient=0.25, diffuse=0.75, specular=0.05,
                show_scalar_bar=False)
    pl.set_background("white")
    pl.camera_position = camera_position(grid.bounds, args.azimuth, args.elev, args.distance)

    # true and apparent slope across the scene, so a viewer can calibrate how
    # much of what they're seeing is real
    true_pct = 100.0 * relief / width_ft
    exaggerated = abs(args.ve - 1.0) > 1e-9
    ve_txt = (f"VERTICAL EXAGGERATION {args.ve:g}x"
              if exaggerated else "NO VERTICAL EXAGGERATION (true scale)")
    u = args.units
    rel_fmt = f"{relief:.1f}" if relief < 20 else f"{relief:.0f}"
    if exaggerated:
        calib = (f"relief {rel_fmt} {u} over {width_ft:,.0f} {u} = {true_pct:.1f}% true; "
                 f"appears as {true_pct*args.ve:.1f}%")
    else:
        calib = f"relief {rel_fmt} {u} over {width_ft:,.0f} {u} = {true_pct:.1f}%"

    if not args.no_caption:
        pl.add_text(
            f"{args.label} - bare-earth DEM, "
            f"{'elevation colour x hillshade' if args.colormap else 'hillshade draped as texture'}\n"
            f"{ve_txt}\n"
            f"{calib}\n"
            f"camera {args.azimuth:g} deg bearing, {args.elev:g} deg above horizon",
            position="upper_left", font_size=11, color="black")

    ve_tag = "ve1_truescale" if abs(args.ve - 1.0) < 1e-9 else f"ve{args.ve:g}x".replace(".", "p")
    # scene slug comes from --label, never hardcoded: an earlier version
    # baked "tucson" into every filename, so rendering any other DEM would
    # have produced a file whose name asserted the wrong subject
    slug = re.sub(r"[^a-z0-9]+", "_", args.label.lower()).strip("_") or "scene"
    out = args.out or (FIG_DIR /
                       f"fig12_{slug}_3d_{ve_tag}_az{args.azimuth:g}_el{args.elev:g}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(out))
    pl.close()

    if args.colorbar and args.colormap:
        # Composited after the 3D pass rather than drawn by PyVista: the
        # mesh carries a texture, not a scalar field, so there is no mapper
        # for add_scalar_bar to key off. Matplotlib gets the exact same
        # normalisation used to build the texture, so the key is honest.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable

        img = plt.imread(str(out))
        ih, iw = img.shape[:2]
        fig = plt.figure(figsize=(iw / 100.0, ih / 100.0), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(img)
        ax.axis("off")
        # Left margin: the terrain fills the centre-right of the frame,
        # so a right-hand bar overlaps the mesh and clips its own title.
        cax = fig.add_axes([0.045, 0.15, 0.016, 0.30])
        sm = ScalarMappable(norm=Normalize(vmin=lo, vmax=hi), cmap=args.colormap)
        cb = fig.colorbar(sm, cax=cax)
        fixed = args.vmin is not None and args.vmax is not None
        # The scale's provenance goes in the LABEL, not a title above the
        # bar: a title there renders outside the axes and clips. It matters
        # because a per-render scale means the same colour denotes different
        # elevations in two images -- the reader has to be able to tell.
        cb.set_label(
            f"Elevation ({args.units}) - "
            + ("FIXED scale, comparable across panels" if fixed
               else "per-render scale, NOT comparable"),
            fontsize=8.5, color=("black" if fixed else "#b5423a"))
        cb.ax.tick_params(labelsize=8)
        fig.savefig(str(out), dpi=100)
        plt.close(fig)
        print(f"  colorbar composited ({lo:.2f}-{hi:.2f} {args.units}, "
              f"{'fixed' if fixed else 'PER-RENDER -- not comparable'})")
    print(f"saved {out}")
    print(f"  {ve_txt}; relief {relief:.1f} {args.units}; "
          f"camera az {args.azimuth:g} el {args.elev:g}")


if __name__ == "__main__":
    main()
