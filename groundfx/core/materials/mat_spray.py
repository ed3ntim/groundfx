# SPDX-License-Identifier: GPL-3.0-or-later
"""Materials of airborne material: sand grains, snow crumbs, mud clots.

Each piece is one point, so there is no texture to speak of.

* **Sand.** One mineral colour per grain, from the palette of the bed (thrown
  sand is the sand that was on the ground). Quartz is translucent: against
  the light a sheet of sand glows at its thin edges while the dense core
  stays dark, and that contrast is most of what makes sand in the air look
  like sand.
* **Snow.** White and deeply translucent. A puff of powder is bright all the
  way through, never grey: light scatters from crumb to crumb.
* **Mud.** Dark, wet, glossy. A clot carries a highlight and no light
  through it.
"""
from __future__ import annotations

import bpy

from ..constants import (
    ELEM_SAND, ELEM_SNOW, ELEM_MUD, MAT_SAND_SPRAY, MAT_SNOW_SPRAY,
    MAT_MUD_SPRAY, PROP_MAT_GENERATED,
)
from . import mat_sand

ATTR_GRAIN_ID = "gfx_grain_id"
_NAMES = {ELEM_SAND: MAT_SAND_SPRAY, ELEM_SNOW: MAT_SNOW_SPRAY,
          ELEM_MUD: MAT_MUD_SPRAY}
# (dark, light) linear colours a piece is picked between, share of
# translucency, roughness range, clearcoat
_LOOK = {
    ELEM_SNOW: ((0.80, 0.84, 0.90), (0.95, 0.96, 0.97), 0.55, (0.35, 0.7), 0.0),
    ELEM_MUD: ((0.035, 0.022, 0.013), (0.085, 0.055, 0.032), 0.0,
               (0.12, 0.38), 0.7),
}


def spray_material(element: str = ELEM_SAND) -> bpy.types.Material:
    name = _NAMES.get(element, MAT_SAND_SPRAY)
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat[PROP_MAT_GENERATED] = True
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = ATTR_GRAIN_ID
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    rough = nt.nodes.new("ShaderNodeMapRange")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    trans = nt.nodes.new("ShaderNodeBsdfTranslucent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if element in _LOOK:
        dark, light, share, (r0, r1), coat = _LOOK[element]
        mat_sand.set_ramp(ramp.color_ramp, ((0.0, dark), (1.0, light)))
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.08
        bsdf.inputs["IOR"].default_value = 1.33
    else:
        ramp.color_ramp.interpolation = "CONSTANT"
        mat_sand.set_ramp(ramp.color_ramp, mat_sand.PALETTE)
        share, r0, r1 = 0.28, 0.35, 0.75
        bsdf.inputs["IOR"].default_value = 1.54
    rough.inputs["To Min"].default_value = r0
    rough.inputs["To Max"].default_value = r1
    mix.inputs[0].default_value = share
    L = nt.links.new
    L(attr.outputs["Factor"], ramp.inputs[0])
    L(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    L(ramp.outputs["Color"], trans.inputs["Color"])
    L(attr.outputs["Factor"], rough.inputs["Value"])
    L(rough.outputs[0], bsdf.inputs["Roughness"])
    L(bsdf.outputs[0], mix.inputs[1])
    L(trans.outputs[0], mix.inputs[2])
    L(mix.outputs[0], out.inputs["Surface"])
    return mat


_DUST_COLOR = {ELEM_SAND: (0.62, 0.50, 0.36), ELEM_SNOW: (0.93, 0.95, 0.98),
               ELEM_MUD: (0.30, 0.24, 0.18)}


def dust_material(element: str = ELEM_SAND) -> bpy.types.Material:
    """Volume material of the haze: reads the ``density`` grid the dust
    stage writes. Slightly forward scattering, so it lights up against the
    sun like real dust."""
    from ..constants import MAT_DUST
    name = f"{MAT_DUST}_{element.title()}"
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat[PROP_MAT_GENERATED] = True
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*_DUST_COLOR.get(
        element, _DUST_COLOR[ELEM_SAND]), 1.0)
    vol.inputs["Density"].default_value = 1.0
    vol.inputs["Anisotropy"].default_value = 0.35
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    return mat


def drop_material() -> bpy.types.Material:
    """Drops of water carrying silt: milky brown, glossy, light passes."""
    from ..constants import MAT_MUD_DROP
    mat = bpy.data.materials.get(MAT_MUD_DROP)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MAT_MUD_DROP)
    mat[PROP_MAT_GENERATED] = True
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.17, 0.115, 0.065, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Transmission Weight"].default_value = 0.3
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat
