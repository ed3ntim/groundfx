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
    st.material_height = preset.material_height  # its callback tags + re-solves
    log.info("applied preset %s to %s", preset.key, domain.name)


class GFX_OT_apply_preset(bpy.types.Operator):
    """Apply a ready-made material preset to the active domain"""

    bl_idname = f"{OP_PREFIX}.apply_preset"
    bl_label = "Apply Preset"
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(
        name="Preset",
        items=[(p.key, p.label, f"{p.label} preset") for p in pmod.all_presets()],
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
