# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural, physics-aware materials for the three elements (E8).

One Principled-BSDF graph per element, built from shared blocks so Sand, Snow
and Mud differ in a small table of numbers plus a per-element *structure* block
(E8-T1). Fully procedural (Object coordinates, no UVs) so it works on the bare
simulation grid and renders in EEVEE and Cycles alike (E8-T9).

Structure is what makes it read as a real surface rather than tinted plastic:
each element stacks several octaves of relief into a chain of Bump nodes (a
macro roll, a mid grain/clump/lump, and a fine micro), and darkens the valleys
between them (a cheap ambient-occlusion from the same height), so the eye sees
depth. On top of that:

* Sand — Voronoi grains with per-grain colour jitter and a faint quartz sparkle.
* Snow — Voronoi clumps and crystal facets, a strong ice sparkle (roughness
  dips to near-mirror on scattered cells), subsurface, and a Fresnel edge sheen.
* Mud — lumps, wet Fresnel gloss, and dry cracks (Voronoi edges) that appear as
  the wetness drops.

It reacts to the physics (E8-S2): ``gfx_comp`` darkens and smooths tracks
(E8-T6); ``gfx_flow`` drives transverse ripples in a track (E8-T2). Wetness is a
single slider the caller also feeds into cohesion, so one control moves look and
behaviour together (E8-T7).

Four named control nodes (base colour, roughness, detail, wetness) are the only
things the Look sliders touch, so a slider edit is a one-line default_value set
and never rebuilds the graph. ``build_material`` stamps the material as
GroundFX-authored; the element switch only rebuilds a stamped material, so a
material the user assigned by hand is safe (E8-T10).

Verified against Blender 5.2.
"""
from __future__ import annotations

import bpy

from ..ng_builder import NodeTreeBuilder
from ..constants import (
    ELEM_SAND, ELEM_SNOW, ELEM_MUD,
    MAT_SAND, MAT_SNOW, MAT_MUD, PROP_MAT_GENERATED,
    MAT_CTRL_BASECOLOR, MAT_CTRL_ROUGHNESS, MAT_CTRL_DETAIL, MAT_CTRL_WETNESS,
    ATTR_COMP, ATTR_FLOW,
)

# Spatial frequency of the transverse track ripples, radians per object unit
# (the domain spans ~2 units). ~40 gives a few-centimetre wavelength.
_RIPPLE_SCALE = 42.0

_MAT_NAME = {ELEM_SAND: MAT_SAND, ELEM_SNOW: MAT_SNOW, ELEM_MUD: MAT_MUD}

# gfx_comp is metres of compacted material summed over the frames a spot was
# pressed. This gain maps a footprint's accumulation onto a full-strength track;
# the result is clamped to 0..1 before it tints anything.
_COMP_GAIN = 10.0


class LookDefaults:
    """Per-element authored look — the starting point for the Look sliders."""

    __slots__ = ("base_color", "wet_color", "roughness", "detail",
                 "base_wetness", "grain_scale", "subsurface", "ripple",
                 "sparkle", "macro_scale", "crevice")

    def __init__(self, base_color, wet_color, roughness, detail,
                 base_wetness, grain_scale, subsurface, ripple=0.0,
                 sparkle=0.0, macro_scale=8.0, crevice=0.5):
        self.base_color = base_color      # dry albedo (RGB)
        self.wet_color = wet_color        # albedo at full wetness (RGB)
        self.roughness = roughness        # dry roughness 0..1
        self.detail = detail              # relief bump strength
        self.base_wetness = base_wetness  # resting moisture 0..1
        self.grain_scale = grain_scale    # fine grain / crystal frequency
        self.subsurface = subsurface      # Principled subsurface weight
        self.ripple = ripple              # transverse track-ripple strength
        self.sparkle = sparkle            # ice-crystal glint strength
        self.macro_scale = macro_scale    # low-frequency relief frequency
        self.crevice = crevice            # how much valleys darken (fake AO)


LOOKS = {
    ELEM_SAND: LookDefaults(
        base_color=(0.62, 0.48, 0.30), wet_color=(0.33, 0.22, 0.11),
        roughness=0.92, detail=0.9, base_wetness=0.0,
        grain_scale=320.0, subsurface=0.0, ripple=0.6,
        sparkle=0.35, macro_scale=6.0, crevice=0.55),
    ELEM_SNOW: LookDefaults(
        base_color=(0.90, 0.93, 0.98), wet_color=(0.72, 0.78, 0.90),
        roughness=0.5, detail=0.7, base_wetness=0.1,
        grain_scale=120.0, subsurface=0.15, ripple=0.25,
        sparkle=1.0, macro_scale=9.0, crevice=0.6),
    ELEM_MUD: LookDefaults(
        base_color=(0.21, 0.15, 0.10), wet_color=(0.07, 0.05, 0.03),
        roughness=0.6, detail=0.6, base_wetness=0.6,
        grain_scale=90.0, subsurface=0.0, ripple=0.15,
        sparkle=0.0, macro_scale=14.0, crevice=0.7),
}


def look_defaults(element: str) -> LookDefaults:
    return LOOKS[element]


def _rgba(rgb, a=1.0):
    return (rgb[0], rgb[1], rgb[2], a)


# --------------------------------------------------------------------------
# small node helpers (keep build_material readable)
# --------------------------------------------------------------------------

def _noise(b, P, scale, detail=2.0, roughness=0.5):
    n = b.add("ShaderNodeTexNoise",
              inputs={"Scale": scale, "Detail": detail, "Roughness": roughness})
    b.link(P[0], P[1], n, "Vector")
    return n


def _voronoi(b, P, scale, feature="F1", randomness=1.0, smoothness=1.0):
    v = b.add("ShaderNodeTexVoronoi", feature=feature,
              inputs={"Scale": scale, "Randomness": randomness})
    if feature == "SMOOTH_F1":
        v.inputs["Smoothness"].default_value = smoothness
    b.link(P[0], P[1], v, "Vector")
    return v


def _math(b, op, a, b2=None, label=""):
    """a op b2, where a and b2 are (node,key) or floats."""
    n = b.add("ShaderNodeMath", operation=op, label=label)
    _feed(b, n, 0, a)
    if b2 is not None:
        _feed(b, n, 1, b2)
    return (n, "Value")


def _feed(b, node, idx, src):
    if isinstance(src, tuple):
        b.link(src[0], src[1], node, idx)
    else:
        b.set_default(node, idx, float(src))


def _scale_color(b, col, factor, label=""):
    """color * scalar via Vector Math SCALE."""
    n = b.add("ShaderNodeVectorMath", operation="SCALE", label=label)
    b.link(col[0], col[1], n, 0)
    _feed_vec_scale(b, n, factor)
    return (n, "Vector")


def _feed_vec_scale(b, node, factor):
    if isinstance(factor, tuple):
        b.link(factor[0], factor[1], node, "Scale")
    else:
        node.inputs["Scale"].default_value = float(factor)


def _mix_rgba(b, fac, a_color, b_color, label=""):
    mix = b.add("ShaderNodeMix", data_type="RGBA", label=label)
    _feed(b, mix, 0, fac)                       # Factor (Float)
    _feed_color(b, mix, 6, a_color)             # A (Color)
    _feed_color(b, mix, 7, b_color)             # B (Color)
    return (mix, 2)                             # Result (Color) is output 2


def _feed_color(b, node, idx, src):
    # A (node, key) socket pair -> link; a literal RGBA tuple -> default value.
    if isinstance(src, tuple) and hasattr(src[0], "outputs"):
        b.link(src[0], src[1], node, idx)
    else:
        b.set_default(node, idx, src)


def _bump(b, height, strength, distance, prev_normal, label=""):
    n = b.add("ShaderNodeBump", inputs={"Distance": distance}, label=label)
    _feed(b, n, "Strength", strength)
    b.link(height[0], height[1], n, "Height")
    if prev_normal is not None:
        b.link(prev_normal[0], prev_normal[1], n, "Normal")
    return (n, "Normal")


# --------------------------------------------------------------------------
# per-element structure: returns relief layers + a valley (crevice) mask +
# an optional roughness multiplier + an optional per-cell colour tint + an
# optional extra-darkening mask (mud cracks).
# --------------------------------------------------------------------------

def _structure(b, element, look, P, det_eff, n_wet):
    macro = _noise(b, P, look.macro_scale, detail=3.0, roughness=0.6)
    micro = _noise(b, P, look.grain_scale * 2.2, detail=6.0, roughness=0.7)
    layers = []            # (height, strength, distance)
    crevice = None         # 0..1, 1 = ridge (bright), 0 = valley (dark)
    rough_mult = None      # multiplies roughness where present
    tint = None            # per-cell colour multiplier (as a fraction)
    extra_dark = None      # 0..1, 1 = fully dark (cracks)

    if element == ELEM_SAND:
        grain = _voronoi(b, P, look.grain_scale, "F1", randomness=1.0)
        grain_h = (grain, "Distance")
        layers = [
            (macro, "Factor", 0.35, 0.03),
            (grain_h[0], grain_h[1], _math(b, "MULTIPLY", det_eff, 0.9), 0.004),
            (micro, "Factor", _math(b, "MULTIPLY", det_eff, 0.4), 0.0015),
        ]
        crevice = grain_h
        # per-grain *brightness* jitter (grayscale, not coloured, or the grains
        # turn into rainbow confetti). Luminance of the Voronoi cell colour ->
        # a scalar in ~0.85..1.12 that lightens/darkens each grain.
        lum = b.add("ShaderNodeVectorMath", operation="DOT_PRODUCT",
                    label="grain luma")
        b.link(grain, "Color", lum, 0)
        lum.inputs[1].default_value = (0.33, 0.33, 0.33)
        tint = _math(b, "MULTIPLY_ADD", (lum, "Value"), 0.3, label="grain bright")
        b.set_default(tint[0], 2, 0.85)
        # faint quartz sparkle
        spk = _voronoi(b, P, look.grain_scale * 2.5, "F1")
        rough_mult = _sparkle_mult(b, spk, 0.06, 0.3 * look.sparkle)

    elif element == ELEM_SNOW:
        clump = _voronoi(b, P, look.macro_scale * 2.4, "SMOOTH_F1",
                         randomness=1.0, smoothness=1.0)
        crystal = _voronoi(b, P, look.grain_scale, "F1", randomness=0.9)
        layers = [
            (clump, "Distance", 0.6, 0.03),
            (crystal, "Distance", _math(b, "MULTIPLY", det_eff, 0.6), 0.005),
            (micro, "Factor", _math(b, "MULTIPLY", det_eff, 0.35), 0.0015),
        ]
        crevice = (clump, "Distance")
        spk = _voronoi(b, P, look.grain_scale * 3.0, "F1", randomness=1.0)
        rough_mult = _sparkle_mult(b, spk, 0.05, 0.9 * look.sparkle)

    else:  # MUD
        lump = _noise(b, P, look.macro_scale, detail=4.0, roughness=0.6)
        # cracks: Voronoi distance-to-edge is ~0 on cell borders
        edge = _voronoi(b, P, look.grain_scale * 0.5, "DISTANCE_TO_EDGE",
                        randomness=1.0)
        crack = _math(b, "LESS_THAN", (edge, "Distance"), 0.04, label="crack")
        dry = _math(b, "SUBTRACT", 1.0, (n_wet, "Value"), label="dryness")
        crack_dry = _math(b, "MULTIPLY", crack, dry, label="dry crack")
        layers = [
            (lump, "Factor", 0.4, 0.03),
            (crack_dry[0], crack_dry[1], _math(b, "MULTIPLY", det_eff, 0.6),
             0.004),
            (micro, "Factor", _math(b, "MULTIPLY", det_eff, 0.3), 0.0015),
        ]
        crevice = (lump, "Factor")
        extra_dark = crack_dry

    return layers, macro, crevice, rough_mult, tint, extra_dark


def _sparkle_mult(b, voro, thresh, strength):
    """Roughness multiplier: dips toward 0 on the sparkle cells."""
    spots = _math(b, "LESS_THAN", (voro, "Distance"), thresh, label="sparkle")
    dip = _math(b, "MULTIPLY", spots, strength, label="dip")
    return _math(b, "SUBTRACT", 1.0, dip, label="1 - dip")


def build_material(element: str, look: LookDefaults | None = None,
                   *, base_color=None, roughness=None, detail=None,
                   wetness=None) -> bpy.types.Material:
    """Create (replacing any same-named block) a material for ``element``."""
    look = look or look_defaults(element)
    name = _MAT_NAME[element]
    existing = bpy.data.materials.get(name)
    if existing is not None and existing.get(PROP_MAT_GENERATED):
        if existing.users == 0:
            bpy.data.materials.remove(existing)
        else:
            existing.name = f"{name}.old"
    mat = bpy.data.materials.new(name)
    mat[PROP_MAT_GENERATED] = True
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    b = NodeTreeBuilder(tree)

    bc = _rgba(base_color if base_color is not None else look.base_color)
    rough0 = roughness if roughness is not None else look.roughness
    det0 = detail if detail is not None else look.detail
    wet0 = wetness if wetness is not None else look.base_wetness

    # -- control nodes (the only things the Look sliders write) --------------
    n_base = b.add("ShaderNodeRGB", name=MAT_CTRL_BASECOLOR, label="Base Color")
    n_base.outputs[0].default_value = bc
    n_rough = b.add("ShaderNodeValue", name=MAT_CTRL_ROUGHNESS, label="Roughness")
    n_rough.outputs[0].default_value = rough0
    n_detail = b.add("ShaderNodeValue", name=MAT_CTRL_DETAIL, label="Detail")
    n_detail.outputs[0].default_value = det0
    n_wet = b.add("ShaderNodeValue", name=MAT_CTRL_WETNESS, label="Wetness")
    n_wet.outputs[0].default_value = wet0

    tex = b.add("ShaderNodeTexCoord")
    P = (tex, "Object")

    # detail weakens as the surface wets (wet packs the grain down)
    det_wet = _math(b, "MULTIPLY_ADD", (n_wet, "Value"), -0.5, label="1-0.5wet")
    b.set_default(det_wet[0], 2, 1.0)
    det_eff = _math(b, "MULTIPLY", (n_detail, "Value"), det_wet, label="detail")

    layers, macro, crevice, rough_mult, tint, extra_dark = _structure(
        b, element, look, P, det_eff, n_wet)

    # -- base colour: two-tone macro shading + variation --------------------
    tone_dark = _scale_color(b, (n_base, "Color"), 0.7, "tone dark")
    tone_light = _scale_color(b, (n_base, "Color"), 1.18, "tone light")
    var = _noise(b, P, look.macro_scale * 2.5, detail=2.0)
    col1 = _mix_rgba(b, (macro, "Factor"), tone_dark, (n_base, "Color"),
                     "macro shade")
    col2 = _mix_rgba(b, _math(b, "MULTIPLY", (var, "Factor"), 0.4),
                     col1, tone_light, "variation")

    # per-grain brightness jitter (scalar), sand only
    if tint is not None:
        col2 = _scale_color(b, col2, tint, "grain brightness")

    # crevice darken (fake AO): valleys lose brightness
    crv_f = _math(b, "MULTIPLY_ADD", crevice,
                  float(look.crevice), label="crevice factor")
    b.set_default(crv_f[0], 2, 1.0 - look.crevice)
    col_crv = _scale_color(b, col2, crv_f, "crevice darken")

    # extra dark (mud cracks)
    if extra_dark is not None:
        dark_f = _math(b, "MULTIPLY_ADD", extra_dark, -0.75, label="crack dark")
        b.set_default(dark_f[0], 2, 1.0)
        col_crv = _scale_color(b, col_crv, dark_f, "crack darken")

    # -- track: compaction darkens & smooths (physics link) -----------------
    comp = b.add("ShaderNodeAttribute", attribute_type="GEOMETRY",
                 attribute_name=ATTR_COMP, label="gfx_comp")
    track = _math(b, "MULTIPLY", (comp, "Factor"), _COMP_GAIN, label="track")
    track_c = b.add("ShaderNodeClamp", inputs={"Min": 0.0, "Max": 1.0})
    b.link(track[0], track[1], track_c, "Value")
    col_trk = _mix_rgba(b, (track_c, "Result"), col_crv,
                        _scale_color(b, col_crv, 0.6, "track tone"),
                        "track darken")

    # -- wetness darken toward the wet colour -------------------------------
    wet_fac = _math(b, "MULTIPLY", (n_wet, "Value"), 0.85, label="wet mix")
    col_wet = _mix_rgba(b, wet_fac, col_trk, _rgba(look.wet_color),
                        "wetness darken")

    # -- roughness: base, lowered by wetness and track, sparkle dips --------
    one_m_wet = _math(b, "SUBTRACT", 1.0,
                      _math(b, "MULTIPLY", (n_wet, "Value"), 0.6))
    one_m_trk = _math(b, "SUBTRACT", 1.0,
                      _math(b, "MULTIPLY", (track_c, "Result"), 0.35))
    rough = _math(b, "MULTIPLY",
                  _math(b, "MULTIPLY", (n_rough, "Value"), one_m_wet),
                  one_m_trk, label="roughness")
    if rough_mult is not None:
        rough = _math(b, "MULTIPLY", rough, rough_mult, label="+ sparkle")

    # -- specular sheen rises with wetness ----------------------------------
    spec = _math(b, "MULTIPLY_ADD", (n_wet, "Value"), 0.5, label="specular")
    b.set_default(spec[0], 2, 0.5)

    # -- relief: chain the structure layers into a bump normal --------------
    normal = None
    for i, (h_node, h_key, strength, dist) in enumerate(layers):
        normal = _bump(b, (h_node, h_key), strength, dist, normal,
                       label=f"bump {i}")

    # -- track ripples along gfx_flow (E8-T2), folded onto the finest bump --
    if look.ripple > 0.0:
        normal = _ripple_normal(b, tex, P, track_c, det_eff, look, normal)

    # -- assemble Principled ------------------------------------------------
    bsdf = b.add("ShaderNodeBsdfPrincipled")
    b.link(col_wet[0], col_wet[1], bsdf, "Base Color")
    b.link(rough[0], rough[1], bsdf, "Roughness")
    if normal is not None:
        b.link(normal[0], normal[1], bsdf, "Normal")
    _try_link(b, spec, bsdf, "Specular IOR Level")
    if look.subsurface > 0.0:
        # Snow: a little subsurface for the soft, waxy light + a Fresnel sheen
        # that brightens grazing edges (rim of clumps catching the sun).
        _try_set(bsdf, "Subsurface Weight", look.subsurface)
        fres = b.add("ShaderNodeFresnel", inputs={"IOR": 1.3})
        sheen = _math(b, "MULTIPLY", (fres, "Factor"), 0.15, label="edge sheen")
        _try_link(b, sheen, bsdf, "Sheen Weight")

    out = b.add("ShaderNodeOutputMaterial")
    b.link(bsdf, "BSDF", out, "Surface")

    b.layout()
    return mat


def _ripple_normal(b, tex, P, track_c, det_eff, look, prev_normal):
    """A sine of position projected on gfx_flow -> transverse track ridges."""
    flow = b.add("ShaderNodeAttribute", attribute_type="GEOMETRY",
                 attribute_name=ATTR_FLOW, label="gfx_flow")
    pdot = b.add("ShaderNodeVectorMath", operation="DOT_PRODUCT", label="P.flow")
    b.link(tex, "Object", pdot, 0)
    b.link(flow, "Vector", pdot, 1)
    phase = _math(b, "MULTIPLY", (pdot, "Value"), _RIPPLE_SCALE, label="phase")
    wave = _math(b, "SINE", phase, label="ripple")
    flow_len = b.add("ShaderNodeVectorMath", operation="LENGTH")
    b.link(flow, "Vector", flow_len, 0)
    gate = _math(b, "MULTIPLY", (track_c, "Result"), (flow_len, "Value"),
                 label="ripple gate")
    amt = _math(b, "MULTIPLY", gate, look.ripple, label="ripple amt")
    ripple_h = _math(b, "MULTIPLY", wave, amt, label="ripple h")
    return _bump(b, ripple_h, 0.5, 0.01, prev_normal, label="ripple bump")


def _try_link(b, from_pair, to_node, to_key):
    try:
        b.link(from_pair[0], from_pair[1], to_node, to_key)
    except KeyError:
        pass


def _try_set(node, key, value):
    try:
        node.inputs[key].default_value = value
    except (KeyError, TypeError):
        pass


def _ctrl(mat, name):
    return mat.node_tree.nodes.get(name) if mat and mat.use_nodes else None


def update_controls(mat, *, base_color=None, roughness=None, detail=None,
                    wetness=None) -> None:
    """Push Look-slider values into a built material's control nodes."""
    if mat is None or not mat.get(PROP_MAT_GENERATED):
        return
    if base_color is not None:
        n = _ctrl(mat, MAT_CTRL_BASECOLOR)
        if n:
            n.outputs[0].default_value = _rgba(base_color)
    for value, cname in ((roughness, MAT_CTRL_ROUGHNESS),
                         (detail, MAT_CTRL_DETAIL),
                         (wetness, MAT_CTRL_WETNESS)):
        if value is not None:
            n = _ctrl(mat, cname)
            if n:
                n.outputs[0].default_value = value


def is_generated(mat) -> bool:
    return bool(mat is not None and mat.get(PROP_MAT_GENERATED))


def domain_material(obj):
    """Return the object's GroundFX-authored material, or None."""
    if obj is None:
        return None
    for slot in obj.material_slots:
        if is_generated(slot.material):
            return slot.material
    return None


def assign_material(obj, mat) -> None:
    """Put ``mat`` in the object's GroundFX slot, replacing an old one (E8-T10)."""
    if obj is None or obj.data is None:
        return
    for i, slot in enumerate(obj.material_slots):
        if is_generated(slot.material):
            old = slot.material
            obj.data.materials[i] = mat
            if (old is not None and old is not mat and old.users == 0
                    and old.get(PROP_MAT_GENERATED)):
                bpy.data.materials.remove(old)
            return
    obj.data.materials.append(mat)
