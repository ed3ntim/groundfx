# SPDX-License-Identifier: GPL-3.0-or-later
"""Mud and standing-water shaders (gen 3).

Mud is clay and silt in water. How wet it is decides everything the eye
reads, and wetness is not uniform: it follows the ground.

* **Soaked near the water.** The surface stage reports how close each point
  is to the water table (``gfx_shore``). At the water's edge the mud is
  saturated: nearly black-brown under a continuous glossy film. A centimetre
  higher it is merely damp: lighter, satin, the film broken into patches.
  Rises dry to a pale matte crust that cracks. This gradient around every
  puddle is what makes the puddle sit *in* the mud.
* **Patchy film.** Even wet mud is not evenly glossy. The clear coat is
  gated by a noise threshold that moves with wetness, so highlights break up
  into irregular wet patches instead of a plastic sheen.
* **Worked mud is wetter.** Where an object went through (``gfx_comp``,
  ``gfx_dist``) water is squeezed to the surface: darker, glossier, smeared
  along the motion (``gfx_flow``).
* **Grit.** Fine sand-sized roughness in the body, a few half-sunk stones in
  the shader, and the real pebbles scattered by the surface stage.

``build_water`` is the puddle itself: murky, shallow, mirror-flat with a
trace of wind, letting the mud show through at the edges.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_expr import Expr
from ..constants import (
    ATTR_COMP, ATTR_FLOW, ATTR_DIST, ATTR_SHORE, ATTR_PEBBLE,
)
from .. import surface_fn as sfn
from .mat_sand import STONES, set_ramp

WET_BODY = (0.060, 0.040, 0.024)    # saturated humic clay
DAMP_BODY = (0.082, 0.054, 0.031)
DRY_BODY = (0.34, 0.27, 0.19)       # dried crust


def _attr(g, name, out="Factor"):
    return g.out(g.node("ShaderNodeAttribute", attribute_name=name,
                        attribute_type="GEOMETRY"), out)


def _noise(g, vec, scale, detail=2.0, roughness=0.5, distortion=0.0):
    return g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": vec, "Scale": scale, "Detail": detail,
                         "Roughness": roughness, "Distortion": distortion}), 0)


def build(tree, ctrl) -> None:
    b = NodeTreeBuilder(tree)
    g = Expr(b)
    base = g.out(ctrl["base"], 0)
    rough = g.out(ctrl["rough"], 0)
    detail = g.out(ctrl["detail"], 0)
    wet = g.out(ctrl["wet"], 0)

    P = g.out(b.add("ShaderNodeTexCoord"), "Object")
    comp = _attr(g, ATTR_COMP).clamp(0.0, 1.0)
    dist = _attr(g, ATTR_DIST).clamp(0.0, 1.0)
    shore = _attr(g, ATTR_SHORE).clamp(0.0, 1.0)
    flow = _attr(g, ATTR_FLOW, "Vector")
    peb = _attr(g, ATTR_PEBBLE)
    is_peb = peb.gt(0.01)

    # smear: stretch the noise domain along the motion where pushed
    Ps = P - flow * (P.dot(flow) * (comp * 0.8))
    lumps = _noise(g, Ps, 9.0, 6.0, 0.55, 0.4)
    folds = _noise(g, Ps, 38.0, 4.0, 0.5)
    fine = _noise(g, P, 420.0, 4.0, 0.65)
    height = lumps * 0.55 + folds * 0.3 + fine * 0.15

    # ---- local wetness --------------------------------------------------------
    # slider sets the level; the shore band and worked mud push it up, high
    # spots of the relief sit a little drier than the creases
    local = (wet * 0.62 + shore * 0.5 + comp * 0.3 + dist * 0.35
             + (0.5 - height) * 0.2).clamp(0.0, 1.0)
    soaked = sfn.smoothstep((local - 0.55) / 0.35)
    dryness = sfn.smoothstep((0.38 - local) / 0.3)

    # ---- body -------------------------------------------------------------------
    col = g.mix(g.vec(*DAMP_BODY), g.vec(*WET_BODY), soaked)
    col = g.mix(col, g.vec(*DRY_BODY), dryness)
    blotch = _noise(g, P, 4.0, 4.0, 0.6)
    col = col * (0.78 + lumps * 0.24 + blotch * 0.2) * base

    # dry crust cracks
    crack_v = g.node("ShaderNodeTexVoronoi", {"Vector": P, "Scale": 42.0,
                                              "Randomness": 1.0},
                     feature="DISTANCE_TO_EDGE", voronoi_dimensions="3D")
    crack = (1.0 - g.out(crack_v, "Distance") / 0.035).clamp(0.0, 1.0) * dryness
    col = col * (1.0 - crack * 0.6)

    # shader grit: a few % of ~3 mm cells are half-sunk stones
    vor = g.node("ShaderNodeTexVoronoi", {"Vector": P, "Scale": 300.0,
                                          "Randomness": 1.0},
                 feature="F1", voronoi_dimensions="3D")
    vd = g.out(vor, "Distance") / 0.3
    rim = _noise(g, P, 900.0, 2.0)
    grit = g.math("MULTIPLY", g.out(vor, "Color").x.gt(0.955),
                  ((1.0 - vd * vd) * 2.0 - 0.6 + rim * 0.6).clamp(0.0, 1.0))
    grit = grit * (1.0 - comp)
    is_grit = grit.gt(0.05)
    col = g.mix(col, g.vec(0.19, 0.16, 0.125) * (0.6 + soaked * -0.25 + 0.4), is_grit)

    stone = g.node("ShaderNodeValToRGB", {0: peb})
    stone.color_ramp.interpolation = "CONSTANT"
    set_ramp(stone.color_ramp, STONES)
    # stones lying in mud are wet and smeared: darker than on dry sand
    stone_col = g.out(stone, "Color") * (0.45 + fine * 0.35)
    stone_col = g.mix(stone_col, col, 0.35)
    col = g.mix(col, stone_col, is_peb)

    # ---- film: patchy clear coat ---------------------------------------------------
    patch = _noise(g, Ps, 55.0, 3.0, 0.6)
    film = sfn.smoothstep((local - 0.35 - (patch - 0.5) * 0.5) / 0.3)
    film = (film * (1.0 - dryness)).max(shore * shore)
    coat_rough = (0.035 + (1.0 - soaked) * 0.16 + fine * 0.05).clamp(0.02, 0.5)

    roughness = g.mix(rough * 0.95, rough * 0.6, soaked)
    roughness = g.mix(roughness, 0.95, dryness)
    roughness = g.mix(roughness, 0.5, is_grit).clamp(0.05, 1.0)

    # ---- normal -----------------------------------------------------------------------
    bump = g.node("ShaderNodeBump",
                  {"Strength": 0.4 * (1.0 - comp * 0.5),
                   "Distance": 0.005 * detail, "Height": height})
    bump_c = g.node("ShaderNodeBump",
                    {"Strength": 0.8, "Distance": 0.0012, "Height": crack * -1.0,
                     "Normal": g.out(bump, "Normal")})
    bump_g = g.node("ShaderNodeBump",
                    {"Strength": 0.45, "Distance": 0.0005,
                     "Height": grit + fine * 0.35 * detail,
                     "Normal": g.out(bump_c, "Normal")})
    # the film is water: it levels the fine relief and keeps only the swell
    coat_bump = g.node("ShaderNodeBump",
                       {"Strength": 0.35, "Distance": 0.004, "Height": lumps})

    bsdf = g.node("ShaderNodeBsdfPrincipled",
                  {"Base Color": col, "Roughness": roughness, "IOR": 1.5,
                   "Specular IOR Level": 0.4,
                   "Normal": g.out(bump_g, "Normal"),
                   "Coat Weight": film, "Coat Roughness": coat_rough,
                   "Coat IOR": 1.33,
                   "Coat Normal": g.out(coat_bump, "Normal")})
    disp = g.node("ShaderNodeDisplacement",
                  {"Height": height - 0.5 + grit * 0.12, "Midlevel": 0.0,
                   "Scale": 0.004 * (1.0 - comp * 0.6)})
    out = g.node("ShaderNodeOutputMaterial",
                 {"Surface": g.out(bsdf, 0), "Displacement": g.out(disp, 0)})
    out.target = "ALL"
    b.layout()


def build_water(tree) -> None:
    """Shallow murky puddle water."""
    b = NodeTreeBuilder(tree)
    g = Expr(b)
    P = g.out(b.add("ShaderNodeTexCoord"), "Object")
    P2 = g.vec(P.x, P.y, 0.0)
    # a trace of wind: long, very low swell plus fine shiver
    swell = _noise(g, g.vec(P.x * 7.0, P.y * 18.0, 0.0), 1.0, 2.0)
    shiver = _noise(g, P2, 160.0, 2.0)
    bump = g.node("ShaderNodeBump",
                  {"Strength": 0.25, "Distance": 0.0015,
                   "Height": swell * 0.8 + shiver * 0.2})
    # suspended silt: the water is not clear, it scatters brown
    cloud = _noise(g, P2, 6.0, 3.0)
    murk = g.vec(0.115, 0.082, 0.050) * (0.8 + cloud * 0.4)
    bsdf = g.node("ShaderNodeBsdfPrincipled",
                  {"Base Color": murk, "Roughness": 0.015, "IOR": 1.333,
                   "Transmission Weight": 0.55,
                   "Normal": g.out(bump, "Normal")})
    # shadow rays pass: the mud under shallow water is lit, not blacked out
    lp = b.add("ShaderNodeLightPath")
    transp = b.add("ShaderNodeBsdfTransparent")
    transp.inputs["Color"].default_value = (0.75, 0.68, 0.58, 1.0)
    mix = g.node("ShaderNodeMixShader",
                 {0: g.out(lp, "Is Shadow Ray"), 1: g.out(bsdf, 0),
                  2: g.out(transp, 0)})
    g.node("ShaderNodeOutputMaterial", {"Surface": g.out(mix, 0)})
    b.layout()
