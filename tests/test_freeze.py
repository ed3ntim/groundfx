# SPDX-License-Identifier: GPL-3.0-or-later
"""E7 tests: freeze-to-mesh and the settle & freeze hero workflow."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import (
    ATTR_HEIGHT, MODIFIER_NAME, ELEM_SAND, QUALITY_LOW,
)


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _press_collider(scene, obj, frames):
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(0.0, 0.0, 2.0))
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)
    scene.frame_set(1)
    for f in range(2, frames + 1):
        cube.location = (0.0, 0.0, 0.20)
        scene.frame_set(f)
    return cube


def test_freeze_to_mesh():
    """E7-S3: the current frame becomes a static mesh with attributes kept."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 30

    obj = create_domain(bpy.context, ELEM_SAND)
    cube = _press_collider(scene, obj, 7)
    bpy.context.view_layer.objects.active = obj

    n_before = len(bpy.data.objects)
    bpy.ops.groundfx.freeze_to_mesh()
    frozen = bpy.context.view_layer.objects.active

    harness.check("new object created", len(bpy.data.objects) == n_before + 1)
    harness.check("frozen name", frozen.name.endswith("_Frozen"))
    harness.check("frozen is static (no modifier)", len(frozen.modifiers) == 0)
    harness.check("frozen keeps gfx_h",
                  frozen.data.attributes.get(ATTR_HEIGHT) is not None)
    harness.check("frozen not a domain",
                  not getattr(frozen.groundfx, "is_domain", False))
    zs = [v.co.z for v in frozen.data.vertices]
    harness.check("frozen surface displaced", max(zs) - min(zs) > 0.005,
                  f"z range {min(zs):.4f}..{max(zs):.4f}")
    harness.check("live domain hidden from render", obj.hide_render)

    bpy.data.objects.remove(cube, do_unlink=True)


def test_settle_and_freeze():
    """E7-S4: play forward to rest, then auto-freeze."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 120

    obj = create_domain(bpy.context, ELEM_SAND)
    cube = _press_collider(scene, obj, 7)
    # Lift the collider away so the disturbed surface can actually come to rest
    # (a held collider keeps churning its contact edge -- see E7-T14/B2).
    cube.location = (0.0, 0.0, 5.0)
    bpy.context.view_layer.objects.active = obj

    n_before = len(bpy.data.objects)
    bpy.ops.groundfx.settle_and_freeze(threshold=1e-3, max_frames=80)
    frozen = bpy.context.view_layer.objects.active

    harness.check("settle produced a frozen mesh",
                  len(bpy.data.objects) == n_before + 1
                  and frozen.name.endswith("_Frozen"))
    harness.check("settle stopped before the max",
                  scene.frame_current < 7 + 80,
                  f"stopped at frame {scene.frame_current}")

    bpy.data.objects.remove(cube, do_unlink=True)


def test_bake_and_free():
    """E7-S1: bake and free the simulation cache without error."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 12

    obj = create_domain(bpy.context, ELEM_SAND)
    cube = _press_collider(scene, obj, 6)
    bpy.context.view_layer.objects.active = obj

    r = bpy.ops.groundfx.bake()
    harness.check("bake finished", r == {"FINISHED"}, f"{r}")
    r = bpy.ops.groundfx.free()
    harness.check("free finished", r == {"FINISHED"}, f"{r}")
    r = bpy.ops.groundfx.bake_all()
    harness.check("bake all finished", r == {"FINISHED"}, f"{r}")
    r = bpy.ops.groundfx.free_all()
    harness.check("free all finished", r == {"FINISHED"}, f"{r}")

    bpy.data.objects.remove(cube, do_unlink=True)


def test_photo_setup():
    """E7-T11: photo setup turns on hero contact and Cycles."""
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.core import modifier_io

    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.groundfx.photo_setup()

    harness.check("hero contact enabled", obj.groundfx.hero_contact)
    harness.check("engine is Cycles",
                  bpy.context.scene.render.engine == "CYCLES")
    md = obj.modifiers[MODIFIER_NAME]
    from groundfx.core.nodegroups import ng_ground_sim as gsim
    harness.check("relax iterations raised",
                  modifier_io.get_input(md, gsim.IN_RELAX_ITERS) >= 16)
