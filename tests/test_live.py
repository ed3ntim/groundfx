# SPDX-License-Identifier: GPL-3.0-or-later
"""Point 3 acceptance: Live Sculpt draws a trace from dragging, no Play needed.

The interactive part (a modal timer, a window, mouse drags) can't run headless,
so these tests drive the piece that carries the logic — ``LiveStepper`` — and
assert the contract the modal relies on:

* a collider that *moved* advances the simulation one frame and deepens the
  material underneath it — i.e. dragging leaves an accumulating trace, exactly
  as a baked animation would;
* a collider that *didn't* move advances nothing (no phantom stepping, so the
  playhead and the field only move when the user actually sculpts);
* the frame range opens ahead of the step, so the sim never stalls at frame_end.
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ATTR_HEIGHT, ELEM_SAND, MODIFIER_NAME
from groundfx.ops.op_live import LiveStepper


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _min_height_near(obj, deps, cx, cy, r=0.2):
    ev = obj.evaluated_get(deps)
    me = ev.data
    hattr = me.attributes.get(ATTR_HEIGHT)
    if hattr is None:
        return None
    r2 = r * r
    vals = [h.value for v, h in zip(me.vertices, hattr.data)
            if (v.co.x - cx) ** 2 + (v.co.y - cy) ** 2 <= r2]
    return min(vals) if vals else None


def _setup():
    from groundfx.ops.op_add import create_domain
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 5
    scene.frame_set(1)
    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(0.0, 0.0, 2.0))
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)
    bpy.context.view_layer.update()
    return scene, obj, cube


def test_drag_steps_and_leaves_a_trace():
    _reset()
    scene, obj, cube = _setup()
    stepper = LiveStepper()
    stepper.snapshot(bpy.context)

    deps = bpy.context.evaluated_depsgraph_get()
    base = _min_height_near(obj, deps, 0.0, 0.0)
    f0 = scene.frame_current

    # Drag the cube down into the sand and let the stepper react, as the modal
    # timer would on each viewport update.
    cube.location = (0.0, 0.0, 0.18)
    bpy.context.view_layer.update()
    stepped = stepper.advance_if_moved(bpy.context)

    harness.check("a moved collider stepped the sim", stepped)
    harness.check("frame advanced by one", scene.frame_current == f0 + 1,
                  f"{f0} -> {scene.frame_current}")
    deps = bpy.context.evaluated_depsgraph_get()
    after = _min_height_near(obj, deps, 0.0, 0.0)
    harness.check("drag left a trace (material pushed down)",
                  base is not None and after is not None and after < base - 0.01,
                  f"h {base} -> {after}")

    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_still_collider_does_not_step():
    _reset()
    scene, obj, cube = _setup()
    stepper = LiveStepper()
    stepper.snapshot(bpy.context)
    f0 = scene.frame_current

    # No movement between snapshot and the tick.
    stepped = stepper.advance_if_moved(bpy.context)
    harness.check("a still collider does not step", not stepped)
    harness.check("frame unchanged", scene.frame_current == f0,
                  f"{f0} -> {scene.frame_current}")

    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_frame_range_opens_ahead():
    _reset()
    scene, obj, cube = _setup()
    scene.frame_set(scene.frame_end)  # sit exactly on the last frame
    stepper = LiveStepper()
    stepper.snapshot(bpy.context)
    end0 = scene.frame_end

    cube.location = (0.1, 0.0, 0.18)
    bpy.context.view_layer.update()
    stepper.advance_if_moved(bpy.context)

    harness.check("frame end extended so the sim can step on",
                  scene.frame_end > end0 and scene.frame_current <= scene.frame_end,
                  f"end {end0} -> {scene.frame_end}, cur {scene.frame_current}")

    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)
