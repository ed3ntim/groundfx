# SPDX-License-Identifier: GPL-3.0-or-later
"""Physically grounded sand surface shader (look v2).

Built from what sand *is*, not from generic noise:

* **Grains at true scale.** Two interleaved Voronoi layers at the grain
  diameter (default 0.4 mm, medium sand) form round-topped grains; the higher
  of the two wins, like grains lying on each other. Their height drives a
  bump whose distance is a fraction of the real diameter, and the gaps
  between grains darken (contact shadow), which is most of why sand reads as
  granular rather than as a textured plane.
* **Mineral palette.** Each grain draws its colour from a constant colour
  ramp of real constituents: clear/frosted quartz, white quartz, feldspar,
  iron-stained grains and a few dark lithics. Averaged at distance this
  gives the familiar warm beige, up close individual grains.
* **Glints.** A share of grains are quartz facets with low roughness, so a
  low sun picks out single sparkling grains instead of a plastic sheen.
* **Physics fields.** ``gfx_comp`` (packed by an object) flattens the grain
  relief and darkens slightly; the Wetness control darkens, smooths and adds
  a thin water film (coat).
* **Displacement** carries only sub-centimetre clods/undulation (bump unless
  the Hero Detail subdivision is on), never the grains themselves.

Sizes are metres in object space (the domain is unscaled). Cycles first;
EEVEE renders the same graph with bump only.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_expr import Expr
from ..constants import ATTR_COMP

GRAIN_SIZE = 0.0004   # metres, medium sand

# Mineral palette (linear RGB) with cumulative thresholds on a per-grain id.
PALETTE = (
    (0.00, (0.47, 0.36, 0.22)),   # frosted quartz, warm
    (0.30, (0.58, 0.47, 0.32)),   # clear quartz over light
    (0.52, (0.70, 0.64, 0.54)),   # white quartz
    (0.64, (0.56, 0.36, 0.25)),   # feldspar, pinkish
    (0.76, (0.42, 0.26, 0.12)),   # iron-stained
    (0.88, (0.33, 0.30, 0.26)),   # grey lithic
    (0.95, (0.07, 0.065, 0.06)),  # dark lithic / magnetite
)


def set_ramp(cr, stops) -> None:
    """Set colour-ramp stops. Positions re-sort the list on assignment, so
    stops are created at their final position and coloured by lookup."""
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position = stops[0][0]
    for pos, _ in stops[1:]:
        cr.elements.new(pos)
    for pos, rgb in stops:
        el = min(cr.elements, key=lambda e: abs(e.position - pos))
        el.color = (*rgb, 1.0)


def build(tree, ctrl, *, grain_size=GRAIN_SIZE) -> None:
    """Fill ``tree`` (cleared material tree). ``ctrl`` maps control names to
    the four Look nodes: base (RGB), rough, detail, wet (Value)."""
    b = NodeTreeBuilder(tree)
    g = Expr(b)
    base = g.out(ctrl["base"], 0)
    rough = g.out(ctrl["rough"], 0)
    detail = g.out(ctrl["detail"], 0)
    wet = g.out(ctrl["wet"], 0)

    P = g.out(b.add("ShaderNodeTexCoord"), "Object")
    comp = g.out(g.node("ShaderNodeAttribute", attribute_name=ATTR_COMP,
                        attribute_type="GEOMETRY"), "Factor").clamp(0.0, 1.0)

    inv = 1.0 / grain_size
    v1 = g.node("ShaderNodeTexVoronoi", {"Vector": P, "Scale": inv,
                                         "Randomness": 0.9},
                feature="F1", voronoi_dimensions="3D")
    v2 = g.node("ShaderNodeTexVoronoi",
                {"Vector": P + (0.37, 0.11, 0.73), "Scale": inv * 1.37,
                 "Randomness": 1.0},
                feature="F1", voronoi_dimensions="3D")

    def dome(vor, radius):
        d = g.out(vor, "Distance") / radius
        return (1.0 - d * d).max(0.0).sqrt()

    d1 = dome(v1, 0.62)
    d2 = dome(v2, 0.55) * 0.85
    top2 = d2.gt(d1)
    height = d1.max(d2)
    grain_id = g.mix(g.out(v1, "Color").x, g.out(v2, "Color").x, top2)
    grain_r2 = g.mix(g.out(v1, "Color").y, g.out(v2, "Color").y, top2)

    ramp = g.node("ShaderNodeValToRGB", {0: grain_id})
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    set_ramp(cr, PALETTE)
    albedo = g.out(ramp, "Color")

    # per-grain brightness jitter, meso clumps, macro hue drift
    jitter = 0.85 + grain_r2 * 0.3
    meso = g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": P, "Scale": inv / 45.0, "Detail": 3.0}),
                 0)
    macro = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P, "Scale": 2.5, "Detail": 2.0}), 0)
    tone = jitter * (0.9 + meso * 0.2) * (0.94 + macro * 0.12)

    # gaps between grains sit in shadow; packed sand closes the gaps
    relief = height * (1.0 - comp * 0.6)
    cavity = 0.55 + 0.45 * (relief.pow(0.5) + comp * 0.6).min(1.0)
    dry = albedo * (tone * cavity * (1.0 - comp * 0.08))
    color = dry * base * (1.0 - wet * 0.55)

    # glints: ~12 % of grains are polished quartz facets
    glint = grain_r2.gt(0.88)
    r_dry = g.mix(rough, rough * 0.28, glint)
    roughness = g.mix(r_dry, rough * 0.35, wet).clamp(0.02, 1.0)

    bump_fine = g.node("ShaderNodeBump",
                       {"Strength": 1.0, "Distance": grain_size * 0.45,
                        "Height": relief * detail})
    clods = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P, "Scale": 90.0, "Detail": 6.0,
                          "Roughness": 0.6}), 0)

    bsdf = g.node("ShaderNodeBsdfPrincipled",
                  {"Base Color": color, "Roughness": roughness, "IOR": 1.54,
                   "Specular IOR Level": 0.5,
                   "Normal": g.out(bump_fine, "Normal"),
                   "Coat Weight": wet * 0.6, "Coat Roughness": 0.05,
                   "Coat IOR": 1.33})
    disp = g.node("ShaderNodeDisplacement",
                  {"Height": clods - 0.5, "Midlevel": 0.0,
                   "Scale": 0.0012 * (1.0 - comp * 0.7)})
    out = g.node("ShaderNodeOutputMaterial",
                 {"Surface": g.out(bsdf, 0),
                  "Displacement": g.out(disp, 0)})
    out.target = "ALL"
    b.layout()
