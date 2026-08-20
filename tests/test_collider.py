# SPDX-License-Identifier: GPL-3.0-or-later
"""E4-S1 tests: multi-collider carving and the mark/unmark operators.

The headline v1 requirement: several objects carve the material at once. These
tests drive two cubes into one domain and assert that *both* leave a trench,
then exercise the mark/unmark operators that fill the collider collection.
"""
from __future__ import annotations

import bpy

import harness

import math

from groundfx.core.constants import (
    ATTR_HEIGHT, ATTR_CARVE, MODIFIER_NAME, ELEM_SAND, PROP_IS_COLLIDER,
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


def _max_height_band(obj, deps, x0, x1, ymax=0.2):
    """Max material height among grid points with x in [x0,x1], |y| <= ymax."""
    ev = obj.evaluated_get(deps)
    me = ev.data
    hattr = me.attributes.get(ATTR_HEIGHT)
    if hattr is None:
        return None
    best = None
    for v, h in zip(me.vertices, hattr.data):
        x, y, _ = v.co
        if x0 <= x <= x1 and abs(y) <= ymax:
            best = h.value if best is None else max(best, h.value)
    return best


def test_bow_wave_heaps_ahead_of_motion():
    """E4-S3: a collider moving +x heaps more material ahead than behind."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 40

    obj = create_domain(bpy.context, ELEM_SAND)
    coll = obj.groundfx.collider_collection

    cube = _add_cube(0.4, (-0.4, 0.0, 2.0))
    coll.objects.link(cube)

    # Frame 1: cube high above -> clean layer.
    scene.frame_set(1)

    # Drive the cube steadily from x=-0.4 to x=+0.4, pressed into the material.
    steps = 16
    for i in range(steps):
        x = -0.4 + 0.8 * (i / (steps - 1))
        cube.location = (x, 0.0, 0.20)
        scene.frame_set(2 + i)
        deps = bpy.context.evaluated_depsgraph_get()

    # Compare the berm ahead of the final position (+x) with the one behind the
    # start (-x). With a bow wave the leading berm is clearly taller.
    ahead = _max_height_band(obj, deps, 0.62, 0.90)
    behind = _max_height_band(obj, deps, -0.90, -0.62)
    harness.check("berm bands read", ahead is not None and behind is not None)
    if ahead is not None and behind is not None:
        harness.check(
            "bow wave heaps ahead, not behind", ahead > behind + 0.002,
            f"ahead {ahead:.4f} vs behind {behind:.4f}")

    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_proxy_reduces_cost_and_still_carves():
    """E4-S2: a bounding-box proxy raycasts far cheaper yet still carves."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 20

    obj = create_domain(bpy.context, ELEM_SAND)
    coll = obj.groundfx.collider_collection

    # A dense high-poly source sphere.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=48,
                                         radius=0.25, location=(0.0, 0.0, 2.0))
    src = bpy.context.active_object
    src_faces = len(src.data.polygons)

    # Mark it with a bounding-box proxy.
    for o in bpy.context.selected_objects:
        o.select_set(False)
    src.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.groundfx.mark_collider(proxy="BBOX")

    harness.check("original left out of raycast set", src.name not in coll.objects)
    proxies = [o for o in coll.objects if o.groundfx.proxy_source is src]
    harness.check("proxy created", len(proxies) == 1)
    proxy = proxies[0]
    harness.check("proxy hidden from render", proxy.hide_render)

    deps = bpy.context.evaluated_depsgraph_get()
    proxy_faces = len(proxy.evaluated_get(deps).data.polygons)
    # Bounding box is 6 faces vs thousands: the raycast target shrinks hugely.
    harness.check("proxy far cheaper than original",
                  proxy_faces * 20 < src_faces,
                  f"proxy {proxy_faces} faces vs source {src_faces}")

    # The proxy follows the source, so pressing the source in still carves.
    scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    base = _max_height_band(obj, deps, -0.9, 0.9, ymax=0.9)
    for f in range(2, 10):
        src.location = (0.0, 0.0, 0.15)
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
    after = _height_near(obj, deps, 0.0, 0.0, r=0.15)
    harness.check("proxy collider carves a trench", after < base - 0.01,
                  f"min height under proxy {after:.4f} (base ~{base:.4f})")

    for o in (src, proxy, obj):
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)


def _edge_partial_count(obj, deps):
    """(#partial-carve cells, full-carve depth): partial = a cell carved between
    20% and 80% of the full depth — i.e. it sits on an anti-aliased edge."""
    ev = obj.evaluated_get(deps)
    cattr = ev.data.attributes.get(ATTR_CARVE)
    if cattr is None:
        return 0, 0.0
    vals = [d.value for d in cattr.data]
    full = max(vals)
    if full <= 1e-4:
        return 0, 0.0
    partial = sum(1 for c in vals if 0.2 * full < c < 0.8 * full)
    return partial, full


def _carve_edge_partials(hero):
    """Press a 45deg-rotated flat-bottomed cube in; count edge partial cells."""
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 10

    obj = create_domain(bpy.context, ELEM_SAND)
    obj.groundfx.hero_contact = hero  # drives Contact AA 0/1

    # A cube rotated 45deg about Z: its silhouette edges cross the grid
    # diagonally, so a flat underside gives a binary imprint without AA.
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0.0, 0.0, 2.0))
    cube = bpy.context.active_object
    cube.rotation_euler[2] = math.radians(45.0)
    obj.groundfx.collider_collection.objects.link(cube)

    scene.frame_set(1)
    cube.location = (0.0, 0.0, 0.28)  # underside ~0.03, a partial trench
    scene.frame_set(2)
    deps = bpy.context.evaluated_depsgraph_get()
    partial, full = _edge_partial_count(obj, deps)

    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)
    return partial, full


def test_hero_contact_antialiases_silhouette():
    """E4-S4/T16: hero contact resolves the imprint edge below cell size."""
    off_partial, off_full = _carve_edge_partials(hero=False)
    on_partial, on_full = _carve_edge_partials(hero=True)

    harness.check("both imprints carve", off_full > 0.01 and on_full > 0.01,
                  f"full off {off_full:.3f} on {on_full:.3f}")
    # Without AA the diagonal edge is binary (near-zero partial cells); with AA
    # a band of sub-cell-coverage cells appears along the silhouette.
    harness.check("hero contact adds edge gradient", on_partial > off_partial + 8,
                  f"partial cells off {off_partial} vs on {on_partial}")


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
