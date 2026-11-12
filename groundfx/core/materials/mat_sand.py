# SPDX-License-Identifier: GPL-3.0-or-later
"""Sand surface shader (gen 3).

Built from what sand *is* and from what the simulation knows about it.

Grain scale (unchanged idea from look v2, it holds up under a macro lens):

* **Grains at true size.** Two interleaved Voronoi layers at the grain
  diameter (0.4 mm, medium sand) form round-topped grains; the higher wins,
  like grains lying on each other. Gaps darken (contact shadow).
* **Mineral palette.** Each grain draws its colour from real constituents:
  quartz in several states, feldspar, iron-stained grains, dark lithics.
* **Glints.** A share of grains are clean quartz facets with low roughness.

New in gen 3, the scale between grain and simulation cell:

* **Moisture from the simulation.** ``gfx_damp`` marks sand the solver has
  just dug up or pushed: it comes from below the dry crust, so it is darker,
  more saturated and a little smoother, and it dries back over time. This
  is the strongest single cue that a track is real.
* **Ripple sorting.** The same ripple function that displaces the geometry
  (``surface_fn``) sorts the grains: heavy dark minerals collect in the
  troughs, crests are a touch lighter. Where the surface stage has no
  geometry for the ripples (far field, or no stage at all) the shader bumps
  them instead, weighted by ``gfx_geo``.
* **Disturbed relief.** ``gfx_dist`` adds the crumbly millimetre relief of
  loosened sand below what the geometry carries.
* **Packed tracks.** ``gfx_comp`` closes the gaps between grains and adds
  fine scrape lines along ``gfx_flow``, the direction the object moved.
* **No plastic.** Fully rough diffuse lobe (Oren-Nayar), weak specular: a
  bed of grains scatters back toward the light and has no sheen of its own.

Sizes are metres in object space (the domain is unscaled).
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_expr import Expr
from ..constants import ATTR_COMP, ATTR_DIST, ATTR_DAMP, ATTR_GEO, ATTR_FLOW
from .. import surface_fn as sfn

GRAIN_SIZE = 0.0004   # metres, medium sand

# Mineral palette (linear RGB) with cumulative thresholds on a per-grain id.
PALETTE = (
    (0.00, (0.52, 0.38, 0.21)),   # frosted quartz, warm
    (0.30, (0.64, 0.50, 0.31)),   # clear quartz over light
    (0.52, (0.76, 0.68, 0.55)),   # white quartz
    (0.64, (0.62, 0.38, 0.24)),   # feldspar, pinkish
    (0.76, (0.45, 0.26, 0.11)),   # iron-stained
    (0.88, (0.33, 0.29, 0.24)),   # grey lithic
    (0.95, (0.07, 0.065, 0.06)),  # dark lithic / magnetite
)
# What water does to the albedo of sand (pore water couples light in).
DAMP_TINT = (0.52, 0.47, 0.41)


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


def _attr(g, name, out="Factor"):
    return g.out(g.node("ShaderNodeAttribute", attribute_name=name,
                        attribute_type="GEOMETRY"), out)


def build(tree, ctrl, *, grain_size=GRAIN_SIZE) -> None:
    """Fill ``tree`` (cleared material tree). ``ctrl`` maps control names to
    nodes: base (RGB), rough, detail, wet, ripple_len, ripple_amt, wind."""
    b = NodeTreeBuilder(tree)
    g = Expr(b)
    base = g.out(ctrl["base"], 0)
    rough = g.out(ctrl["rough"], 0)
    detail = g.out(ctrl["detail"], 0)
    wet = g.out(ctrl["wet"], 0)
    rip_len = g.out(ctrl["ripple_len"], 0)
    rip_amt = g.out(ctrl["ripple_amt"], 0)
    wind = g.out(ctrl["wind"], 0)

    P = g.out(b.add("ShaderNodeTexCoord"), "Object")
    P2 = g.vec(P.x, P.y, 0.0)
    comp = _attr(g, ATTR_COMP).clamp(0.0, 1.0)
    dist = _attr(g, ATTR_DIST).clamp(0.0, 1.0)
    damp = _attr(g, ATTR_DAMP).clamp(0.0, 1.0)
    geo_w = _attr(g, ATTR_GEO).clamp(0.0, 1.0)
    flow = _attr(g, ATTR_FLOW, "Vector")

    # ---- meso fields ------------------------------------------------------
    rip = sfn.ripple_height(g, P2, rip_len, wind)
    w_rip = sfn.smoothstep(1.0 - dist * 1.6) * (1.0 - comp)
    has_rip = (rip_amt * 400.0).clamp(0.0, 1.0)
    trough = ((0.15 - rip) * 0.9).clamp(0.0, 1.0) * w_rip * has_rip
    crest = ((rip - 0.35) * 1.2).clamp(0.0, 1.0) * w_rip * has_rip
    moist = (damp * 0.8).max(wet)
    loose = sfn.smoothstep(dist) * (1.0 - comp)

    # ---- grains -------------------------------------------------------------
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

    # Sorting: troughs hold more of the heavy dark grains. Pushing the id up
    # the palette makes more grains land in the lithic/magnetite bins.
    sort_patch = g.out(g.node("ShaderNodeTexNoise",
                              {"Vector": P2, "Scale": 9.0, "Detail": 3.0}), 0)
    grain_sel = (grain_id + trough * sort_patch * 0.34).min(1.0)
    ramp = g.node("ShaderNodeValToRGB", {0: grain_sel})
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    set_ramp(cr, PALETTE)
    albedo = g.out(ramp, "Color")

    # per-grain brightness jitter, clumps, patches, long streaks down the wind
    jitter = 0.85 + grain_r2 * 0.3
    meso = g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": P, "Scale": inv / 45.0, "Detail": 3.0}), 0)
    macro = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P2, "Scale": 2.5, "Detail": 3.0}), 0)
    c = g.math("COSINE", wind)
    s = g.math("SINE", wind)
    along = P2.x * c + P2.y * s
    across = P2.y * c - P2.x * s
    streak = g.out(g.node("ShaderNodeTexNoise",
                          {"Vector": g.vec(along * 1.5, across * 22.0, 5.0),
                           "Scale": 1.0, "Detail": 2.0}), 0)
    tone = (jitter * (0.9 + meso * 0.2) * (0.90 + macro * 0.2)
            * (0.95 + streak * 0.1 * (1.0 - dist)) * (1.0 + crest * 0.07))

    # gaps between grains sit in shadow; packed sand closes the gaps
    relief = height * (1.0 - comp * 0.6)
    cavity = 0.55 + 0.45 * (relief.pow(0.5) + comp * 0.6).min(1.0)
    dry = albedo * (tone * cavity * (1.0 - comp * 0.06))
    damp_mul = g.mix(g.vec(1.0, 1.0, 1.0), g.vec(*DAMP_TINT), moist)
    color = dry * base * damp_mul

    # ---- roughness -----------------------------------------------------------
    glint = g.math("MULTIPLY", grain_r2.gt(0.88), 1.0 - moist * 0.7)
    r_dry = g.mix(rough, rough * 0.28, glint)
    roughness = g.mix(r_dry, rough * 0.55, moist)
    roughness = (roughness * (1.0 - comp * 0.15)).clamp(0.02, 1.0)
    film = sfn.smoothstep((wet - 0.45) / 0.5)   # standing water film

    # ---- normal: far ripples, loose crumbs, scrape lines, grains -----------
    far = g.node("ShaderNodeBump",
                 {"Strength": 1.0 - geo_w, "Distance": 1.0,
                  "Height": rip * w_rip * (rip_amt * 0.5)})
    crumb = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P, "Scale": 420.0, "Detail": 4.0,
                          "Roughness": 0.65}), 0)
    crumbs = g.node("ShaderNodeBump",
                    {"Strength": 0.7, "Distance": 0.0012,
                     "Height": crumb * (0.25 + loose * 0.75) * detail,
                     "Normal": g.out(far, "Normal")})
    f2 = g.vec(flow.x, flow.y, 0.0)
    f_len = f2.length()
    a = P2.dot(f2)
    q = P2.x * flow.y - P2.y * flow.x
    scrape = g.out(g.node("ShaderNodeTexNoise",
                          {"Vector": g.vec(a * 5.0, q * 900.0, 2.0),
                           "Scale": 1.0, "Detail": 2.0}), 0)
    scrapes = g.node("ShaderNodeBump",
                     {"Strength": 0.6, "Distance": 0.0006,
                      "Height": scrape * comp * f_len.min(1.0) * detail,
                      "Normal": g.out(crumbs, "Normal")})
    bump_fine = g.node("ShaderNodeBump",
                       {"Strength": 1.0, "Distance": grain_size * 0.45,
                        "Height": relief * detail,
                        "Normal": g.out(scrapes, "Normal")})

    inputs = {"Base Color": color, "Roughness": roughness, "IOR": 1.54,
              "Specular IOR Level": 0.3,
              "Normal": g.out(bump_fine, "Normal"),
              "Coat Weight": film * 0.7, "Coat Roughness": 0.04,
              "Coat IOR": 1.33}
    bsdf = g.node("ShaderNodeBsdfPrincipled", inputs)
    if "Diffuse Roughness" in bsdf.inputs:
        bsdf.inputs["Diffuse Roughness"].default_value = 1.0

    clods = g.out(g.node("ShaderNodeTexNoise",
                         {"Vector": P, "Scale": 260.0, "Detail": 5.0,
                          "Roughness": 0.6}), 0)
    disp = g.node("ShaderNodeDisplacement",
                  {"Height": clods - 0.5, "Midlevel": 0.0,
                   "Scale": 0.0009 * (1.0 - comp * 0.7)})
    out = g.node("ShaderNodeOutputMaterial",
                 {"Surface": g.out(bsdf, 0),
                  "Displacement": g.out(disp, 0)})
    out.target = "ALL"
    b.layout()
