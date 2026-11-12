# SPDX-License-Identifier: GPL-3.0-or-later
"""Material lifecycle for the three elements.

The shaders themselves live in ``mat_sand`` / ``mat_snow`` / ``mat_mud``;
each is fully procedural in object coordinates (no UVs, no tiling, no
resolution limit) and reads the solver's fields. This module owns what is
common:

* the named **control nodes** the Look sliders write into, so a slider edit
  is one ``default_value`` assignment and never rebuilds the graph;
* the **generated stamp**: only a stamped material is rebuilt or replaced on
  an element switch, a material the user assigned by hand is never touched;
* slot handling on the domain object.
"""
from __future__ import annotations

import math

import bpy

from ..ng_builder import NodeTreeBuilder
from ..constants import (
    ELEM_SAND, ELEM_SNOW, ELEM_MUD,
    MAT_SAND, MAT_SNOW, MAT_MUD, MAT_WATER, PROP_MAT_GENERATED,
    MAT_CTRL_BASECOLOR, MAT_CTRL_ROUGHNESS, MAT_CTRL_DETAIL, MAT_CTRL_WETNESS,
    MAT_CTRL_RIPPLE_LEN, MAT_CTRL_RIPPLE_AMT, MAT_CTRL_WIND,
)

_MAT_NAME = {ELEM_SAND: MAT_SAND, ELEM_SNOW: MAT_SNOW, ELEM_MUD: MAT_MUD}

# Surface relief defaults shared by the surface stage and the shader.
RIPPLE_HEIGHT = 0.005
RIPPLE_LENGTH = 0.07
WIND_ANGLE = math.radians(20.0)


class LookDefaults:
    """Per-element authored look: the starting point for the Look sliders."""

    __slots__ = ("base_color", "roughness", "detail", "base_wetness")

    def __init__(self, base_color, roughness, detail, base_wetness):
        self.base_color = base_color      # tint over the element's own albedo
        self.roughness = roughness        # dry roughness 0..1
        self.detail = detail              # relief strength
        self.base_wetness = base_wetness  # resting moisture 0..1


LOOKS = {
    ELEM_SAND: LookDefaults((1.0, 1.0, 1.0), 0.9, 1.0, 0.0),
    ELEM_SNOW: LookDefaults((1.0, 1.0, 1.0), 0.55, 0.7, 0.1),
    ELEM_MUD: LookDefaults((1.0, 1.0, 1.0), 0.6, 0.6, 0.8),
}


def look_defaults(element: str) -> LookDefaults:
    return LOOKS[element]


def _rgba(rgb, a=1.0):
    return (rgb[0], rgb[1], rgb[2], a)


def _value(b, name, label, value):
    node = b.add("ShaderNodeValue", name=name, label=label)
    node.outputs[0].default_value = value
    return node


def build_material(element: str, look: LookDefaults | None = None,
                   *, base_color=None, roughness=None, detail=None,
                   wetness=None) -> bpy.types.Material:
    """Create (replacing any same-named block) a material for ``element``."""
    from . import mat_sand, mat_snow, mat_mud

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

    n_base = b.add("ShaderNodeRGB", name=MAT_CTRL_BASECOLOR, label="Base Color")
    n_base.outputs[0].default_value = _rgba(
        base_color if base_color is not None else look.base_color)
    ctrl = {
        "base": n_base,
        "rough": _value(b, MAT_CTRL_ROUGHNESS, "Roughness",
                        roughness if roughness is not None else look.roughness),
        "detail": _value(b, MAT_CTRL_DETAIL, "Detail",
                         detail if detail is not None else look.detail),
        "wet": _value(b, MAT_CTRL_WETNESS, "Wetness",
                      wetness if wetness is not None else look.base_wetness),
    }
    if element == ELEM_SAND:
        ctrl["ripple_len"] = _value(b, MAT_CTRL_RIPPLE_LEN, "Ripple Length",
                                    RIPPLE_LENGTH)
        ctrl["ripple_amt"] = _value(b, MAT_CTRL_RIPPLE_AMT, "Ripple Height",
                                    RIPPLE_HEIGHT)
        ctrl["wind"] = _value(b, MAT_CTRL_WIND, "Wind Direction", WIND_ANGLE)
        mat_sand.build(tree, ctrl)
    elif element == ELEM_SNOW:
        mat_snow.build(tree, ctrl)
    else:
        mat_mud.build(tree, ctrl)
    try:
        mat.displacement_method = "BOTH"
    except (AttributeError, TypeError):
        pass
    return mat


def water_material() -> bpy.types.Material:
    """Murky standing water for the mud surface stage (built once)."""
    mat = bpy.data.materials.get(MAT_WATER)
    if mat is not None:
        return mat
    from . import mat_mud
    mat = bpy.data.materials.new(MAT_WATER)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    mat_mud.build_water(mat.node_tree)
    return mat


def _ctrl(mat, name):
    return mat.node_tree.nodes.get(name) if mat and mat.use_nodes else None


def update_controls(mat, *, base_color=None, roughness=None, detail=None,
                    wetness=None, ripple_length=None, ripple_height=None,
                    wind=None) -> None:
    """Push slider values into a built material's control nodes."""
    if mat is None or not mat.get(PROP_MAT_GENERATED):
        return
    if base_color is not None:
        n = _ctrl(mat, MAT_CTRL_BASECOLOR)
        if n:
            n.outputs[0].default_value = _rgba(base_color)
    for value, cname in ((roughness, MAT_CTRL_ROUGHNESS),
                         (detail, MAT_CTRL_DETAIL),
                         (wetness, MAT_CTRL_WETNESS),
                         (ripple_length, MAT_CTRL_RIPPLE_LEN),
                         (ripple_height, MAT_CTRL_RIPPLE_AMT),
                         (wind, MAT_CTRL_WIND)):
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
    """Put ``mat`` in the object's GroundFX slot, replacing an old one."""
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
