# SPDX-License-Identifier: GPL-3.0-or-later
"""Collider proxy node group (E4-S2).

A high-poly collider (a 500k-tri character) is ruinous to raycast against once
per grid cell. This group turns a *source* object into a cheap stand-in that the
solver raycasts instead: its bounding box or its convex hull. Both are built
from the source's **evaluated** geometry via Object Info, so the proxy follows
the original through animation and armature deformation for free (E4-T6) — no
constraints, no baking.

The proxy object itself sits at the world origin with identity transform; Object
Info in RELATIVE space bakes the source's world placement into the geometry, so
the domain's Collection Info (also RELATIVE) passes it straight through.

Verified against Blender 5.2.
"""
from __future__ import annotations

import bpy

from ..ng_builder import NodeTreeBuilder, new_geometry_group
from ..constants import NG_COLLIDER_PROXY

IN_SOURCE = "Source"
IN_PROXY_TYPE = "Proxy Type"   # 0 = bounding box, 1 = convex hull
OUT_GEOMETRY = "Geometry"


def build(name: str = NG_COLLIDER_PROXY) -> bpy.types.GeometryNodeTree:
    tree = new_geometry_group(name)
    b = NodeTreeBuilder(tree)

    b.input(IN_SOURCE, "NodeSocketObject",
            description="High-poly object this proxy stands in for")
    b.input(IN_PROXY_TYPE, "NodeSocketInt", default=0, min=0, max=1,
            description="0 = bounding box (cheapest), 1 = convex hull")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")

    gin, gout = b.group_io()

    # Evaluated (deformed) geometry of the source, in this proxy's local space.
    obj_info = b.add("GeometryNodeObjectInfo", transform_space="RELATIVE",
                     inputs={"As Instance": False})
    b.link(gin, IN_SOURCE, obj_info, "Object")

    bbox = b.add("GeometryNodeBoundBox")
    b.link(obj_info, "Geometry", bbox, "Geometry")
    hull = b.add("GeometryNodeConvexHull")
    b.link(obj_info, "Geometry", hull, "Geometry")

    use_hull = b.add("ShaderNodeMath", operation="GREATER_THAN",
                     inputs={1: 0.5}, label="type == hull")
    b.link(gin, IN_PROXY_TYPE, use_hull, 0)

    switch = b.add("GeometryNodeSwitch", input_type="GEOMETRY",
                   label="bbox / hull")
    b.link(use_hull, "Value", switch, "Switch")
    b.link(bbox, "Bounding Box", switch, "False")
    b.link(hull, "Convex Hull", switch, "True")

    b.link(switch, "Output", gout, OUT_GEOMETRY)

    b.layout()
    return tree
