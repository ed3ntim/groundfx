# SPDX-License-Identifier: GPL-3.0-or-later
"""GroundFX — deformable sand, snow and mud for Blender.

Extension entry point. Metadata lives in ``blender_manifest.toml`` (no legacy
``bl_info`` dict). This module owns nothing but registration; every feature
lives in its own subpackage and is collected through ``registry``.
"""
from __future__ import annotations

import bpy

from . import registry
from .core.constants import ADDON_NAME
from .data import prefs as _prefs
from .utils import compat, log

# Track what we actually registered so unregister is exact and reversible,
# even if registration aborted half-way.
_registered: list = []


def _guard_version() -> bool:
    """Refuse to load on unsupported Blender, with a clear message."""
    if compat.is_supported():
        return True
    have = compat.version_string()
    need = ".".join(str(n) for n in compat.BLENDER_MIN)
    log.error(
        "%s requires Blender %s or newer, but this is %s. Not registering.",
        ADDON_NAME, need, have,
    )
    return False


def register() -> None:
    if not _guard_version():
        return

    # Self-heal: if a previous register() left classes behind (reload, or a
    # test that skipped teardown), tear them down before registering again.
    if _registered:
        unregister()

    # The extension is imported as "bl_ext.<repo>.groundfx"; the preferences
    # class must advertise that exact module path as its bl_idname.
    _prefs.GFX_Preferences.bl_idname = __package__

    _registered.clear()
    for cls in registry.all_classes():
        bpy.utils.register_class(cls)
        _registered.append(cls)

    registry.register_extras()

    # Apply the persisted debug setting now that preferences exist.
    try:
        addon = bpy.context.preferences.addons.get(__package__)
        if addon:
            log.set_debug(addon.preferences.debug)
    except Exception:  # noqa: BLE001 -- preferences may be absent in --background
        pass

    log.info("%s registered (%d classes).", ADDON_NAME, len(_registered))


def unregister() -> None:
    try:
        registry.unregister_extras()
    except Exception:  # noqa: BLE001
        pass
    # Unregister in reverse so dependents go before their dependencies.
    for cls in reversed(_registered):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            # Already gone (e.g. reload); keep tearing down the rest.
            pass
    _registered.clear()
    log.info("%s unregistered.", ADDON_NAME)
