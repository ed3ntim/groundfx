# SPDX-License-Identifier: GPL-3.0-or-later
"""Addon preferences: currently just the debug-logging switch."""
from __future__ import annotations

import bpy

from ..core.constants import ADDON_PKG
from ..utils import log


def _on_debug_changed(self, _context):
    log.set_debug(self.debug)


class GFX_Preferences(bpy.types.AddonPreferences):
    # For an extension the bl_idname is the dotted package path Blender loads
    # it under: "bl_ext.<repo>.<pkg>". We resolve it at registration time in
    # __init__.py and patch it in, so this default only matters as a fallback.
    bl_idname = ADDON_PKG

    debug: bpy.props.BoolProperty(
        name="Debug Logging",
        description="Print verbose GroundFX diagnostics to the system console",
        default=False,
        update=_on_debug_changed,
    )

    def draw(self, _context):
        self.layout.prop(self, "debug")


classes = (
    GFX_Preferences,
)
