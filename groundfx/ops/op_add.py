# SPDX-License-Identifier: GPL-3.0-or-later
"""Add Sand / Snow / Mud — one click to a working domain.

Creates a grid mesh at the 3D cursor, attaches the ground-simulation modifier,
seeds sensible per-element defaults, and files the object under the GroundFX
collection. This is the E2 deliverable; the material assignment is a stub until
the shaders land in E8.
"""
from __future__ import annotations

import bpy

from ..core import modifier_io
from ..core.constants import (
    ELEMENTS, ELEMENT_LABELS, MODIFIER_NAME, COLLECTION_NAME,
    PROP_IS_DOMAIN, PROP_ELEMENT, OP_PREFIX,
    DEFAULT_DOMAIN_SIZE, QUALITY_MEDIUM,
)
from ..core.ng_library import ensure_node_group
from ..core.nodegroups import ng_ground_sim as gsim
from ..data import quality as qmod
from ..utils import log


def _get_collection(context) -> bpy.types.Collection:
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION_NAME)
        context.scene.collection.children.link(coll)
    return coll


def _make_grid_mesh(name: str, size: float, resolution: int) -> bpy.types.Mesh:
    """Build a flat grid mesh directly (no bpy.ops, so it works headless)."""
    import numpy as np

    n = resolution + 1
    xs = (np.linspace(0.0, 1.0, n) - 0.5) * size
    grid_x, grid_y = np.meshgrid(xs, xs)
    verts = np.column_stack(
        (grid_x.ravel(), grid_y.ravel(), np.zeros(n * n)))

    # Quad faces.
    idx = np.arange(n * n).reshape(n, n)
    v0 = idx[:-1, :-1].ravel()
    v1 = idx[:-1, 1:].ravel()
    v2 = idx[1:, 1:].ravel()
    v3 = idx[1:, :-1].ravel()
    faces = np.column_stack((v0, v1, v2, v3))

    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.ravel())
    mesh.loops.add(faces.size)
    mesh.polygons.add(len(faces))
    mesh.loops.foreach_set("vertex_index", faces.ravel())
    mesh.polygons.foreach_set("loop_start", np.arange(0, faces.size, 4))
    mesh.polygons.foreach_set("loop_total", np.full(len(faces), 4))
    mesh.update()
    mesh.validate()
    return mesh


def create_domain(context, element: str,
                  size: float = DEFAULT_DOMAIN_SIZE) -> bpy.types.Object:
    """Create and return a fully wired GroundFX domain object."""
    quality_key = QUALITY_MEDIUM
    prof = qmod.profile(quality_key)

    name = f"GroundFX_{ELEMENT_LABELS[element]}"
    mesh = _make_grid_mesh(name, size, prof.resolution)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = context.scene.cursor.location

    _get_collection(context).objects.link(obj)

    # Node group + modifier.
    tree = ensure_node_group(gsim.NG_GROUND_SIM, gsim.build)
    modifier_io.invalidate(tree.name)
    md = obj.modifiers.new(MODIFIER_NAME, "NODES")
    md.node_group = tree

    # Object-level settings.
    st = obj.groundfx
    st.is_domain = True
    st.element = element
    st.quality = quality_key
    st.domain_size = size
    obj[PROP_IS_DOMAIN] = True
    obj[PROP_ELEMENT] = element

    # Seed modifier inputs.
    modifier_io.set_input(md, gsim.IN_MATERIAL_HEIGHT, st.material_height)
    log.info("created %s domain (%d^2, %.2f m)", element, prof.resolution, size)
    return obj


class GFX_OT_add_ground(bpy.types.Operator):
    """Add a GroundFX domain of the given element at the 3D cursor"""

    bl_idname = f"{OP_PREFIX}.add_ground"
    bl_label = "Add GroundFX Ground"
    bl_options = {"REGISTER", "UNDO"}

    element: bpy.props.EnumProperty(
        name="Element",
        items=[(k, ELEMENT_LABELS[k], "") for k in ELEMENTS],
        default=ELEMENTS[0],
    )

    def execute(self, context):
        obj = create_domain(context, self.element)
        # Select and activate the new domain.
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"Added {ELEMENT_LABELS[self.element]} domain")
        return {"FINISHED"}


classes = (
    GFX_OT_add_ground,
)
