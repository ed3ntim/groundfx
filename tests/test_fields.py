# SPDX-License-Identifier: GPL-3.0-or-later
"""E3-S4 acceptance: the shader-facing physics fields behave.

The solver now emits three fields the material reads. None feed back into the
height solve, so these tests just assert they carry the right signal:

* ``gfx_comp`` builds up under a collider and then *fades* once the spot is left
  alone — tracks recover over time instead of being permanent (E3-T15);
* ``gfx_age`` reads zero under the collider and counts up on undisturbed ground
  (E3-T18);
* ``gfx_flow`` records the unit direction the collider moved, so a straight
  drag along +x leaves a track whose flow points +x (E3-T17).
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import (
    ATTR_COMP, ATTR_AGE, ATTR_FLOW, ELEM_SAND,
)


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _attr(obj, name):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return ev.data.attributes.get(name)


def _floats(obj, name):
    a = _attr(obj, name)
    return [d.value for d in a.data] if a else None


def _setup_and_drag():
    from groundfx.ops.op_add import create_domain
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 60
    scene.frame_set(1)
    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(-0.6, 0.0, 2.0))
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)
    scene.frame_set(1)
    for k in range(16):  # drag +x, pressed in
        cube.location = (-0.6 + 0.05 * k, 0.0, 0.20)
        scene.frame_set(2 + k)
    return scene, obj, cube


def test_compaction_recovers_over_time():
    _reset()
    scene, obj, cube = _setup_and_drag()
    during = max(_floats(obj, ATTR_COMP))
    harness.check("compaction built up under the drag", during > 0.01,
                  f"max comp {during:.4f}")
    # Lift the collider and let it sit: compaction must fade (recovery > 0).
    cube.location = (0.0, 0.0, 5.0)
    for f in range(18, 50):
        scene.frame_set(f)
    after = max(_floats(obj, ATTR_COMP))
    harness.check("compaction recovered once undisturbed", after < during * 0.5,
                  f"comp {during:.4f} -> {after:.4f}")
    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_age_zero_under_collider_grows_elsewhere():
    _reset()
    scene, obj, cube = _setup_and_drag()
    age = _floats(obj, ATTR_AGE)
    harness.check("some cell freshly disturbed (age 0)", min(age) == 0.0,
                  f"min age {min(age)}")
    harness.check("undisturbed ground has aged", max(age) > 5.0,
                  f"max age {max(age)}")
    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_flow_points_along_the_drag():
    _reset()
    scene, obj, cube = _setup_and_drag()
    a = _attr(obj, ATTR_FLOW)
    harness.check("gfx_flow exists", a is not None)
    if a is not None:
        # The strongest-flow cell (a track cell) should point clearly +x.
        best = max((d.vector for d in a.data),
                   key=lambda v: v[0] * v[0] + v[1] * v[1])
        harness.check("flow points along +x drag",
                      best[0] > 0.7 and abs(best[1]) < 0.4,
                      f"flow dir ({best[0]:.2f}, {best[1]:.2f})")
    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)
