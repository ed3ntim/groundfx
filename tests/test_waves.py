# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Wave layer on the standing water of mud (issue #8)."""
from __future__ import annotations

import bpy
import numpy as np

import harness

from groundfx.core import modifier_io
from groundfx.core.constants import ELEM_MUD, ELEM_SAND


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _wave(obj):
    me = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    a = me.attributes.get("gfx_wave")
    w = np.zeros(len(me.vertices))
    if a is not None:
        a.data.foreach_get("value", w)
    return w


def _run(element, frames=30, stop=20):
    """A box dug in 3 cm, below the water table, drives and stops."""
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    import bmesh
    obj = create_domain(bpy.context, element, surface=True)
    me = bpy.data.meshes.new("wave_box")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.2)
    bm.to_mesh(me)
    bm.free()
    box = bpy.data.objects.new("wave_box", me)
    bpy.context.scene.collection.objects.link(box)
    ensure_collider_collection(bpy.context, obj).objects.link(box)
    z = obj.groundfx.material_height + 0.1 - 0.03
    scene = bpy.context.scene
    peaks = {}
    for f in range(1, frames + 1):
        box.location = (-0.3 + 0.015 * min(f, stop), 0.0, z)
        scene.frame_set(f)
        if f in (stop, frames):
            peaks[f] = float(np.abs(_wave(obj)).max())
    md = obj.modifiers["GroundFX"]
    waves_in = modifier_io.get_input(md, "Waves")
    for o in (box, obj):
        bpy.data.objects.remove(o, do_unlink=True)
    return peaks, waves_in


def test_moving_box_makes_waves_that_calm_down():
    _reset()
    peaks, waves_in = _run(ELEM_MUD, frames=60, stop=20)
    harness.check("mud domain has the wave layer on", waves_in > 0.0,
                  f"Waves {waves_in}")
    harness.check("a box driving below the water table makes waves",
                  peaks[20] > 5e-4, f"peak {peaks[20] * 1000:.2f} mm")
    harness.check("waves stay small (a few millimetres)",
                  peaks[20] <= 0.0061, f"peak {peaks[20] * 1000:.2f} mm")
    harness.check("waves calm down after the box stops",
                  peaks[60] < 0.6 * peaks[20],
                  f"{peaks[20] * 1000:.2f} -> {peaks[60] * 1000:.2f} mm")


def test_sand_has_no_waves():
    _reset()
    peaks, waves_in = _run(ELEM_SAND, frames=10, stop=10)
    harness.check("sand has no wave layer", waves_in == 0.0 and peaks[10] == 0.0,
                  f"Waves {waves_in}, peak {peaks[10]}")
