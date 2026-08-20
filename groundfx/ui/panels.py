# SPDX-License-Identifier: GPL-3.0-or-later
"""User-facing panels.

E0 ships a minimal N-panel so the addon has a visible footprint the moment it
is enabled. It grows into the full layout (PLAN.md section 7) across E2/E9.
"""
from __future__ import annotations

import bpy

from ..core.constants import ADDON_NAME, PANEL_CATEGORY
from ..utils import compat


class GFX_PT_main(bpy.types.Panel):
    """Root GroundFX panel in the 3D viewport sidebar."""

    bl_label = ADDON_NAME
    bl_idname = "GFX_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY

    def draw(self, context):
        layout = self.layout
        # Placeholder body until the Add operators land in E2.
        col = layout.column(align=True)
        col.label(text="GroundFX is active.", icon="CHECKMARK")
        col.label(text=f"Blender {compat.version_string()}")
        col.separator()
        col.label(text="Add tools arrive in E2.", icon="INFO")


# Classes this module contributes to the central registry.
classes = (
    GFX_PT_main,
)
