# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Physically grounded snow shader (look v2).

Snow is a packing of small ice grains in air. What the eye reads:

* **Volume scattering.** Light enters and leaves centimetres away: soft
  shading, glowing edges, blue in depth (ice absorbs red slightly more).
  -> Principled random-walk subsurface, radius blue-biased, near-white albedo.
* **Single-crystal glints.** Each grain has flat facets; in sun a scatter of
  them flashes like glitter, changing with the view. -> per-grain Voronoi
  cells: ~8 % get a near-mirror roughness and a random facet normal tilt.
* **Grain relief at true scale** (default 0.8 mm, settled snow): rounded
  grains and pores, faint at a distance, granular up close.
* **Packing (gfx_comp).** A footprint or track is denser: less air, so a
  little greyer/bluer, smoother, fewer glints.
* **Wetness** turns it into slush: darker, translucent-blue, glossy.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_expr import Expr
from ..constants import ATTR_COMP, ATTR_DIST
from ..surface_fn import smoothstep as sfnstep

GRAIN_SIZE = 0.0008
GLINT_SIZE = 0.0022   # metres, cell of one glinting crystal
GLINT_PLATE = 0.4     # radius of the plate in its cell (cell units)
GLINT_SHARE = 0.5     # share of cells that hold a plate
GLINT_UP = 0.6        # pull of the facet normal toward the surface normal
GLINT_EYE = 0.6       # pull toward the eye (makes up for too few crystals)
GLINT_SPREAD = 0.55   # random tilt of the facets
GLINT_ROUGH = 0.2
GLINT_GAIN = 0.5    # flash strength: ice Fresnel plus internal reflection


def build(tree, ctrl, *, grain_size=GRAIN_SIZE) -> None:
    b = NodeTreeBuilder(tree)
    g = Expr(b)
    base = g.out(ctrl["base"], 0)
    rough = g.out(ctrl["rough"], 0)
    detail = g.out(ctrl["detail"], 0)
    wet = g.out(ctrl["wet"], 0)

    P = g.out(b.add("ShaderNodeTexCoord"), "Object")
    comp = g.out(g.node("ShaderNodeAttribute", attribute_name=ATTR_COMP,
                        attribute_type="GEOMETRY"), "Factor").clamp(0.0, 1.0)

    # Broken snow (the solver's disturbance field): crumbly, matt, with
    # blue pores between the crumbs. Wind-packed snow around it stays
    # smooth and glittering.
    dist = g.out(g.node("ShaderNodeAttribute", attribute_name=ATTR_DIST,
                        attribute_type="GEOMETRY"), "Factor").clamp(0.0, 1.0)
    broken = dist * (1.0 - comp)
    # Broken snow is loose grains and tiny crumbs: a fine, irregular,
    # high-contrast grain. A smooth 5 mm noise read as a soft kneaded mass;
    # Voronoi cells with gaps (tried at 3.5 and 9 mm) read as reptile skin
    # and dried mud. The real loose grains are geometry (surface stage).
    crumb = sfnstep((g.out(g.node("ShaderNodeTexNoise",
                                  {"Vector": P, "Scale": 420.0, "Detail": 2.0,
                                   "Roughness": 0.7}), 0) - 0.3) / 0.4)

    inv = 1.0 / grain_size
    vor = g.node("ShaderNodeTexVoronoi", {"Vector": P, "Scale": inv,
                                          "Randomness": 1.0},
                 feature="F1", voronoi_dimensions="3D")
    d = g.out(vor, "Distance") / 0.6
    dome = (1.0 - d * d).max(0.0).sqrt()
    # Glints come from the larger crystals on top (surface hoar, broken
    # dendrites): flat plates of a couple of millimetres, far fewer than the
    # grains. Their own cells, a plate in the middle of some of them, each
    # with a random tilt. At grain size they would be a pixel or less.
    gvor = g.node("ShaderNodeTexVoronoi", {"Vector": P,
                                           "Scale": 1.0 / GLINT_SIZE,
                                           "Randomness": 1.0},
                  feature="F1", voronoi_dimensions="3D")
    gcell = g.out(gvor, "Color")
    plate = g.math("MULTIPLY", gcell.x.gt(1.0 - GLINT_SHARE),
                   g.out(gvor, "Distance").lt(GLINT_PLATE))
    tilt = (gcell - (0.5, 0.5, 0.5)) * 2.0

    glint = g.math("MULTIPLY", plate,
                   (1.0 - comp * 0.8) * (1.0 - broken * 0.6))
    meso = g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": P, "Scale": 14.0, "Detail": 4.0,
                         "Roughness": 0.55}), 0)
    macro = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P, "Scale": 2.0, "Detail": 2.0}), 0)

    albedo = g.vec(0.93, 0.95, 0.98) * base
    packed_tint = g.vec(0.80, 0.86, 0.95)
    col = g.mix(albedo, albedo * packed_tint, comp * 0.8)
    # pores between grains sit in (blue) shadow: the granular read up close
    cavity = 0.62 + 0.38 * (dome * (1.0 - comp * 0.6) + comp * 0.6).min(1.0)
    # gaps between the crumbs of broken snow: in blue shadow
    pore = (1.0 - sfnstep((crumb - 0.15) / 0.45)) * broken
    col = col * (0.96 + meso * 0.06) * cavity * (1.0 - wet * 0.25)
    col = g.mix(col, col * g.vec(0.72, 0.80, 0.93), pore * 0.7)

    roughness = rough * (0.85 + macro * 0.3)
    roughness = g.mix(roughness, rough * 0.6, comp * 0.5)
    roughness = g.mix(roughness, 0.9, broken * 0.5)
    roughness = g.mix(roughness, 0.08, wet).clamp(0.02, 1.0)

    relief = dome * (1.0 - comp * 0.7) * detail
    bump = g.node("ShaderNodeBump", {"Strength": 1.0,
                                     "Distance": grain_size * 0.7,
                                     "Height": relief})
    soft = g.node("ShaderNodeBump",
                  {"Strength": 0.4 + broken * 0.4, "Distance": 0.004,
                   "Height": meso + (crumb - 0.5) * broken * 0.5,
                   "Normal": g.out(bump, "Normal")})
    n_soft = g.out(soft, "Normal")
    bsdf = g.node("ShaderNodeBsdfPrincipled",
                  {"Base Color": col, "Roughness": roughness, "IOR": 1.31,
                   # Broken snow scatters less deep: light leaves a crumb
                   # at its own surface, not centimetres away, so crumbs
                   # keep their edges instead of melting into wax.
                   "Subsurface Weight": 0.75 - broken * 0.35,
                   "Subsurface Radius": (0.6, 0.85, 1.0),
                   # mm-scale mean free path: soft, but grains survive
                   "Subsurface Scale": 0.0035 * (1.0 - comp * 0.4)
                   * (1.0 - broken * 0.6),
                   "Specular IOR Level": 0.5,
                   "Normal": n_soft,
                   "Coat Weight": wet * 0.8, "Coat Roughness": 0.05,
                   "Coat IOR": 1.33})
    # Random-walk scattering loses light through the open border of the
    # simulation grid and of the surround ring: a dark line where they meet.
    # The surface-based method does not look behind the surface.
    bsdf.subsurface_method = "BURLEY"

    # A glinting crystal is one flat facet, and crystals lie in every
    # direction: the facets are tilted over most of the hemisphere, not a
    # few degrees, so snow sparkles in front light too (a facet then has to
    # face back up toward the sun). The flash is added on top: ice is clear,
    # so a facet that does not catch the sun shows the snow behind it, never
    # a dark mirror of the sky (a coat layer would darken it). Not a perfect
    # mirror either: a lobe of a degree or two lets enough facets catch the
    # sun disc (at roughness 0.04 it is a tenth of a degree).
    # Real snow has millions of crystals per square metre, these cells a
    # tenth of that: with facets spread evenly only a few dozen per square
    # metre would ever line up. The facets lean toward the eye a little to
    # make up for it; whether one flashes is still up to the sun.
    eye = g.out(b.add("ShaderNodeNewGeometry"), "Incoming")
    n_facet = (n_soft * GLINT_UP + eye * GLINT_EYE
               + tilt * GLINT_SPREAD).normalize()
    flash = g.node("ShaderNodeBsdfAnisotropic",
                   {"Color": g.vec(1.0, 1.0, 1.0) * (glint * (1.0 - wet)
                                                     * GLINT_GAIN),
                    "Roughness": GLINT_ROUGH, "Normal": n_facet})
    surface = g.node("ShaderNodeAddShader",
                     {0: g.out(bsdf, 0), 1: g.out(flash, 0)})
    clumps = g.out(g.node("ShaderNodeTexNoise",
                          {"Vector": P, "Scale": 40.0, "Detail": 5.0,
                           "Roughness": 0.6}), 0)
    disp = g.node("ShaderNodeDisplacement",
                  {"Height": clumps - 0.5, "Midlevel": 0.0,
                   "Scale": 0.002 * (1.0 - comp * 0.8)})
    out = g.node("ShaderNodeOutputMaterial",
                 {"Surface": g.out(surface, 0),
                  "Displacement": g.out(disp, 0)})
    out.target = "ALL"
    b.layout()
