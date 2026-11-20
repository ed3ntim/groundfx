# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Displaced material never lands under an overhang of the collider.

A weapon lying in mud covers many cells it does not touch (under the stock,
the barrel). Those cells were part of the ring the carved volume is pushed
to, but material under a collider is never relaxed: the volume of a whole
footprint piled up there into thin towers metres high.
"""
from __future__ import annotations

import bmesh
import bpy
import numpy as np

import harness

from groundfx.core.constants import ELEM_MUD


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _attr(me, name):
    a = me.attributes.get(name)
    v = np.zeros(len(me.vertices))
    if a is not None:
        a.data.foreach_get("value", v)
    return v


def _table():
    """A plate 1 cm above the ground with a small block under its middle
    that digs 3 cm into the material."""
    me = bpy.data.meshes.new("overhang")
    bm = bmesh.new()
    plate = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(0.26, 0.26, 0.02), verts=plate)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.05), verts=plate)
    block = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(0.06, 0.06, 0.08), verts=block)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new("overhang", me)


def test_no_material_piles_under_an_overhang():
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    obj = create_domain(bpy.context, ELEM_MUD, surface=False)
    h0 = obj.groundfx.material_height
    tab = _table()
    bpy.context.scene.collection.objects.link(tab)
    ensure_collider_collection(bpy.context, obj).objects.link(tab)
    # block bottom 3 cm below the surface, plate bottom 1 cm above it
    z = h0 + 0.04 - 0.03
    scene = bpy.context.scene
    worst = 0.0
    for f in range(1, 13):
        tab.location = (-0.05 + 0.01 * f, 0.0, z)
        scene.frame_set(f)
        me = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        h = _attr(me, "gfx_h")
        under = (_attr(me, "gfx_cov") > 0.5) & (_attr(me, "gfx_occ") < 0.5)
        if under.any():
            worst = max(worst, float(h[under].max()) - h0)
    for o in (tab, obj):
        bpy.data.objects.remove(o, do_unlink=True)
    harness.check("nothing piles up in the cells under the plate",
                  worst < 0.01, f"highest {worst * 1000:.1f} mm above rest")
