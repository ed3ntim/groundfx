# SPDX-License-Identifier: GPL-3.0-or-later
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
    crumb = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P, "Scale": 190.0, "Detail": 3.0,
                          "Roughness": 0.65}), 0)

    inv = 1.0 / grain_size
    vor = g.node("ShaderNodeTexVoronoi", {"Vector": P, "Scale": inv,
                                          "Randomness": 1.0},
                 feature="F1", voronoi_dimensions="3D")
    d = g.out(vor, "Distance") / 0.6
    dome = (1.0 - d * d).max(0.0).sqrt()
    cell = g.out(vor, "Color")
    cid = cell.x
    # facet tilt: a random vector per grain, used as a bump gradient
    tilt = (cell - (0.5, 0.5, 0.5)) * 2.0

    glint = g.math("MULTIPLY", cid.gt(0.9),
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
    # pores of broken snow: darker and bluer where the crumb noise is low
    pore = (1.0 - sfnstep((crumb - 0.32) / 0.2)) * broken
    col = col * (0.96 + meso * 0.06) * cavity * (1.0 - wet * 0.25)
    col = g.mix(col, col * g.vec(0.72, 0.80, 0.93), pore * 0.7)

    roughness = g.mix(rough * (0.85 + macro * 0.3), 0.04, glint)
    roughness = g.mix(roughness, rough * 0.6, comp * 0.5)
    roughness = g.mix(roughness, 0.9, broken * 0.5)
    roughness = g.mix(roughness, 0.08, wet).clamp(0.02, 1.0)

    relief = dome * (1.0 - comp * 0.7) * detail
    bump = g.node("ShaderNodeBump", {"Strength": 1.0,
                                     "Distance": grain_size * 0.7,
                                     "Height": relief})
    facet = g.node("ShaderNodeBump",
                   {"Strength": glint, "Distance": grain_size * 0.8,
                    "Height": tilt.dot(P * inv) * 0.5,
                    "Normal": g.out(bump, "Normal")})
    soft = g.node("ShaderNodeBump",
                  {"Strength": 0.4 + broken * 0.5, "Distance": 0.004,
                   "Height": meso + (crumb - 0.5) * broken * 0.8,
                   "Normal": g.out(facet, "Normal")})

    bsdf = g.node("ShaderNodeBsdfPrincipled",
                  {"Base Color": col, "Roughness": roughness, "IOR": 1.31,
                   "Subsurface Weight": 0.75,
                   "Subsurface Radius": (0.6, 0.85, 1.0),
                   # mm-scale mean free path: soft, but grains survive
                   "Subsurface Scale": 0.0035 * (1.0 - comp * 0.4),
                   "Specular IOR Level": 0.5,
                   "Normal": g.out(soft, "Normal"),
                   "Coat Weight": wet * 0.8, "Coat Roughness": 0.05,
                   "Coat IOR": 1.33})
    # Random-walk scattering loses light through the open border of the
    # simulation grid and of the surround ring: a dark line where they meet.
    # The surface-based method does not look behind the surface.
    bsdf.subsurface_method = "BURLEY"
    clumps = g.out(g.node("ShaderNodeTexNoise",
                          {"Vector": P, "Scale": 40.0, "Detail": 5.0,
                           "Roughness": 0.6}), 0)
    disp = g.node("ShaderNodeDisplacement",
                  {"Height": clumps - 0.5, "Midlevel": 0.0,
                   "Scale": 0.002 * (1.0 - comp * 0.8)})
    out = g.node("ShaderNodeOutputMaterial",
                 {"Surface": g.out(bsdf, 0), "Displacement": g.out(disp, 0)})
    out.target = "ALL"
    b.layout()
