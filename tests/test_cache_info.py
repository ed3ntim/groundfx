# SPDX-License-Identifier: GPL-3.0-or-later
"""E7-S2: the bake-cost estimate scales with frames, verts and quality."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ELEM_SAND, QUALITY_LOW, QUALITY_HIGH


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_bake_estimate_scales():
    _reset()
    from groundfx.ops.op_add import create_domain, rebuild_grid
    from groundfx.ops.op_bake import bake_estimate_mb

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 100
    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj

    mb1, frames1, verts1 = bake_estimate_mb(obj, scene)
    harness.check("estimate positive", mb1 > 0.0, f"{mb1}")
    harness.check("frame count read", frames1 == 100, f"{frames1}")

    # More frames -> proportionally more memory.
    scene.frame_end = 200
    mb2, frames2, _ = bake_estimate_mb(obj, scene)
    harness.check("doubling frames ~doubles the estimate",
                  abs(mb2 - 2.0 * mb1) < 0.01 * mb1, f"{mb1} -> {mb2}")

    # Higher quality (more verts) -> more memory.
    scene.frame_end = 100
    obj.groundfx.quality = QUALITY_HIGH
    rebuild_grid(obj)
    mb3, _, verts3 = bake_estimate_mb(obj, scene)
    harness.check("higher quality costs more", mb3 > mb1 and verts3 > verts1,
                  f"verts {verts1} -> {verts3}, MB {mb1:.0f} -> {mb3:.0f}")
    bpy.data.objects.remove(obj, do_unlink=True)
