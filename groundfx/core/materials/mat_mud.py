# SPDX-License-Identifier: GPL-3.0-or-later
"""Physically grounded mud shader (look v2).

Mud is clay/silt particles in water. What the eye reads:

* **A water film.** Wet mud is a dark matte body under a thin, glossy water
  layer: sharp sky reflections on the crests, the body nearly black-brown
  in the troughs where water pools. -> Principled body + clear coat, coat
  weight from wetness, troughs wetter than crests.
* **Viscous relief.** Smeared, lumpy, glossy folds rather than grains;
  where an object pushed through (gfx_comp) the surface is smoothed and
  wetter (squeezed water), streaked along the motion (gfx_flow).
* **Inclusions.** Small grit and pebbles (a few mm), lighter and matte,
  half sunk.
* **Drying.** As wetness drops the coat fades and the body lightens and
  greys - the same slider moves the solver's cohesion.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_expr import Expr
from ..constants import ATTR_COMP, ATTR_FLOW


def build(tree, ctrl) -> None:
    b = NodeTreeBuilder(tree)
    g = Expr(b)
    base = g.out(ctrl["base"], 0)
    rough = g.out(ctrl["rough"], 0)
    detail = g.out(ctrl["detail"], 0)
    wet = g.out(ctrl["wet"], 0)

    P = g.out(b.add("ShaderNodeTexCoord"), "Object")
    comp = g.out(g.node("ShaderNodeAttribute", attribute_name=ATTR_COMP,
                        attribute_type="GEOMETRY"), "Factor").clamp(0.0, 1.0)
    flow = g.out(g.node("ShaderNodeAttribute", attribute_name=ATTR_FLOW,
                        attribute_type="GEOMETRY"), "Vector")

    # smear: stretch the noise domain along the motion where pushed
    Ps = P - flow * (P.dot(flow) * (comp * 0.75))
    lumps = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": Ps, "Scale": 9.0, "Detail": 6.0,
                          "Roughness": 0.55, "Distortion": 0.4}), 0)
    folds = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": Ps, "Scale": 35.0, "Detail": 4.0,
                          "Roughness": 0.5}), 0)
    height = lumps * 0.7 + folds * 0.3

    # grit: a few % of Voronoi cells at ~3 mm become small stones
    vor = g.node("ShaderNodeTexVoronoi", {"Vector": P, "Scale": 300.0,
                                          "Randomness": 1.0},
                 feature="F1", voronoi_dimensions="3D")
    vd = g.out(vor, "Distance") / 0.3
    # half-sunk grit: flat-topped, irregular (noise-warped rim), not beads
    rim = g.out(g.node("ShaderNodeTexNoise", {"Vector": P, "Scale": 900.0,
                                               "Detail": 2.0}), 0)
    stone = g.math("MULTIPLY", g.out(vor, "Color").x.gt(0.95),
                   ((1.0 - vd * vd) * 2.0 - 0.6 + rim * 0.6).clamp(0.0, 1.0))
    stone = stone * (1.0 - comp)

    # water pools in troughs; pushed mud is squeezed wetter
    film = (wet * (1.25 - height) + comp * 0.3).clamp(0.0, 1.0)
    body = g.vec(0.12, 0.07, 0.035) * base        # wet humic brown
    dry_body = g.vec(0.24, 0.17, 0.105) * base    # dried clay
    col = g.mix(dry_body, body, wet.clamp(0.0, 1.0)) * (0.75 + lumps * 0.5)
    col = g.mix(col, g.vec(0.20, 0.17, 0.13), stone.gt(0.05))

    roughness = g.mix(rough, 0.55, stone.gt(0.05)).clamp(0.05, 1.0)
    bump = g.node("ShaderNodeBump",
                  {"Strength": 0.6 * (1.0 - comp * 0.5),
                   "Distance": 0.006 * detail, "Height": height})
    bump2 = g.node("ShaderNodeBump",
                   {"Strength": 0.7, "Distance": 0.0005, "Height": stone,
                    "Normal": g.out(bump, "Normal")})
    bsdf = g.node("ShaderNodeBsdfPrincipled",
                  {"Base Color": col, "Roughness": roughness,
                   "Normal": g.out(bump2, "Normal"),
                   "Coat Weight": film * 0.6,
                   "Coat Roughness": 0.08 + (1.0 - wet) * 0.2,
                   "Coat IOR": 1.33,
                   "Coat Normal": g.out(bump, "Normal")})
    disp = g.node("ShaderNodeDisplacement",
                  {"Height": height - 0.5 + stone * 0.12, "Midlevel": 0.0,
                   "Scale": 0.006 * (1.0 - comp * 0.6)})
    out = g.node("ShaderNodeOutputMaterial",
                 {"Surface": g.out(bsdf, 0), "Displacement": g.out(disp, 0)})
    out.target = "ALL"
    b.layout()
