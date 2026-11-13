# SPDX-License-Identifier: GPL-3.0-or-later
"""Extent of the airborne grains in the hero skid scene, per frame.

    blender -b --factory-startup --python dev/probe_spray_shape.py

Prints, for the parcels (solver) and the grains (spray stage), the range in
x, y, z and percentiles of the height above the resting surface.
"""
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hero_scene  # noqa: E402

domain, box = hero_scene.build("SAND", "HIGH", 1.2, "wide", surround=False,
                               coat=False, action="skid")
scene = bpy.context.scene
rest = domain.groundfx.material_height
spray = domain.modifiers.get("GroundFX Spray")


def cloud(show_spray):
    spray.show_viewport = show_spray
    deps = bpy.context.evaluated_depsgraph_get()
    gs = domain.evaluated_get(deps).evaluated_geometry()
    pc = gs.pointcloud
    if pc is None or not len(pc.points):
        return None
    co = np.zeros(len(pc.points) * 3)
    pc.attributes["position"].data.foreach_get("vector", co)
    return co.reshape(-1, 3)


for f in range(1, 27):
    scene.frame_set(f)
    if f not in (10, 14, 18, 22, 26):
        continue
    print(f"FRAME {f} box x={box.matrix_world.translation.x:.3f}")
    for label, on in (("parcels", False), ("grains", True)):
        co = cloud(on)
        if co is None:
            print(f"  {label}: none")
            continue
        z = co[:, 2] - rest
        print(f"  {label:8} n={len(co):7d} "
              f"x[{co[:, 0].min():.2f},{co[:, 0].max():.2f}] "
              f"y[{co[:, 1].min():.2f},{co[:, 1].max():.2f}] "
              f"z above rest p50={np.percentile(z, 50):.3f} "
              f"p90={np.percentile(z, 90):.3f} max={z.max():.3f}")
    spray.show_viewport = False
    deps = bpy.context.evaluated_depsgraph_get()
    gs = domain.evaluated_get(deps).evaluated_geometry()
    pc = gs.pointcloud
    if pc is not None and len(pc.points):
        k = len(pc.points)
        v = np.zeros(k * 3)
        pc.attributes["gfx_e_v"].data.foreach_get("vector", v)
        v0 = np.zeros(k)
        pc.attributes["gfx_e_v0"].data.foreach_get("value", v0)
        age = np.zeros(k)
        pc.attributes["gfx_e_age"].data.foreach_get("value", age)
        v = v.reshape(-1, 3)
        new = age < 0.06
        print(f"  launch speed p50={np.percentile(v0, 50):.2f} "
              f"p99={np.percentile(v0, 99):.2f} max={v0.max():.2f} m/s; "
              f"newborn vz max={v[new, 2].max() if new.any() else 0:.2f} "
              f"vx max={v[new, 0].max() if new.any() else 0:.2f}")
    me = gs.mesh
    gv = np.zeros(len(me.vertices) * 3)
    me.attributes["gfx_vel"].data.foreach_get("vector", gv)
    gv = np.linalg.norm(gv.reshape(-1, 3), axis=1)
    print(f"  collider step per frame max={gv.max():.4f} m "
          f"(= {gv.max() * scene.render.fps:.2f} m/s)")
    if pc is not None and len(pc.points):
        co = np.zeros(k * 3)
        pc.attributes["position"].data.foreach_get("vector", co)
        co = co.reshape(-1, 3)
        land = np.zeros(k)
        pc.attributes["gfx_e_land"].data.foreach_get("value", land)
        drag = np.zeros(k)
        pc.attributes["gfx_e_drag"].data.foreach_get("value", drag)
        for i in np.argsort(-co[:, 2])[:6]:
            print(f"    high: pos=({co[i, 0]:.2f},{co[i, 1]:.2f},{co[i, 2]:.2f}) "
                  f"v=({v[i, 0]:.2f},{v[i, 1]:.2f},{v[i, 2]:.2f}) age={age[i]:.2f} "
                  f"land={land[i]:.0f} drag={drag[i]:.2f} v0={v0[i]:.2f}")
    for name in ("gfx_h", "gfx_arr", "gfx_air", "gfx_top", "gfx_carve"):
        a = np.zeros(len(me.vertices))
        me.attributes[name].data.foreach_get("value", a)
        print(f"    grid {name}: max={a.max():.4f} sum={a.sum():.3f} "
              f"cells>0.2m={(a > 0.2).sum()}")
