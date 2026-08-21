# SPDX-License-Identifier: GPL-3.0-or-later
"""Settle & Freeze — the product-photo hero workflow (E7-S3 / E7-S4).

For a hero still the material must first come to rest and then be captured as a
plain, render-ready mesh with the displaced surface and the ``gfx_*`` attributes
baked in — no live solver, so look-dev and turntables stay fast and stable.

Three operators:
 * Freeze to Mesh      — the current frame -> a new static object (E7-S3).
 * Settle & Freeze     — step until the surface stops moving, then freeze (E7-S4).
 * Photo Setup         — nudge the domain toward hero-shot settings (E7-T11).

Stepping frames from Python here is fine: these are one-shot user actions, not
per-frame callbacks in the render loop, so the solver stays bake-friendly.
"""
from __future__ import annotations

import bpy

from ..core.constants import (
    OP_PREFIX, MODIFIER_NAME, COLLECTION_NAME, ATTR_HEIGHT, QUALITY_HIGH,
)
from ..core import modifier_io
from ..core.nodegroups import ng_ground_sim as gsim
from ..utils import log


def _active_domain(context):
    obj = context.active_object
    if obj is not None and getattr(obj.groundfx, "is_domain", False):
        return obj
    return None


def _read_heights(obj, deps):
    """Evaluated per-point ``gfx_h`` as a numpy array, or None."""
    import numpy as np
    attr = obj.evaluated_get(deps).data.attributes.get(ATTR_HEIGHT)
    if attr is None:
        return None
    arr = np.empty(len(attr.data), dtype="f")
    attr.data.foreach_get("value", arr)
    return arr


def freeze_domain(context, domain):
    """Freeze the domain's current evaluated frame into a new static object."""
    deps = context.evaluated_depsgraph_get()
    ev = domain.evaluated_get(deps)
    mesh = bpy.data.meshes.new_from_object(
        ev, preserve_all_data_layers=True, depsgraph=deps)
    mesh.name = f"{domain.name}_Frozen"

    frozen = bpy.data.objects.new(f"{domain.name}_Frozen", mesh)
    frozen.matrix_world = domain.matrix_world.copy()
    # Carry the materials so the frozen mesh renders like the live domain.
    for slot in domain.data.materials:
        frozen.data.materials.append(slot)

    coll = bpy.data.collections.get(COLLECTION_NAME) or context.scene.collection
    coll.objects.link(frozen)

    # Keep the live domain around but out of the way; the frozen mesh is the
    # render/look-dev object now.
    domain.hide_set(True)
    domain.hide_render = True

    for o in context.selected_objects:
        o.select_set(False)
    frozen.select_set(True)
    context.view_layer.objects.active = frozen
    log.info("froze %s -> %s (%d verts)", domain.name, frozen.name,
             len(mesh.vertices))
    return frozen


class GFX_OT_freeze_to_mesh(bpy.types.Operator):
    """Freeze the current simulated frame into a new static mesh object"""

    bl_idname = f"{OP_PREFIX}.freeze_to_mesh"
    bl_label = "Freeze to Mesh"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        frozen = freeze_domain(context, domain)
        self.report({"INFO"}, f"Froze to {frozen.name}")
        return {"FINISHED"}


class GFX_OT_settle_and_freeze(bpy.types.Operator):
    """Play forward until the surface stops moving, then freeze it to a mesh"""

    bl_idname = f"{OP_PREFIX}.settle_and_freeze"
    bl_label = "Settle & Freeze"
    bl_options = {"REGISTER", "UNDO"}

    threshold: bpy.props.FloatProperty(
        name="Settle Threshold", default=1e-4, min=1e-6, max=1e-1,
        precision=6, subtype="DISTANCE",
        description="Max per-frame height change that still counts as 'at rest'")
    max_frames: bpy.props.IntProperty(
        name="Max Frames", default=240, min=1, max=100000,
        description="Give up (and freeze anyway) after this many frames")

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        import numpy as np
        domain = _active_domain(context)
        scene = context.scene

        start = scene.frame_current
        deps = context.evaluated_depsgraph_get()
        prev = _read_heights(domain, deps)

        settled_frame = None
        last = min(start + self.max_frames, scene.frame_end)
        for f in range(start + 1, last + 1):
            scene.frame_set(f)
            deps = context.evaluated_depsgraph_get()
            cur = _read_heights(domain, deps)
            if prev is not None and cur is not None and len(cur) == len(prev):
                if float(np.max(np.abs(cur - prev))) < self.threshold:
                    settled_frame = f
                    break
            prev = cur

        frozen = freeze_domain(context, domain)
        if settled_frame is not None:
            self.report({"INFO"},
                        f"Settled at frame {settled_frame}, froze to {frozen.name}")
        else:
            self.report({"WARNING"},
                        f"No rest within {self.max_frames} frames; "
                        f"froze frame {scene.frame_current}")
        return {"FINISHED"}


class GFX_OT_photo_setup(bpy.types.Operator):
    """Set the active domain up for a hero product shot"""

    bl_idname = f"{OP_PREFIX}.photo_setup"
    bl_label = "Photo Setup"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        st = domain.groundfx
        st.hero_contact = True  # silhouette-accurate contact edge
        md = domain.modifiers.get(MODIFIER_NAME)
        if md:
            # A denser relaxation settles the surface more cleanly for a still.
            modifier_io.set_input(md, gsim.IN_RELAX_ITERS, 16)
        context.scene.render.engine = "CYCLES"
        note = ""
        if st.quality != QUALITY_HIGH:
            note = " (raise Quality to High/Ultra + re-add for a finer grid)"
        self.report({"INFO"}, f"Photo setup applied{note}")
        return {"FINISHED"}


classes = (
    GFX_OT_freeze_to_mesh,
    GFX_OT_settle_and_freeze,
    GFX_OT_photo_setup,
)
