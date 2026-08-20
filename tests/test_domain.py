# SPDX-License-Identifier: GPL-3.0-or-later
"""E2 + M1 tests: domain creation and the minimal carve.

The carve test is the M1 acceptance criterion: a collider lowered into the
material leaves a measurable trench in the height attribute.
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import (
    ATTR_HEIGHT, ATTR_CARVE, MODIFIER_NAME, COLLECTION_NAME,
    ELEM_SAND, QUALITY_LOW,
)


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_create_domain():
    _reset()
    from groundfx.ops.op_add import create_domain
    obj = create_domain(bpy.context, ELEM_SAND)
    harness.check("domain is_domain flag", obj.groundfx.is_domain)
    harness.check("has modifier", obj.modifiers.get(MODIFIER_NAME) is not None)
    harness.check("has node group",
                  obj.modifiers[MODIFIER_NAME].node_group is not None)
    harness.check("in GroundFX collection",
                  COLLECTION_NAME in [c.name for c in obj.users_collection])
    bpy.data.objects.remove(obj, do_unlink=True)


def _read_height_stats(obj, deps):
    ev = obj.evaluated_get(deps)
    attr = ev.data.attributes.get(ATTR_HEIGHT)
    if attr is None:
        return None
    vals = [d.value for d in attr.data]
    return min(vals), max(vals), sum(vals) / len(vals)


def test_minimal_carve():
    """M1: a collider pressed into the material carves a visible trench."""
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.core import modifier_io
    from groundfx.core.nodegroups import ng_ground_sim as gsim

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 20

    # Use LOW quality (64^2) for a fast test; 2 m domain, 8 cm material.
    obj = create_domain(bpy.context, ELEM_SAND)
    obj.groundfx.quality = QUALITY_LOW  # visual only; grid already built
    md = obj.modifiers[MODIFIER_NAME]

    # A 0.4 m cube collider; its underside sits 0.2 m below its origin.
    bpy.ops.mesh.primitive_cube_add(size=0.4)
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)

    # Baseline: place the collider high ABOVE the material *before* stepping
    # frame 1, so the simulation initialises to a clean 0.08 m layer. (The sim
    # caches per frame, so the collider position must be set before the step.)
    cube.location = (0.0, 0.0, 2.0)
    scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    base = _read_height_stats(obj, deps)
    harness.check("baseline height read", base is not None)

    # Lower the cube so its underside (z - 0.2) reaches ~0.04 m: a partial
    # trench that leaves some material, rather than scraping to the base.
    for f in range(2, 9):
        cube.location = (0.0, 0.0, 0.24)
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()

    after = _read_height_stats(obj, deps)
    harness.check("carved height read", after is not None)
    if base and after:
        # Minimum height should have dropped where the cube pressed in.
        harness.check(
            "trench carved",
            after[0] < base[0] - 0.01,
            f"min height {base[0]:.4f} -> {after[0]:.4f} (expected drop)",
        )
        # Some points remain untouched at full height (cube is local).
        harness.check(
            "untouched material remains",
            after[1] > 0.05,
            f"max height {after[1]:.4f} (expected ~0.08 away from cube)",
        )

    bpy.data.objects.remove(cube, do_unlink=True)
    bpy.data.objects.remove(obj, do_unlink=True)


def test_piling_forms_berm():
    """E3-S3: carved material heaps into a berm above the original surface."""
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.core import modifier_io
    from groundfx.core.nodegroups import ng_ground_sim as gsim

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 20

    obj = create_domain(bpy.context, ELEM_SAND)
    md = obj.modifiers[MODIFIER_NAME]

    bpy.ops.mesh.primitive_cube_add(size=0.4)
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)

    cube.location = (0.0, 0.0, 2.0)
    scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    base = _read_height_stats(obj, deps)

    # Press the cube into the material.
    for f in range(2, 12):
        cube.location = (0.0, 0.0, 0.20)
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
    after = _read_height_stats(obj, deps)

    if base and after:
        # A berm rises above the original flat surface (~0.08 m).
        harness.check(
            "berm above original surface",
            after[1] > base[1] + 0.003,
            f"max height {base[1]:.4f} -> {after[1]:.4f} (expected rise)",
        )
        # And a trench below it.
        harness.check(
            "trench below berm",
            after[0] < base[0] - 0.01,
            f"min height {base[0]:.4f} -> {after[0]:.4f}",
        )

    bpy.data.objects.remove(cube, do_unlink=True)
    bpy.data.objects.remove(obj, do_unlink=True)
