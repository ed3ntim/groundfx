# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe the airborne phase: parcel counts, volumes and mass balance.

Run::

    blender -b --factory-startup --python dev/probe_ejecta.py -- \
        [--speed 1.5] [--spray 0.85] [--quality MEDIUM] [--frames 60]

A box ploughs at ``speed`` m/s for half a second and stops. Prints per frame
the bed, top-layer and airborne volume (litres), their sum and the solver
time, so launch, flight and landing can be checked in numbers.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import bpy
import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--speed", type=float, default=1.5)
    p.add_argument("--spray", type=float, default=0.85)
    p.add_argument("--quality", default="MEDIUM")
    p.add_argument("--frames", type=int, default=60)
    p.add_argument("--size", type=float, default=2.0)
    return p.parse_args(argv)


def volumes(obj):
    """(bed, top, airborne, parcels in flight, parcels total) in m^3 / counts."""
    deps = bpy.context.evaluated_depsgraph_get()
    gs = obj.evaluated_get(deps).evaluated_geometry()
    me = gs.mesh
    n = len(me.vertices)
    h = np.zeros(n)
    me.attributes["gfx_h"].data.foreach_get("value", h)
    top = np.zeros(n)
    me.attributes["gfx_top"].data.foreach_get("value", top)
    side = int(round(n ** 0.5))
    cell = obj.groundfx.domain_size / (side - 1)
    pc = gs.pointcloud
    air, flying, total = 0.0, 0, 0
    zmax = 0.0
    if pc is not None and len(pc.points):
        total = len(pc.points)
        vol = np.zeros(total)
        pc.attributes["gfx_e_vol"].data.foreach_get("value", vol)
        land = np.zeros(total)
        pc.attributes["gfx_e_land"].data.foreach_get("value", land)
        co = np.zeros(total * 3)
        pc.attributes["position"].data.foreach_get("vector", co)
        air = float(vol.sum())
        flying = int((land < 0.5).sum())
        co = co.reshape(-1, 3)
        zmax = float(co[:, 2].max())
        half = obj.groundfx.domain_size * 0.5
        out = (np.abs(co[:, 0]) > half) | (np.abs(co[:, 1]) > half)
        volumes.left += float(vol[out & (land < 0.5)].sum())
    return h.sum() * cell * cell, top.sum() * cell * cell, air, flying, total, zmax


volumes.left = 0.0


def main():
    a = _args()
    import groundfx
    groundfx.register()
    from groundfx.ops.op_add import create_domain, rebuild_grid
    from groundfx.ops.op_collider import ensure_collider_collection
    from groundfx.core import modifier_io
    import bmesh

    scene = bpy.context.scene
    dom = create_domain(bpy.context, "SAND", size=a.size)
    dom.groundfx.quality = a.quality
    rebuild_grid(dom)
    md = dom.modifiers["GroundFX"]
    modifier_io.set_input(md, "Spray", a.spray)

    me = bpy.data.meshes.new("box")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.2)
    bm.to_mesh(me)
    bm.free()
    box = bpy.data.objects.new("box", me)
    scene.collection.objects.link(box)
    ensure_collider_collection(bpy.context, dom).objects.link(box)

    fps = scene.render.fps
    step = a.speed / fps
    h = dom.groundfx.material_height
    z = h + 0.1 - 0.03
    move = fps // 2
    v0 = None
    print("frame  bed[l]   top[l]   air[l]   sum[l]   fly  pts  zmax[m]  ms")
    for f in range(1, a.frames + 1):
        box.location = (-0.4 + step * min(f, move), 0.0, z)
        t = time.perf_counter()
        scene.frame_set(f)
        bed, top, air, fly, tot, zmax = volumes(dom)
        ms = (time.perf_counter() - t) * 1000.0
        if v0 is None:
            v0 = bed
        if f <= 3 or f % 3 == 0:
            print(f"{f:5d} {bed * 1e3:8.3f} {top * 1e3:8.3f} {air * 1e3:8.4f} "
                  f"{(bed + top + air) * 1e3:8.3f} {fly:5d} {tot:5d} "
                  f"{zmax:7.3f} {ms:6.1f}", flush=True)
    print(f"START {v0 * 1e3:.3f} l  END {(bed + top + air) * 1e3:.3f} l  "
          f"(airborne volume seen outside the domain, summed over frames: "
          f"{volumes.left * 1e3:.3f} l)")


if __name__ == "__main__":
    main()
