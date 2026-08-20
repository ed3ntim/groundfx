# SPDX-License-Identifier: GPL-3.0-or-later
"""The ground simulation node group.

M1 scope — a minimal but *real* solver: it establishes the material layer,
then each frame carves the surface down where a collider intrudes, so a moving
object leaves a visible trench. Piling (E3-S3), slope relaxation (E3-S2) and
multi-collider support (E4) extend this same group later; the interface is
already shaped for them.

Carve trick: cast a ray straight up from just below the base. The first hit is
the collider's *underside*. If that underside sits below the current material
surface, the surface is pushed down to it. No Python runs per frame — the whole
thing is nodes, so it bakes.

Verified against Blender 5.2.
"""
from __future__ import annotations

import bpy

from ..ng_builder import NodeTreeBuilder, new_geometry_group
from ..ng_zones import make_simulation_zone
from ..constants import (
    NG_GROUND_SIM, ATTR_HEIGHT, ATTR_BASE, ATTR_CARVE,
    DEFAULT_MATERIAL_HEIGHT,
)

# Group input socket names (also used by the property/socket mapping).
IN_GEOMETRY = "Geometry"
IN_MATERIAL_HEIGHT = "Material Height"
IN_COLLIDER = "Collider"
IN_COLLIDER_OFFSET = "Collider Offset"
OUT_GEOMETRY = "Geometry"

_RAY_LENGTH = 10.0  # metres; ample for the close-up domain scale


def _store_float(b, geo_socket_node, geo_key, name, value_node, value_key):
    """Append a Store Named Attribute(FLOAT, POINT) to the geometry chain."""
    store = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                  domain="POINT", inputs={"Name": name})
    b.link(geo_socket_node, geo_key, store, "Geometry")
    b.link(value_node, value_key, store, "Value")
    return store


def build(name: str = NG_GROUND_SIM) -> bpy.types.GeometryNodeTree:
    tree = new_geometry_group(name)
    b = NodeTreeBuilder(tree)

    # -- interface ----------------------------------------------------------
    b.input(IN_GEOMETRY, "NodeSocketGeometry")
    b.input(IN_MATERIAL_HEIGHT, "NodeSocketFloat",
            default=DEFAULT_MATERIAL_HEIGHT, min=0.0, max=5.0,
            subtype="DISTANCE",
            description="Resting thickness of the material layer")
    b.input(IN_COLLIDER, "NodeSocketObject",
            description="Object that carves the material (E4 adds collections)")
    b.input(IN_COLLIDER_OFFSET, "NodeSocketFloat", default=0.0,
            min=-0.5, max=0.5, subtype="DISTANCE",
            description="Penetration tolerance added to the collider surface")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")

    gin, gout = b.group_io()

    # -- initial state: set base = current Z, h = material height -----------
    pos = b.add("GeometryNodeInputPosition")
    sep = b.add("ShaderNodeSeparateXYZ")
    b.link(pos, "Position", sep, "Vector")

    init_base = _store_float(b, gin, IN_GEOMETRY, ATTR_BASE, sep, "Z")
    # h = Material Height (broadcast scalar) on every point.
    init_h = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                   domain="POINT", inputs={"Name": ATTR_HEIGHT})
    b.link(init_base, "Geometry", init_h, "Geometry")
    b.link(gin, IN_MATERIAL_HEIGHT, init_h, "Value")

    # -- simulation zone (geometry state carries the attributes) ------------
    zone = make_simulation_zone(b, state_items=[])
    b.link(init_h, "Geometry", zone.input, "Geometry")

    sim_geo = zone.input  # geometry available at the zone's input node output

    # Read previous-frame attributes.
    read_base = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                      inputs={"Name": ATTR_BASE})
    read_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_HEIGHT})

    # surface_old = base + h
    surface_old = b.add("ShaderNodeMath", operation="ADD",
                        label="surface = base + h")
    b.link(read_base, "Attribute", surface_old, 0)
    b.link(read_h, "Attribute", surface_old, 1)

    # Ray source well below base so it starts *under* any collider: cast up
    # from (x, y, base - RAY_LENGTH) to hit the collider's underside first.
    src_z = b.add("ShaderNodeMath", operation="SUBTRACT",
                  inputs={1: _RAY_LENGTH}, label="base - RAY_LENGTH")
    b.link(read_base, "Attribute", src_z, 0)
    pos2 = b.add("GeometryNodeInputPosition")
    sep2 = b.add("ShaderNodeSeparateXYZ")
    b.link(pos2, "Position", sep2, "Vector")
    src = b.add("ShaderNodeCombineXYZ")
    b.link(sep2, "X", src, "X")
    b.link(sep2, "Y", src, "Y")
    b.link(src_z, "Value", src, "Z")

    obj_info = b.add("GeometryNodeObjectInfo", transform_space="RELATIVE")
    b.link(gin, IN_COLLIDER, obj_info, "Object")

    ray = b.add("GeometryNodeRaycast", data_type="FLOAT",
                inputs={"Ray Length": 2.0 * _RAY_LENGTH,
                        "Ray Direction": (0.0, 0.0, 1.0)})
    b.link(obj_info, "Geometry", ray, "Target Geometry")
    b.link(src, "Vector", ray, "Source Position")

    hit_sep = b.add("ShaderNodeSeparateXYZ")
    b.link(ray, "Hit Position", hit_sep, "Vector")
    # Apply collider offset: raise the effective underside by the tolerance.
    hit_z = b.add("ShaderNodeMath", operation="ADD", label="hit_z + offset")
    b.link(hit_sep, "Z", hit_z, 0)
    b.link(gin, IN_COLLIDER_OFFSET, hit_z, 1)

    # candidate = is_hit ? hit_z : surface_old
    candidate = b.add("GeometryNodeSwitch", input_type="FLOAT",
                      label="hit_z if hit")
    b.link(ray, "Is Hit", candidate, "Switch")
    b.link(surface_old, "Value", candidate, "False")
    b.link(hit_z, "Value", candidate, "True")

    # new_surface = clamp(min(candidate, surface_old), >= base)
    lower = b.add("ShaderNodeMath", operation="MINIMUM", label="min(cand, surf)")
    b.link(candidate, "Output", lower, 0)
    b.link(surface_old, "Value", lower, 1)
    new_surface = b.add("ShaderNodeMath", operation="MAXIMUM",
                        label="max(_, base)")
    b.link(lower, "Value", new_surface, 0)
    b.link(read_base, "Attribute", new_surface, 1)

    # new_h = new_surface - base ; carve = surface_old - new_surface
    new_h = b.add("ShaderNodeMath", operation="SUBTRACT", label="new_h")
    b.link(new_surface, "Value", new_h, 0)
    b.link(read_base, "Attribute", new_h, 1)
    carve = b.add("ShaderNodeMath", operation="SUBTRACT", label="carve")
    b.link(surface_old, "Value", carve, 0)
    b.link(new_surface, "Value", carve, 1)

    # Store updated attributes back onto the geometry.
    store_h = _store_float(b, sim_geo, "Geometry", ATTR_HEIGHT, new_h, "Value")
    store_carve = _store_float(b, store_h, "Geometry", ATTR_CARVE, carve, "Value")

    # Displace points to the new surface: pos.z = new_surface.
    new_pos = b.add("ShaderNodeCombineXYZ")
    b.link(sep2, "X", new_pos, "X")
    b.link(sep2, "Y", new_pos, "Y")
    b.link(new_surface, "Value", new_pos, "Z")
    set_pos = b.add("GeometryNodeSetPosition")
    b.link(store_carve, "Geometry", set_pos, "Geometry")
    b.link(new_pos, "Vector", set_pos, "Position")

    b.link(set_pos, "Geometry", zone.output, "Geometry")
    b.link(zone.output, "Geometry", gout, OUT_GEOMETRY)

    b.layout()
    return tree
