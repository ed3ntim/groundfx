# SPDX-License-Identifier: GPL-3.0-or-later
"""Coat objects: material clinging to collider flanks (see ``ng_coat``).

One coat object per collider and domain. It lives in the GroundFX
collection, stays at the world origin and is never itself a collider.
Everything is idempotent so the collider operators, the element switch and
the repair path can all call ``sync_coats``.
"""
from __future__ import annotations

import bpy

from ..core import modifier_io
from ..core.constants import OP_PREFIX, COAT_MODIFIER_NAME
from ..core.ng_library import ensure_node_group
from ..core.nodegroups import ng_coat as ncoat
from ..core.materials import mat_builder as matb

# Elements whose material clings to objects.
COAT_ELEMENTS = tuple(ncoat.PROFILES)


def coat_name(collider) -> str:
    return f"{collider.name} Coat"


def find_coat(domain, collider):
    """The coat object for this collider on this domain, or None."""
    for o in bpy.data.objects:
        st = o.groundfx
        if st.coat_source is collider and st.coat_domain is domain:
            return o
    return None


def coats_of(domain):
    return [o for o in bpy.data.objects if o.groundfx.coat_domain is domain]


def remove_coat(domain, collider) -> None:
    coat = find_coat(domain, collider)
    if coat is not None:
        me = coat.data
        bpy.data.objects.remove(coat, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def _push(coat, domain, collider) -> None:
    element = domain.groundfx.element
    tree = ensure_node_group(ncoat.group_name(element),
                             lambda name: ncoat.build(name, element))
    modifier_io.invalidate(tree.name)
    md = coat.modifiers.get(COAT_MODIFIER_NAME)
    if md is None:
        md = coat.modifiers.new(COAT_MODIFIER_NAME, "NODES")
    switched = md.node_group is not tree
    md.node_group = tree
    set_ = modifier_io.set_input
    set_(md, ncoat.IN_COLLIDER, collider, tag=False)
    set_(md, ncoat.IN_DOMAIN, domain, tag=False)
    set_(md, ncoat.IN_MATERIAL, matb.domain_material(domain), tag=False)
    # sample the ground about a cell and a half outside the face
    from ..data import quality as qmod
    st = domain.groundfx
    cell = st.domain_size / qmod.profile(st.quality).resolution
    set_(md, ncoat.IN_REACH, 1.5 * cell, tag=False)
    if switched:
        prof = ncoat.defaults(element)
        set_(md, ncoat.IN_DENSITY, prof["density"], tag=False)
        set_(md, ncoat.IN_SPLASH, prof["splash"], tag=False)
        set_(md, ncoat.IN_CLING, prof["cling"], tag=False)
    coat.update_tag()


def ensure_coat(context, domain, collider):
    """Create (or refresh) the coat object for ``collider``. Returns it, or
    None if the domain's element has no coat."""
    if domain.groundfx.element not in COAT_ELEMENTS:
        remove_coat(domain, collider)
        return None
    coat = find_coat(domain, collider)
    if coat is None:
        from .op_add import get_groundfx_collection
        mesh = bpy.data.meshes.new(coat_name(collider))
        coat = bpy.data.objects.new(coat_name(collider), mesh)
        coat.groundfx.coat_source = collider
        coat.groundfx.coat_domain = domain
        coat.hide_select = True          # it must stay at the origin
        get_groundfx_collection(context).objects.link(coat)
    _push(coat, domain, collider)
    return coat


def sync_coats(context, domain) -> int:
    """Bring every coat of ``domain`` in line with its settings: make them
    for all colliders when Coat Colliders is on, drop them when it is off or
    a collider has left. Returns the number of coats afterwards."""
    st = domain.groundfx
    coll = st.collider_collection
    members = set()
    if coll is not None:
        for o in coll.objects:
            members.add(o.groundfx.proxy_source or o)
    for coat in coats_of(domain):
        src = coat.groundfx.coat_source
        if (not st.coat_colliders or src is None or src not in members
                or st.element not in COAT_ELEMENTS):
            remove_coat(domain, src) if src is not None else \
                bpy.data.objects.remove(coat, do_unlink=True)
    if not st.coat_colliders or st.element not in COAT_ELEMENTS:
        return 0
    for src in members:
        ensure_coat(context, domain, src)
    return len(members)


class GFX_OT_sync_coats(bpy.types.Operator):
    """Rebuild the clinging material on all colliders of the active domain"""

    bl_idname = f"{OP_PREFIX}.sync_coats"
    bl_label = "Refresh Coats"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and getattr(ob.groundfx, "is_domain", False)

    def execute(self, context):
        n = sync_coats(context, context.active_object)
        self.report({"INFO"}, f"{n} coat(s)")
        return {"FINISHED"}


classes = (GFX_OT_sync_coats,)
