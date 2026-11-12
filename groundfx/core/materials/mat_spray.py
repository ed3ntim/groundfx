# SPDX-License-Identifier: GPL-3.0-or-later
"""Material of airborne sand grains.

Each grain is one point, so there is no texture to speak of: a grain has one
mineral colour (same palette as the bed, so thrown sand is the sand that was
on the ground) and its own roughness. Quartz is translucent. Against the
light a real sheet of sand glows at its thin edges while its dense core stays
dark, and that contrast is most of what makes sand in the air look like
sand. A share of translucency gives it.
"""
from __future__ import annotations

import bpy

from ..constants import MAT_SAND_SPRAY, PROP_MAT_GENERATED
from . import mat_sand

ATTR_GRAIN_ID = "gfx_grain_id"
_TRANSLUCENT = 0.28


def spray_material() -> bpy.types.Material:
    mat = bpy.data.materials.get(MAT_SAND_SPRAY)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MAT_SAND_SPRAY)
    mat[PROP_MAT_GENERATED] = True
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = ATTR_GRAIN_ID
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    mat_sand.set_ramp(ramp.color_ramp, mat_sand.PALETTE)
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.35
    rough.inputs["To Max"].default_value = 0.75
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["IOR"].default_value = 1.54
    trans = nt.nodes.new("ShaderNodeBsdfTranslucent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = _TRANSLUCENT
    out = nt.nodes.new("ShaderNodeOutputMaterial")
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
