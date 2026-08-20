# SPDX-License-Identifier: GPL-3.0-or-later
"""User-facing panels (3D-view N-panel)."""
from __future__ import annotations

import bpy

from ..core.constants import (
    ADDON_NAME, PANEL_CATEGORY, ELEMENT_LABELS, ELEM_SAND, ELEM_SNOW, ELEM_MUD,
    OP_PREFIX,
)
from ..data import quality as qmod

_LIGHT_ICON = {"GREEN": "COLORSET_03_VEC", "AMBER": "COLORSET_09_VEC",
               "RED": "COLORSET_01_VEC"}


class GFX_PT_main(bpy.types.Panel):
    """Root GroundFX panel: the Add tools."""

    bl_label = ADDON_NAME
    bl_idname = "GFX_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Add material:")
        row = col.row(align=True)
        for elem in (ELEM_SAND, ELEM_SNOW, ELEM_MUD):
            op = row.operator(f"{OP_PREFIX}.add_ground",
                              text=ELEMENT_LABELS[elem])
            op.element = elem


class GFX_PT_domain(bpy.types.Panel):
    """Per-domain settings, shown when a GroundFX domain is active."""

    bl_label = "Domain"
    bl_idname = "GFX_PT_domain"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and getattr(obj.groundfx, "is_domain", False)

    def draw(self, context):
        layout = self.layout
        st = context.active_object.groundfx

        col = layout.column()
        col.prop(st, "element")
        col.prop(st, "quality")

        # Live resolution / cell-size readout with a traffic light.
        prof = qmod.profile(st.quality)
        cs = qmod.cell_size(st.domain_size, st.quality)
        light = qmod.traffic_light(st.domain_size, st.quality)
        box = layout.box()
        box.label(text=f"{prof.resolution}²  ·  "
                       f"{prof.vertex_count:,} verts",
                  icon="MESH_GRID")
        box.label(text=f"Cell size: {cs * 100:.1f} cm",
                  icon=_LIGHT_ICON.get(light, "DOT"))
        box.label(text=f"~{prof.target_ms[0]:.0f}–{prof.target_ms[1]:.0f} "
                       f"ms/frame")

        col = layout.column()
        col.prop(st, "domain_size")
        col.prop(st, "material_height")
        col.prop(st, "hero_contact")


class GFX_UL_colliders(bpy.types.UIList):
    """Rows of the active domain's collider collection."""

    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_prop, index):
        # ``item`` is a CollectionObject wrapper; item.name is the object name.
        obj = getattr(item, "object", None) or item
        src = obj.groundfx.proxy_source
        if src is not None:
            from ..core.constants import PROXY_MODE_LABELS
            label = PROXY_MODE_LABELS.get(src.groundfx.collider_proxy, "Proxy")
            layout.label(text=src.name, icon="OBJECT_DATA")
            layout.label(text=label, icon="MOD_MESHDEFORM")
        else:
            layout.label(text=obj.name, icon="OBJECT_DATA")


class GFX_PT_colliders(bpy.types.Panel):
    """Collider list + mark/unmark tools for the active domain."""

    bl_label = "Colliders"
    bl_idname = "GFX_PT_colliders"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_parent_id = "GFX_PT_domain"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and getattr(obj.groundfx, "is_domain", False)

    def draw(self, context):
        layout = self.layout
        st = context.active_object.groundfx
        coll = st.collider_collection

        row = layout.row()
        if coll is not None:
            row.template_list(
                "GFX_UL_colliders", "", coll, "objects", st, "collider_active",
                rows=3)
            side = row.column(align=True)
            side.operator(f"{OP_PREFIX}.unmark_collider", text="", icon="X")
            n = len(coll.objects)
            layout.label(text=f"{n} collider{'' if n == 1 else 's'}",
                         icon="OBJECT_DATA")
        else:
            layout.label(text="No collider collection", icon="ERROR")

        layout.operator_menu_enum(f"{OP_PREFIX}.mark_collider", "proxy",
                                  text="Mark as Collider", icon="ADD")


classes = (
    GFX_PT_main,
    GFX_PT_domain,
    GFX_UL_colliders,
    GFX_PT_colliders,
)
