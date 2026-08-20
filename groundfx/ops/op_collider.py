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
    PROXY_NONE, PROXY_MODES, PROXY_MODE_LABELS, PROXY_TYPE_INT,
)
from ..core import modifier_io
from ..core.ng_library import ensure_node_group
from ..core.nodegroups import ng_ground_sim as gsim
from ..core.nodegroups import ng_collider_proxy as proxymod
from ..utils import log


def _find_proxy(coll, source):
    """Return the proxy object in ``coll`` standing in for ``source``, or None."""
    for o in coll.objects:
        if o.groundfx.proxy_source is source:
            return o
    return None


def _ensure_proxy(context, source, mode, coll):
    """Create or update the low-poly proxy for ``source`` inside ``coll``."""
    proxy = _find_proxy(coll, source)
    if proxy is None:
        mesh = bpy.data.meshes.new(f"GFX_Proxy_{source.name}")
        proxy = bpy.data.objects.new(f"GFX_Proxy_{source.name}", mesh)
        proxy.groundfx.proxy_source = source
        proxy.hide_render = True
        proxy.display_type = "WIRE"
        tree = ensure_node_group(proxymod.NG_COLLIDER_PROXY, proxymod.build)
        modifier_io.invalidate(tree.name)
        md = proxy.modifiers.new("GFX_Proxy", "NODES")
        md.node_group = tree
        modifier_io.set_input(md, proxymod.IN_SOURCE, source, tag=False)
        coll.objects.link(proxy)
    md = proxy.modifiers.get("GFX_Proxy")
    if md:
        modifier_io.set_input(md, proxymod.IN_PROXY_TYPE, PROXY_TYPE_INT[mode])
    return proxy


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

    proxy: bpy.props.EnumProperty(
        name="Proxy", default=0,
        items=[(m, PROXY_MODE_LABELS[m], PROXY_MODE_LABELS[m])
               for m in PROXY_MODES],
        description="Use a cheap low-poly stand-in for the raycast instead of "
                    "the original mesh (needed for high-poly colliders)")

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        coll = ensure_collider_collection(context, domain)
        targets = [o for o in context.selected_objects
                   if o is not domain and not o.groundfx.is_domain
                   and o.groundfx.proxy_source is None]
        if not targets:
            self.report({"WARNING"},
                        "Select one or more non-domain objects to mark")
            return {"CANCELLED"}

        added = 0
        for o in targets:
            o[PROP_IS_COLLIDER] = True
            o.groundfx.is_collider = True
            o.groundfx.collider_proxy = self.proxy
            if self.proxy == PROXY_NONE:
                # A previously created proxy is now stale -> drop it.
                stale = _find_proxy(coll, o)
                if stale is not None:
                    bpy.data.objects.remove(stale, do_unlink=True)
                if o.name not in coll.objects:
                    coll.objects.link(o)
                    added += 1
            else:
                if o.name in coll.objects:
                    coll.objects.unlink(o)  # raycast the proxy, not the original
                _ensure_proxy(context, o, self.proxy, coll)
                added += 1
        domain.update_tag()
        log.info("marked %d collider(s) on %s (proxy=%s)",
                 added, domain.name, self.proxy)
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
            src = o.groundfx.proxy_source
            if src is not None:
                # o is a proxy object: clear the real collider it stood in for
                # and delete the proxy entirely.
                src.groundfx.is_collider = False
                if PROP_IS_COLLIDER in src:
                    del src[PROP_IS_COLLIDER]
                bpy.data.objects.remove(o, do_unlink=True)
            else:
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
