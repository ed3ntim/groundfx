# SPDX-License-Identifier: GPL-3.0-or-later
"""Solver v2 physics: mass, angle of repose, rest state, plough behaviour."""
from __future__ import annotations

import math

import bpy
import numpy as np

import harness

from groundfx.core import modifier_io
from groundfx.core.constants import ATTR_HEIGHT, ATTR_BASE, ELEM_SAND


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _heights(obj):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.data
    n = len(me.vertices)
    out = {}
    for name in (ATTR_HEIGHT, ATTR_BASE):
        a = np.zeros(n, dtype=np.float64)
        me.attributes[name].data.foreach_get("value", a)
        out[name] = a
    side = int(round(math.sqrt(n)))
    return out[ATTR_HEIGHT].reshape(side, side), out[ATTR_BASE].reshape(side, side)


def _domain_with_spike(height=0.3, radius=0.12):
    from groundfx.ops.op_add import create_domain
    obj = create_domain(bpy.context, ELEM_SAND)
    md = obj.modifiers["GroundFX"]
    modifier_io.set_input(md, "Material Height", 0.0)
    me = obj.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    r = np.hypot(co[:, 0], co[:, 1])
    a = me.attributes.new("gfx_init", "FLOAT", "POINT")
    a.data.foreach_set("value", np.where(r < radius, height, 0.0))
    return obj


def test_relaxation_conserves_mass_and_reaches_repose():
    _reset()
    obj = _domain_with_spike()
    scene = bpy.context.scene
    scene.frame_set(1)
    h0, _ = _heights(obj)
    for f in range(2, 90):
        scene.frame_set(f)
    h1, _ = _heights(obj)
    harness.check("relaxation conserves mass",
                  abs(h1.sum() - h0.sum()) < 1e-4 * h0.sum(),
                  f"{h0.sum():.6f} -> {h1.sum():.6f}")
    cell = obj.groundfx.domain_size / (h1.shape[0] - 1)
    gy, gx = np.gradient(h1, cell)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    flank = slope[(h1 > 0.01) & (h1 < 0.8 * h1.max())]
    p90 = float(np.percentile(flank, 90)) if flank.size else 0.0
    harness.check("heap settles near the 34 deg angle of repose",
                  28.0 <= p90 <= 40.0, f"p90 slope {p90:.1f} deg")

    # Rest state: no creep once settled.
    for f in range(90, 100):
        scene.frame_set(f)
    h2, _ = _heights(obj)
    creep = float(np.abs(h2 - h1).max())
    harness.check("settled heap does not creep", creep < 2e-4,
                  f"max |dh| over 10 frames {creep * 1000:.3f} mm")
    bpy.data.objects.remove(obj, do_unlink=True)


def _plough(stop_frame=30, frames=50):
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    import bmesh
    obj = create_domain(bpy.context, ELEM_SAND)
    me = bpy.data.meshes.new("plough")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.3)
    bm.to_mesh(me)
    bm.free()
    box = bpy.data.objects.new("plough", me)
    bpy.context.scene.collection.objects.link(box)
    ensure_collider_collection(bpy.context, obj).objects.link(box)
    scene = bpy.context.scene
    h = obj.groundfx.material_height
    z = h + 0.15 - 0.04
    snaps = {}
    for f in range(1, frames + 1):
        x = -0.6 + 0.02 * min(f, stop_frame)
        box.location = (x, 0.0, z)
        scene.frame_set(f)
        if f in (1, stop_frame, frames):
            snaps[f] = _heights(obj)[0].copy()
    return obj, box, snaps


def test_plough_conserves_mass_and_piles_ahead():
    _reset()
    obj, box, snaps = _plough()
    n = snaps[1].shape[0]
    h_first, h_stop, h_end = snaps[1], snaps[30], snaps[50]
    ratio = obj.modifiers["GroundFX"]
    # Only (1 - displacement ratio) of the carved volume may vanish.
    harness.check("plough mass within compaction budget",
                  h_end.sum() > 0.97 * h_first.sum() and
                  h_end.sum() <= h_first.sum() * 1.0001,
                  f"{h_first.sum():.3f} -> {h_end.sum():.3f}")
    # x index of the box front at the stop: box centre -0.6+0.6=0, front +0.15
    size = obj.groundfx.domain_size
    col = lambda x: int(round((x / size + 0.5) * (n - 1)))  # noqa: E731
    mid = n // 2
    rest = obj.groundfx.material_height
    ahead = h_end[mid, col(0.17):col(0.30)].max()
    behind = h_end[mid, col(-0.45):col(-0.25)].mean()
    harness.check("material piled up ahead of the stopped box",
                  ahead > rest + 0.02, f"ahead max {ahead:.3f} m")
    harness.check("trench left behind the box", behind < rest - 0.02,
                  f"behind mean {behind:.3f} m")
    drift = float(np.abs(h_end - h_stop).max())
    harness.check("pile stays once the box has stopped (no sliding away)",
                  float(h_end[mid, col(0.17):col(0.30)].max()) > rest + 0.02,
                  f"max change after stop {drift:.3f}")
    for o in (box, obj):
        bpy.data.objects.remove(o, do_unlink=True)
