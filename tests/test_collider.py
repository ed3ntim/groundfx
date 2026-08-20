# SPDX-License-Identifier: GPL-3.0-or-later
"""E4-S1 tests: multi-collider carving and the mark/unmark operators.

The headline v1 requirement: several objects carve the material at once. These
tests drive two cubes into one domain and assert that *both* leave a trench,
then exercise the mark/unmark operators that fill the collider collection.
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import (
    ATTR_HEIGHT, MODIFIER_NAME, ELEM_SAND, PROP_IS_COLLIDER,
)


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _height_near(obj, deps, cx, cy, r=0.15):
    """Minimum material height among grid points within r of (cx, cy)."""
    ev = obj.evaluated_get(deps)
    me = ev.data
    hattr = me.attributes.get(ATTR_HEIGHT)
    if hattr is None:
        return None
    vals = []
    r2 = r * r
    for v, h in zip(me.vertices, hattr.data):
        x, y, _ = v.co
        if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
            vals.append(h.value)
    return min(vals) if vals else None


def _add_cube(size, location):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    return bpy.context.active_object


def test_two_colliders_carve_simultaneously():
    """Two cubes at different XY each carve their own trench in one frame set."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 20

    obj = create_domain(bpy.context, ELEM_SAND)
    coll = obj.groundfx.collider_collection
    harness.check("collider collection auto-created", coll is not None)

    # Two 0.4 m cubes, undersides 0.2 m below their origin, at x = -0.5 / +0.5.
    c1 = _add_cube(0.4, (-0.5, 0.0, 2.0))
    c2 = _add_cube(0.4, (0.5, 0.0, 2.0))
    coll.objects.link(c1)
    coll.objects.link(c2)

    # Frame 1: both high above -> clean 0.08 m layer.
    scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    base1 = _height_near(obj, deps, -0.5, 0.0)
    base2 = _height_near(obj, deps, 0.5, 0.0)
    harness.check("baseline under both spots read",
                  base1 is not None and base2 is not None)

    # Press both cubes in.
    for f in range(2, 10):
        c1.location = (-0.5, 0.0, 0.20)
        c2.location = (0.5, 0.0, 0.20)
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()

    a1 = _height_near(obj, deps, -0.5, 0.0)
    a2 = _height_near(obj, deps, 0.5, 0.0)
    corner = _height_near(obj, deps, -0.9, -0.9, r=0.1)

    harness.check("collider 1 carved a trench", a1 < base1 - 0.01,
                  f"h at (-0.5,0): {base1:.4f} -> {a1:.4f}")
    harness.check("collider 2 carved a trench", a2 < base2 - 0.01,
                  f"h at (0.5,0): {base2:.4f} -> {a2:.4f}")
    harness.check("far corner untouched", corner is None or corner > 0.05,
                  f"corner height {corner}")

    for o in (c1, c2, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_mark_and_unmark_operators():
    """The mark op fills the collection; unmark removes the active row."""
    _reset()
    from groundfx.ops.op_add import create_domain

    obj = create_domain(bpy.context, ELEM_SAND)
    coll = obj.groundfx.collider_collection

    c1 = _add_cube(0.4, (-0.5, 0.0, 1.0))
    c2 = _add_cube(0.4, (0.5, 0.0, 1.0))

    # Select both cubes, make the domain active, then mark.
    for o in bpy.context.selected_objects:
        o.select_set(False)
    c1.select_set(True)
    c2.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.groundfx.mark_collider()

    names = {o.name for o in coll.objects}
    harness.check("both cubes marked", c1.name in names and c2.name in names,
                  f"collection: {names}")
    harness.check("collider flag set",
                  c1.groundfx.is_collider and PROP_IS_COLLIDER in c1)

    # Remove the active row (index 0).
    obj.groundfx.collider_active = 0
    bpy.ops.groundfx.unmark_collider()
    harness.check("one collider removed", len(coll.objects) == 1,
                  f"remaining {len(coll.objects)}")

    for o in (c1, c2, obj):
        bpy.data.objects.remove(o, do_unlink=True)
