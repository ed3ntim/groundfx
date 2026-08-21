# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply a named preset to a domain (E5-S2/T8)."""
from __future__ import annotations

import bpy

from ..core.constants import OP_PREFIX, MODIFIER_NAME
from ..core import modifier_io
from ..core.nodegroups import ng_ground_sim as gsim
from ..data import presets as pmod
from ..utils import log


def _active_domain(context):
    obj = context.active_object
    if obj is not None and getattr(obj.groundfx, "is_domain", False):
        return obj
    return None


# Blender keeps no reference to enum items built on the fly, so cache them to
# avoid the strings being garbage-collected mid-menu.
_items_cache = []


def _preset_items(self, context):
    """Only the presets for the active domain's element (B4)."""
    domain = _active_domain(context)
    elem = domain.groundfx.element if domain else None
    _items_cache.clear()
    for p in pmod.all_presets():
        if elem is None or p.element == elem:
            _items_cache.append((p.key, p.label, f"{p.label} preset"))
    if not _items_cache:  # never hand back an empty enum
        _items_cache.append(("NONE", "None", "No preset"))
    return _items_cache


def apply_preset(domain, preset):
    """Set a domain's element + physics from a preset, atomically."""
    st = domain.groundfx
    st.element = preset.element  # swaps element defaults first (E5-S1 callback)
    md = domain.modifiers.get(MODIFIER_NAME)
    if md:
        modifier_io.set_input(md, gsim.IN_REPOSE, preset.repose_rad, tag=False)
        modifier_io.set_input(md, gsim.IN_COHESION, preset.cohesion, tag=False)
        modifier_io.set_input(md, gsim.IN_FLOW, preset.flow_rate, tag=False)
        modifier_io.set_input(md, gsim.IN_BOW_WAVE, preset.bow_wave, tag=False)
        modifier_io.set_input(md, gsim.IN_RECOVERY, preset.recovery, tag=False)
    # Stickiness via the property so the panel slider reflects the preset (its
    # callback pushes IN_STICKINESS). Set after st.element, which reset it to
    # the element default.
    st.stickiness = preset.stickiness
    st.material_height = preset.material_height  # its callback tags + re-solves
    log.info("applied preset %s to %s", preset.key, domain.name)


class GFX_OT_apply_preset(bpy.types.Operator):
    """Apply a ready-made material preset to the active domain"""

    bl_idname = f"{OP_PREFIX}.apply_preset"
    bl_label = "Apply Preset"
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(
        name="Preset", items=_preset_items,
        description="Ready-made material look to apply")

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        apply_preset(domain, pmod.get(self.preset))
        self.report({"INFO"}, f"Applied {pmod.get(self.preset).label}")
        return {"FINISHED"}


classes = (
    GFX_OT_apply_preset,
)
