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
        col.operator_menu_enum(f"{OP_PREFIX}.apply_preset", "preset",
                               text="Apply Preset", icon="PRESET")
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
                       f"ms/frame (est.)")
        row = box.row(align=True)
        row.operator(f"{OP_PREFIX}.benchmark", text="Measure", icon="TIME")
        if st.measured_ms >= 0.0:
            over = st.measured_ms > 2.0 * prof.target_ms[1]
            row.label(text=f"{st.measured_ms:.1f} ms",
                      icon="ERROR" if over else "CHECKMARK")

        # Quality/Size only take effect once the grid is rebuilt to match.
        from ..ops.op_add import grid_is_current
        if not grid_is_current(context.active_object):
            warn = box.row(align=True)
            warn.alert = True
            warn.label(text="Grid outdated", icon="ERROR")
            warn.operator(f"{OP_PREFIX}.rebuild_grid", text="Rebuild",
                          icon="FILE_REFRESH")

        col = layout.column()
        col.prop(st, "domain_size")
        col.prop(st, "material_height")
        col.prop(st, "stickiness", slider=True)
        col.prop(st, "terrain")
        if st.terrain is not None:
            col.label(text="Press Rebuild to conform to terrain", icon="INFO")
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
            if n == 0:
                hint = layout.row()
                hint.label(text="No colliders — nothing will deform",
                           icon="INFO")
            else:
                layout.label(text=f"{n} collider{'' if n == 1 else 's'}",
                             icon="OBJECT_DATA")
        else:
            layout.label(text="No collider collection", icon="ERROR")

        layout.prop(st, "collider_pick", text="Add")
        layout.operator_menu_enum(f"{OP_PREFIX}.mark_collider", "proxy",
                                  text="Mark Selected", icon="ADD")

        # Live Sculpt: drag a collider and see the trace without pressing Play.
        active = context.scene.gfx_live_active
        layout.separator()
        layout.operator(f"{OP_PREFIX}.live_sculpt",
                        text="Live Sculpt" + (" (on)" if active else ""),
                        icon="GREASEPENCIL", depress=active)


class GFX_PT_look(bpy.types.Panel):
    """Material look: a few well-named sliders (E8-S3)."""

    bl_label = "Look"
    bl_idname = "GFX_PT_look"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_parent_id = "GFX_PT_domain"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and getattr(obj.groundfx, "is_domain", False)

    def draw(self, context):
        from ..core.materials import mat_builder as matb

        layout = self.layout
        obj = context.active_object
        st = obj.groundfx

        col = layout.column()
        col.prop(st, "look_base_color")
        col.prop(st, "look_roughness", slider=True)
        col.prop(st, "look_detail", slider=True)
        col.prop(st, "wetness", slider=True)

        if matb.domain_material(obj) is None:
            layout.label(text="Custom material in use", icon="INFO")


class GFX_PT_cache(bpy.types.Panel):
    """Bake / free the simulation cache."""

    bl_label = "Cache"
    bl_idname = "GFX_PT_cache"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_parent_id = "GFX_PT_domain"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and getattr(obj.groundfx, "is_domain", False)

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator(f"{OP_PREFIX}.bake", icon="PHYSICS")
        row.operator(f"{OP_PREFIX}.free", icon="TRASH")
        row = layout.row(align=True)
        row.operator(f"{OP_PREFIX}.bake_all")
        row.operator(f"{OP_PREFIX}.free_all")


class GFX_PT_photo(bpy.types.Panel):
    """Settle & Freeze workflow for hero / product shots."""

    bl_label = "Settle & Freeze"
    bl_idname = "GFX_PT_photo"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_parent_id = "GFX_PT_domain"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and getattr(obj.groundfx, "is_domain", False)

    def draw(self, context):
        layout = self.layout
        from ..ops.op_freeze import hero_detail_modifier

        col = layout.column(align=True)
        col.operator(f"{OP_PREFIX}.photo_setup", icon="CAMERA_DATA")
        on = hero_detail_modifier(context.active_object) is not None
        col.operator(f"{OP_PREFIX}.hero_detail",
                     text="Hero Detail" + (" (on)" if on else ""),
                     icon="MOD_SUBSURF", depress=on)
        col.operator(f"{OP_PREFIX}.settle_and_freeze", icon="FREEZE")
        col.operator(f"{OP_PREFIX}.freeze_to_mesh", icon="MESH_DATA")


class GFX_MT_add(bpy.types.Menu):
    """GroundFX entries under the 3D-view Add menu (Shift+A)."""

    bl_idname = "GFX_MT_add"
    bl_label = ADDON_NAME

    def draw(self, context):
        layout = self.layout
        for elem in (ELEM_SAND, ELEM_SNOW, ELEM_MUD):
            op = layout.operator(f"{OP_PREFIX}.add_ground",
                                 text=ELEMENT_LABELS[elem], icon="MESH_GRID")
            op.element = elem


def _draw_add_menu(self, context):
    self.layout.menu(GFX_MT_add.bl_idname, icon="MESH_GRID")


def register_menu():
    bpy.types.VIEW3D_MT_add.append(_draw_add_menu)


def unregister_menu():
    bpy.types.VIEW3D_MT_add.remove(_draw_add_menu)


classes = (
    GFX_PT_main,
    GFX_PT_domain,
    GFX_UL_colliders,
    GFX_PT_colliders,
    GFX_PT_look,
    GFX_PT_cache,
    GFX_PT_photo,
    GFX_MT_add,
)
