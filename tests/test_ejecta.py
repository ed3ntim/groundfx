# SPDX-License-Identifier: GPL-3.0-or-later
"""Airborne phase (gen 4): launch, flight, landing, mass balance, display."""
from __future__ import annotations

import bpy
import numpy as np

import harness

from groundfx.core import modifier_io
from groundfx.core.constants import ELEM_SAND, SPRAY_MODIFIER_NAME


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _state(obj):
    """(bed + top volume, airborne volume, parcels in flight, max z)."""
    deps = bpy.context.evaluated_depsgraph_get()
    gs = obj.evaluated_get(deps).evaluated_geometry()
    me = gs.mesh
    n = len(me.vertices)
    h = np.zeros(n)
    top = np.zeros(n)
    me.attributes["gfx_h"].data.foreach_get("value", h)
    me.attributes["gfx_top"].data.foreach_get("value", top)
    side = int(round(n ** 0.5))
    cell = obj.groundfx.domain_size / (side - 1)
    ground = float((h.sum() + top.sum()) * cell * cell)
    pc = gs.pointcloud
    if pc is None or not len(pc.points):
        return ground, 0.0, 0, 0.0
    k = len(pc.points)
    vol = np.zeros(k)
    land = np.zeros(k)
    co = np.zeros(k * 3)
    pc.attributes["gfx_e_vol"].data.foreach_get("value", vol)
    pc.attributes["gfx_e_land"].data.foreach_get("value", land)
    pc.attributes["position"].data.foreach_get("vector", co)
    return (ground, float(vol.sum()), int((land < 0.5).sum()),
            float(co.reshape(-1, 3)[:, 2].max()))


def _run(speed, spray, frames=40, size=6.0):
    """A box ploughs at ``speed`` m/s for half a second, then rests."""
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    import bmesh
    scene = bpy.context.scene
    obj = create_domain(bpy.context, ELEM_SAND, size=size)
    modifier_io.set_input(obj.modifiers["GroundFX"], "Spray", spray)
    me = bpy.data.meshes.new("thrower")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.3)
    bm.to_mesh(me)
    bm.free()
    box = bpy.data.objects.new("thrower", me)
    scene.collection.objects.link(box)
    ensure_collider_collection(bpy.context, obj).objects.link(box)
    fps = scene.render.fps
    z = obj.groundfx.material_height + 0.15 - 0.04
    rows = []
    for f in range(1, frames + 1):
        box.location = (-0.4 + speed / fps * min(f, fps // 2), 0.0, z)
        scene.frame_set(f)
        rows.append(_state(obj))
    return obj, box, rows


def _cleanup(*objs):
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)


def test_fast_contact_throws_material_and_it_comes_back():
    _reset()
    obj, box, rows = _run(speed=1.8, spray=0.85)
    air = [r[1] for r in rows]
    harness.check("fast plough puts material in the air",
                  max(air) > 2e-4, f"peak airborne {max(air) * 1e3:.3f} l")
    harness.check("thrown material rises above the bed",
                  max(r[3] for r in rows) > obj.groundfx.material_height + 0.03,
                  f"max z {max(r[3] for r in rows):.3f} m")
    # 1.8 m/s can lift a grain about 10 cm. Anything far above that started
    # from the top of the bow volume the displacement dumps on the ring.
    harness.check("nothing flies higher than its launch speed allows",
                  max(r[3] for r in rows) < obj.groundfx.material_height + 0.2,
                  f"max z {max(r[3] for r in rows):.3f} m")
    harness.check("everything has landed a second after the stop",
                  rows[-1][2] == 0 and rows[-1][1] < 1e-9,
                  f"{rows[-1][2]} parcels, {rows[-1][1] * 1e3:.4f} l in the air")
    # Nothing may vanish in flight: from the stop on (frame 12) the total of
    # ground and air only changes by what is still being carved (nothing).
    stop = rows[13][0] + rows[13][1]
    end = rows[-1][0] + rows[-1][1]
    harness.check("flight and landing conserve volume",
                  abs(end - stop) < 2e-6 * stop,
                  f"{stop * 1e3:.4f} l -> {end * 1e3:.4f} l")
    start = rows[0][0]
    harness.check("total loss stays within the compaction budget",
                  0.0 <= start - end < 0.1 * 0.3 * 0.04 * 0.9,
                  f"lost {(start - end) * 1e3:.3f} l")
    _cleanup(box, obj)


def test_slow_contact_and_zero_spray_stay_in_the_bed():
    _reset()
    obj, box, rows = _run(speed=0.2, spray=0.85, frames=16)
    harness.check("slow plough throws nothing",
                  max(r[1] for r in rows) == 0.0,
                  f"peak airborne {max(r[1] for r in rows) * 1e3:.4f} l")
    _cleanup(box, obj)
    obj, box, rows = _run(speed=1.8, spray=0.0, frames=16)
    harness.check("spray 0 throws nothing even when fast",
                  max(r[1] for r in rows) == 0.0,
                  f"peak airborne {max(r[1] for r in rows) * 1e3:.4f} l")
    _cleanup(box, obj)


def test_spray_stage_follows_the_property():
    _reset()
    from groundfx.ops.op_add import create_domain
    bare = create_domain(bpy.context, ELEM_SAND)
    harness.check("bare domain has no spray",
                  bare.groundfx.spray == 0.0
                  and bare.modifiers.get(SPRAY_MODIFIER_NAME) is None)
    full = create_domain(bpy.context, ELEM_SAND, surface=True)
    names = [m.name for m in full.modifiers]
    harness.check("full sand domain has the spray stage last",
                  full.groundfx.spray > 0.0
                  and names[-1] == SPRAY_MODIFIER_NAME, str(names))
    harness.check("solver got the spray amount",
                  abs(modifier_io.get_input(full.modifiers["GroundFX"],
                                            "Spray", 0.0)
                      - full.groundfx.spray) < 1e-6)
    full.groundfx.spray = 0.0
    harness.check("spray 0 removes the stage",
                  full.modifiers.get(SPRAY_MODIFIER_NAME) is None)
    full.groundfx.spray = 0.5
    full.groundfx.element = "MUD"
    harness.check("mud has no spray stage yet",
                  full.modifiers.get(SPRAY_MODIFIER_NAME) is None
                  and modifier_io.get_input(full.modifiers["GroundFX"],
                                            "Spray", 1.0) == 0.0)
    _cleanup(bare, full)


def test_spray_stage_draws_grains_with_velocity():
    _reset()
    from groundfx.ops.op_spray import sync_spray
    obj, box, rows = _run(speed=1.8, spray=0.85, frames=8, size=2.0)
    obj.groundfx.spray = 0.85
    sync_spray(obj)
    md = obj.modifiers[SPRAY_MODIFIER_NAME]
    modifier_io.set_input(md, "Viewport Detail", 0.2)
    bpy.context.scene.frame_set(9)
    deps = bpy.context.evaluated_depsgraph_get()
    gs = obj.evaluated_get(deps).evaluated_geometry()  # keeps pc alive
    pc = gs.pointcloud
    count = len(pc.points) if pc is not None else 0
    harness.check("spray stage turns parcels into many grains",
                  count > 5 * max(1, rows[-1][2]),
                  f"{count} grains from {rows[-1][2]} parcels")
    names = set(pc.attributes.keys()) if pc is not None else set()
    harness.check("grains carry velocity for motion blur and a mineral id",
                  {"velocity", "gfx_grain_id"} <= names, str(sorted(names)))
    harness.check("solver attributes are stripped from the grains",
                  not any(n.startswith("gfx_e_") for n in names),
                  str(sorted(names)))
    _cleanup(box, obj)
