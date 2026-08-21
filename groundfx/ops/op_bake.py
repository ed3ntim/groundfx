# SPDX-License-Identifier: GPL-3.0-or-later
"""Bake and free the simulation cache (E7-S1).

The solver is a Simulation Zone, so Blender's simulation-nodes cache bakes it:
once baked, playback is real-time and the frozen-in result survives scrubbing;
Free returns to the live solve. All the version-specific operator wiring lives
in ``utils/compat`` — these operators just pick the target objects and report.
"""
from __future__ import annotations

import bpy

from ..core.constants import OP_PREFIX, MODIFIER_NAME
from ..utils import compat

# The simulation cache stores, per baked frame, the point positions plus the
# gfx_* state attributes the solver carries. Roughly 15 floats/vertex:
# position (3) + h/base/carve/carve_prev/occ/occ_prev/pile/comp/age (9) +
# flow (3). Four bytes each — an estimate for the panel, not an exact figure.
_BYTES_PER_VERTEX = 15 * 4


def bake_estimate_mb(obj, scene) -> tuple[float, int, int]:
    """Rough megabytes a full bake would cost, plus (frames, vertices)."""
    verts = len(obj.data.vertices) if obj.data else 0
    frames = max(0, scene.frame_end - scene.frame_start + 1)
    mb = verts * frames * _BYTES_PER_VERTEX / (1024.0 * 1024.0)
    return mb, frames, verts


def _is_domain(obj) -> bool:
    return getattr(obj.groundfx, "is_domain", False) and \
        obj.modifiers.get(MODIFIER_NAME) is not None


def _active_domain(context):
    obj = context.active_object
    return obj if obj is not None and _is_domain(obj) else None


def _all_domains(context):
    return [o for o in context.scene.objects if _is_domain(o)]


class GFX_OT_bake(bpy.types.Operator):
    """Bake the active domain's simulation for real-time playback"""

    bl_idname = f"{OP_PREFIX}.bake"
    bl_label = "Bake"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        if compat.bake_geometry_nodes([domain]):
            self.report({"INFO"}, f"Baked {domain.name}")
            return {"FINISHED"}
        self.report({"ERROR"}, "Bake failed")
        return {"CANCELLED"}


class GFX_OT_bake_all(bpy.types.Operator):
    """Bake every GroundFX domain in the scene"""

    bl_idname = f"{OP_PREFIX}.bake_all"
    bl_label = "Bake All"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return bool(_all_domains(context))

    def execute(self, context):
        domains = _all_domains(context)
        if compat.bake_geometry_nodes(domains):
            self.report({"INFO"}, f"Baked {len(domains)} domain(s)")
            return {"FINISHED"}
        self.report({"ERROR"}, "Bake failed")
        return {"CANCELLED"}


class GFX_OT_free(bpy.types.Operator):
    """Free the active domain's baked cache and return to the live solve"""

    bl_idname = f"{OP_PREFIX}.free"
    bl_label = "Free"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _active_domain(context) is not None

    def execute(self, context):
        domain = _active_domain(context)
        if compat.free_geometry_nodes([domain]):
            self.report({"INFO"}, f"Freed {domain.name}")
            return {"FINISHED"}
        self.report({"ERROR"}, "Free failed")
        return {"CANCELLED"}


class GFX_OT_free_all(bpy.types.Operator):
    """Free every GroundFX domain's baked cache"""

    bl_idname = f"{OP_PREFIX}.free_all"
    bl_label = "Free All"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return bool(_all_domains(context))

    def execute(self, context):
        domains = _all_domains(context)
        if compat.free_geometry_nodes(domains):
            self.report({"INFO"}, f"Freed {len(domains)} domain(s)")
            return {"FINISHED"}
        self.report({"ERROR"}, "Free failed")
        return {"CANCELLED"}


classes = (
    GFX_OT_bake,
    GFX_OT_bake_all,
    GFX_OT_free,
    GFX_OT_free_all,
)
