# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural, physics-aware materials for the three elements (E8).

One Principled-BSDF graph per element, built from shared blocks so Sand, Snow
and Mud differ only in a small table of numbers (E8-T1). The graph is fully
procedural (Object coordinates, no UVs) so it works on the bare simulation grid
and renders the same in EEVEE and Cycles (E8-T9).

It reacts to the physics (E8-S2): the solver's ``gfx_comp`` attribute — how much
material has been compacted underfoot — darkens and smooths the track relative
to undisturbed material (E8-T6), which is the one attribute the solver actually
produces today. Wetness is a single slider that the caller also feeds into the
solver's cohesion, so one control moves both look and behaviour (E8-T7).

Four named control nodes (base colour, roughness, detail, wetness) are the only
things the Look sliders touch, so a slider edit is a one-line default_value set
and never rebuilds the graph. ``build_material`` stamps the material as
GroundFX-authored; the element switch only ever rebuilds a stamped material, so
a material the user assigned by hand is safe (E8-T10).

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

# Spatial frequency of the transverse track ripples, in radians per object-space
# unit (the domain spans ~2 units). ~40 gives a few-centimetre wavelength.
_RIPPLE_SCALE = 42.0

_MAT_NAME = {ELEM_SAND: MAT_SAND, ELEM_SNOW: MAT_SNOW, ELEM_MUD: MAT_MUD}

# gfx_comp is metres of compacted material summed over the frames a spot was
# pressed. This gain maps a typical footprint's accumulation onto a full-
# strength track; the result is clamped to 0..1 before it tints anything.
_COMP_GAIN = 10.0


class LookDefaults:
    """Per-element authored look — the starting point for the Look sliders."""

    __slots__ = ("base_color", "wet_color", "roughness", "detail",
                 "base_wetness", "grain_scale", "subsurface", "ripple")

    def __init__(self, base_color, wet_color, roughness, detail,
                 base_wetness, grain_scale, subsurface, ripple=0.0):
        self.base_color = base_color      # dry albedo (RGB)
        self.wet_color = wet_color        # albedo at full wetness (RGB)
        self.roughness = roughness        # dry roughness 0..1
        self.detail = detail              # grain bump strength 0..1
        self.base_wetness = base_wetness  # resting moisture 0..1
        self.grain_scale = grain_scale    # procedural grain frequency
        self.subsurface = subsurface      # Principled subsurface weight
        self.ripple = ripple              # transverse track-ripple strength


LOOKS = {
    ELEM_SAND: LookDefaults(
        base_color=(0.60, 0.47, 0.29), wet_color=(0.30, 0.20, 0.10),
        roughness=0.85, detail=0.5, base_wetness=0.0,
        grain_scale=55.0, subsurface=0.0, ripple=0.6),
    ELEM_SNOW: LookDefaults(
        base_color=(0.90, 0.93, 0.98), wet_color=(0.72, 0.78, 0.90),
        roughness=0.55, detail=0.35, base_wetness=0.1,
        grain_scale=38.0, subsurface=0.12, ripple=0.25),
    ELEM_MUD: LookDefaults(
        base_color=(0.20, 0.14, 0.09), wet_color=(0.07, 0.05, 0.03),
        roughness=0.55, detail=0.45, base_wetness=0.6,
        grain_scale=45.0, subsurface=0.0, ripple=0.15),
}


def look_defaults(element: str) -> LookDefaults:
    return LOOKS[element]


def _rgba(rgb, a=1.0):
    return (rgb[0], rgb[1], rgb[2], a)


def _mix_rgba(b, fac_node, fac_key, a_color, b_color, label=""):
    """Colour = mix(a, b, fac). Uses the Mix node by index (RGBA is index 6/7)."""
    mix = b.add("ShaderNodeMix", data_type="RGBA", label=label)
    b.link(fac_node, fac_key, mix, 0)          # Factor (Float)
    b.set_default(mix, 6, a_color)             # A (Color)
    b.set_default(mix, 7, b_color)             # B (Color)
    return mix, 2                              # Result (Color) is output index 2


def build_material(element: str, look: LookDefaults | None = None,
                   *, base_color=None, roughness=None, detail=None,
                   wetness=None) -> bpy.types.Material:
    """Create (replacing any same-named block) a material for ``element``.

    The optional overrides seed the four control nodes so a rebuild on element
    switch keeps the user's current slider values.
    """
    look = look or look_defaults(element)
    name = _MAT_NAME[element]
    # Free the clean name for the new block. An unused old one is removed; one
    # still worn by an object is only renamed here (removing it would null the
    # slot it sits in) and cleaned up by assign_material once swapped out.
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
    n_base = b.add("ShaderNodeRGB", name=MAT_CTRL_BASECOLOR,
                   label="Base Color")
    n_base.outputs[0].default_value = bc
    n_rough = b.add("ShaderNodeValue", name=MAT_CTRL_ROUGHNESS, label="Roughness")
    n_rough.outputs[0].default_value = rough0
    n_detail = b.add("ShaderNodeValue", name=MAT_CTRL_DETAIL, label="Detail")
    n_detail.outputs[0].default_value = det0
    n_wet = b.add("ShaderNodeValue", name=MAT_CTRL_WETNESS, label="Wetness")
    n_wet.outputs[0].default_value = wet0

    # -- procedural coordinates ---------------------------------------------
    tex = b.add("ShaderNodeTexCoord")
    mapping = b.add("ShaderNodeMapping")
    b.link(tex, "Object", mapping, "Vector")

    # -- colour variation: mix two tones by a low-frequency noise -----------
    var_noise = b.add("ShaderNodeTexNoise",
                      inputs={"Scale": look.grain_scale * 0.15, "Detail": 2.0})
    b.link(mapping, "Vector", var_noise, "Vector")
    var_ramp = b.add("ShaderNodeValToRGB")
    var_ramp.color_ramp.elements[0].position = 0.35
    var_ramp.color_ramp.elements[1].position = 0.65
    b.link(var_noise, "Factor", var_ramp, "Factor")
    # second tone = base colour darkened ~20 %
    tone_b = b.add("ShaderNodeVectorMath", operation="SCALE",
                   inputs={"Scale": 0.8})
    b.link(n_base, "Color", tone_b, 0)
    varied, varied_k = _mix_rgba(b, var_ramp, "Color", (0, 0, 0, 1), (0, 0, 0, 1),
                                 label="tone variation")
    # feed the two tones in as links (override the placeholder defaults)
    varied_node = varied
    b.link(n_base, "Color", varied_node, 6)
    b.link(tone_b, "Vector", varied_node, 7)

    # -- track: compaction darkens & smooths (the physics link) -------------
    comp = b.add("ShaderNodeAttribute", attribute_type="GEOMETRY",
                 attribute_name=ATTR_COMP, label="gfx_comp")
    track = b.add("ShaderNodeMath", operation="MULTIPLY",
                  inputs={1: _COMP_GAIN}, label="track = comp*gain")
    b.link(comp, "Factor", track, 0)
    track_c = b.add("ShaderNodeClamp", inputs={"Min": 0.0, "Max": 1.0})
    b.link(track, "Value", track_c, "Value")
    # darken varied colour toward 55 % where compacted
    track_col = b.add("ShaderNodeVectorMath", operation="SCALE",
                      inputs={"Scale": 0.55})
    b.link(varied_node, varied_k, track_col, 0)
    col_tracked, col_tracked_k = _mix_rgba(b, track_c, "Result",
                                           (0, 0, 0, 1), (0, 0, 0, 1),
                                           label="track darken")
    b.link(varied_node, varied_k, col_tracked, 6)
    b.link(track_col, "Vector", col_tracked, 7)

    # -- wetness: darken toward wet colour, applied on top of the track -----
    wet_fac = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.85},
                    label="wet mix amount")
    b.link(n_wet, "Value", wet_fac, 0)
    col_wet, col_wet_k = _mix_rgba(b, wet_fac, "Value",
                                   (0, 0, 0, 1), _rgba(look.wet_color),
                                   label="wetness darken")
    b.link(col_tracked, col_tracked_k, col_wet, 6)

    # -- roughness: base, lowered by wetness and by the track ---------------
    # r = rough0 * (1 - 0.6*wet) * (1 - 0.35*track)
    wet_k = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.6})
    b.link(n_wet, "Value", wet_k, 0)
    one_m_wet = b.add("ShaderNodeMath", operation="SUBTRACT", inputs={0: 1.0})
    b.link(wet_k, "Value", one_m_wet, 1)
    trk_k = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.35})
    b.link(track_c, "Result", trk_k, 0)
    one_m_trk = b.add("ShaderNodeMath", operation="SUBTRACT", inputs={0: 1.0})
    b.link(trk_k, "Value", one_m_trk, 1)
    r1 = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(n_rough, "Value", r1, 0)
    b.link(one_m_wet, "Value", r1, 1)
    rough_final = b.add("ShaderNodeMath", operation="MULTIPLY", label="roughness")
    b.link(r1, "Value", rough_final, 0)
    b.link(one_m_trk, "Value", rough_final, 1)

    # -- specular rises with wetness (wet sheen) ----------------------------
    spec = b.add("ShaderNodeMath", operation="MULTIPLY_ADD",
                 inputs={1: 0.5, 2: 0.5}, label="specular")
    b.link(n_wet, "Value", spec, 0)  # 0.5 + 0.5*wet

    # -- grain bump, weakened where wet ------------------------------------
    grain = b.add("ShaderNodeTexNoise",
                  inputs={"Scale": look.grain_scale, "Detail": 4.0})
    b.link(mapping, "Vector", grain, "Vector")
    det_wet = b.add("ShaderNodeMath", operation="MULTIPLY_ADD",
                    inputs={1: -0.5, 2: 1.0}, label="1 - 0.5*wet")
    b.link(n_wet, "Value", det_wet, 0)
    det_str = b.add("ShaderNodeMath", operation="MULTIPLY", label="bump strength")
    b.link(n_detail, "Value", det_str, 0)
    b.link(det_wet, "Value", det_str, 1)

    # -- track ripples: transverse corrugations along gfx_flow (E8-T2) ------
    # Sand dragged past leaves ridges *across* the motion. gfx_flow is the unit
    # motion direction the solver recorded per cell; a sine of the position
    # projected onto it gives bands perpendicular to travel. Gated by the track
    # mask (gfx_comp) and by |flow|, so ripples show only where material was
    # actually pushed, never on untouched ground.
    height = grain
    height_key = "Factor"
    if look.ripple > 0.0:
        flow = b.add("ShaderNodeAttribute", attribute_type="GEOMETRY",
                     attribute_name=ATTR_FLOW, label="gfx_flow")
        pdot = b.add("ShaderNodeVectorMath", operation="DOT_PRODUCT",
                     label="P . flow")
        b.link(tex, "Object", pdot, 0)
        b.link(flow, "Vector", pdot, 1)
        phase = b.add("ShaderNodeMath", operation="MULTIPLY",
                      inputs={1: _RIPPLE_SCALE}, label="phase")
        b.link(pdot, "Value", phase, 0)
        wave = b.add("ShaderNodeMath", operation="SINE", label="ripple wave")
        b.link(phase, "Value", wave, 0)
        # magnitude of flow (0 on untouched ground, ~1 on a track)
        flow_len = b.add("ShaderNodeVectorMath", operation="LENGTH")
        b.link(flow, "Vector", flow_len, 0)
        gate = b.add("ShaderNodeMath", operation="MULTIPLY", label="ripple gate")
        b.link(track_c, "Result", gate, 0)
        b.link(flow_len, "Value", gate, 1)
        ripple_amt = b.add("ShaderNodeMath", operation="MULTIPLY",
                           inputs={1: look.ripple}, label="ripple * strength")
        b.link(gate, "Value", ripple_amt, 0)
        ripple_h = b.add("ShaderNodeMath", operation="MULTIPLY", label="ripple h")
        b.link(wave, "Value", ripple_h, 0)
        b.link(ripple_amt, "Value", ripple_h, 1)
        combined = b.add("ShaderNodeMath", operation="ADD", label="grain+ripple")
        b.link(grain, "Factor", combined, 0)
        b.link(ripple_h, "Value", combined, 1)
        height, height_key = combined, "Value"

    bump = b.add("ShaderNodeBump", inputs={"Distance": 0.002})
    b.link(det_str, "Value", bump, "Strength")
    b.link(height, height_key, bump, "Height")

    # -- assemble Principled ------------------------------------------------
    bsdf = b.add("ShaderNodeBsdfPrincipled")
    b.link(col_wet, col_wet_k, bsdf, "Base Color")
    b.link(rough_final, "Value", bsdf, "Roughness")
    b.link(bump, "Normal", bsdf, "Normal")
    _try_link(b, spec, "Value", bsdf, "Specular IOR Level")
    if look.subsurface > 0.0:
        # Snow: a little subsurface for the soft, waxy light. EEVEE Next and
        # Cycles both honour the weight; the radius default is fine at this
        # scale, so we only set the weight (approximation in EEVEE, E8-T3).
        _try_set(bsdf, "Subsurface Weight", look.subsurface)
    out = b.add("ShaderNodeOutputMaterial")
    b.link(bsdf, "BSDF", out, "Surface")

    b.layout()
    return mat


def _try_link(b, from_node, from_key, to_node, to_key):
    """Link if the target socket exists (Principled socket names drift)."""
    try:
        b.link(from_node, from_key, to_node, to_key)
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
    """Put ``mat`` in the object's GroundFX slot, replacing an old one.

    If the object already carries a GroundFX-authored material, that slot is
    swapped; otherwise the material is appended, leaving any material the user
    assigned themselves in place and untouched (E8-T10).
    """
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
