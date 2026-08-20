# SPDX-License-Identifier: GPL-3.0-or-later
"""E0 smoke test: the addon registers, exposes its panel, and unregisters.

This is the acceptance test for E0-S1/E0-S3: it proves the skeleton loads in a
real Blender before any feature exists.
"""
from __future__ import annotations

import bpy

import harness


def test_import():
    import groundfx  # noqa: F401
    harness.check("import groundfx", True)


def test_register_unregister():
    import groundfx
    groundfx.register()
    # Panel class should now be registered.
    harness.check(
        "panel registered",
        hasattr(bpy.types, "GFX_PT_main"),
        "GFX_PT_main missing after register()",
    )
    # Preferences class present. AddonPreferences are not exposed under their
    # class name in bpy.types (they register by bl_idname); is_registered is
    # the reliable signal.
    from groundfx.data.prefs import GFX_Preferences
    harness.check(
        "prefs registered",
        GFX_Preferences.is_registered,
        "GFX_Preferences.is_registered is False after register()",
    )
    groundfx.unregister()
    harness.check(
        "panel unregistered",
        not hasattr(bpy.types, "GFX_PT_main"),
        "GFX_PT_main still present after unregister()",
    )


def test_reregister_is_clean():
    """Register twice in a row (reload scenario) without leaking classes."""
    import groundfx
    groundfx.register()
    groundfx.unregister()
    groundfx.register()
    ok = hasattr(bpy.types, "GFX_PT_main")
    groundfx.unregister()
    harness.check("re-register clean", ok, "second register() failed")


def test_constants_prefixed():
    """Every reused name carries the gfx/groundfx namespace."""
    from groundfx.core import constants as c
    attrs = [c.ATTR_HEIGHT, c.ATTR_CARVE, c.ATTR_COMP, c.ATTR_WET]
    harness.check(
        "attributes prefixed",
        all(a.startswith("gfx_") for a in attrs),
        f"unprefixed attribute in {attrs}",
    )
    harness.eq("element count", len(c.ELEMENTS), 3)
    harness.eq("quality count", len(c.QUALITY_LEVELS), 4)
