# SPDX-License-Identifier: GPL-3.0-or-later
"""Mark / unmark objects as colliders for a GroundFX domain (E4-S1).

Each domain owns a *collider collection* ("<domain> Colliders"), nested under
the GroundFX collection. The solver raycasts against the union of everything in
it, so any number of objects — including instances and animated ones — carve
the material at once. These operators are the user-facing way to fill and empty
that collection without ever touching the node setup.
"""
from __future__ import annotations

import bpy

from ..core.constants import (
    OP_PREFIX, PROP_IS_COLLIDER, COLLIDER_COLLECTION_SUFFIX, MODIFIER_NAME,
)
from ..core import modifier_io
from ..core.nodegroups import ng_ground_sim as gsim
from ..utils import log


def collider_collection_name(domain: bpy.types.Object) -> str:
    return f"{domain.name}{COLLIDER_COLLECTION_SUFFIX}"


def ensure_collider_collection(context, domain: bpy.types.Object
                               ) -> bpy.types.Collection:
    """Return the domain's collider collection, creating and wiring it once.

    Idempotent: if the domain already points at a collection we return it. The
    new collection is nested under the GroundFX collection and pushed into the
    modifier's Colliders input so the raycast sees it immediately.
    """
    st = domain.groundfx
    coll = st.collider_collection
    if coll is not None:
        return coll

    from .op_add import get_groundfx_collection

    coll = bpy.data.collections.new(collider_collection_name(domain))
    get_groundfx_collection(context).children.link(coll)
    # Assigning the pointer fires _push_collider_collection, which writes the
    # modifier input; do it explicitly too in case the callback is suppressed.
    st.collider_collection = coll
    md = domain.modifiers.get(MODIFIER_NAME)
    if md:
        modifier_io.set_input(md, gsim.IN_COLLIDER_COLLECTION, coll)
    return coll


def _active_domain(context):
    obj = context.active_object
    if obj is not None and getattr(obj.groundfx, "is_domain", False):
        return obj
    return None


class GFX_OT_mark_collider(bpy.types.Operator):
    """Add the selected objects to the active domain's collider collection"""

    bl_idname = f"{OP_PREFIX}.mark_collider"
    bl_label = "Mark as Collider"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        coll = ensure_collider_collection(context, domain)
        targets = [o for o in context.selected_objects
                   if o is not domain and not o.groundfx.is_domain]
        if not targets:
            self.report({"WARNING"},
                        "Select one or more non-domain objects to mark")
            return {"CANCELLED"}

        added = 0
        for o in targets:
            if o.name not in coll.objects:
                coll.objects.link(o)
                added += 1
            o[PROP_IS_COLLIDER] = True
            o.groundfx.is_collider = True
        domain.update_tag()
        log.info("marked %d collider(s) on %s", added, domain.name)
        self.report({"INFO"}, f"Marked {added} collider(s)")
        return {"FINISHED"}


class GFX_OT_unmark_collider(bpy.types.Operator):
    """Remove a collider from the active domain's collider collection"""

    bl_idname = f"{OP_PREFIX}.unmark_collider"
    bl_label = "Remove Collider"
    bl_options = {"REGISTER", "UNDO"}

    # When False, remove the collider selected in the UIList; when True, remove
    # every currently selected object that is in the collection.
    use_selection: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        domain = _active_domain(context)
        return domain is not None and domain.groundfx.collider_collection

    def execute(self, context):
        domain = _active_domain(context)
        coll = domain.groundfx.collider_collection
        members = list(coll.objects)

        if self.use_selection:
            targets = [o for o in context.selected_objects if o in members]
        else:
            idx = domain.groundfx.collider_active
            targets = [members[idx]] if 0 <= idx < len(members) else []

        if not targets:
            self.report({"WARNING"}, "No collider to remove")
            return {"CANCELLED"}

        for o in targets:
            coll.objects.unlink(o)
            o.groundfx.is_collider = False
            if PROP_IS_COLLIDER in o:
                del o[PROP_IS_COLLIDER]

        # Keep the list index in range.
        n = len(coll.objects)
        domain.groundfx.collider_active = min(
            domain.groundfx.collider_active, max(0, n - 1))
        domain.update_tag()
        self.report({"INFO"}, f"Removed {len(targets)} collider(s)")
        return {"FINISHED"}


classes = (
    GFX_OT_mark_collider,
    GFX_OT_unmark_collider,
)
