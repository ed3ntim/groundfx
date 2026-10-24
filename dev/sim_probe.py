# SPDX-License-Identifier: GPL-3.0-or-later
"""Step the hero scene headless and print solver statistics per frame.

    blender -b --factory-startup --python dev/sim_probe.py -- [--frames 40]
"""
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hero_scene  # noqa: E402


def stats(domain):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = domain.evaluated_get(deps)
    me = ev.data
    n = len(me.vertices)

    def arr(name):
        a = me.attributes.get(name)
        if a is None:
            return None
        out = np.zeros(n, dtype=np.float32)
        a.data.foreach_get("value", out)
        return out
    return arr("gfx_h"), arr("gfx_occ"), arr("gfx_carve")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    frames = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 40
    quality = argv[argv.index("--quality") + 1] if "--quality" in argv else "HIGH"
    domain, box = hero_scene.build("SAND", quality, 1.2, "close")
    if "--iters" in argv:
        from groundfx.core import modifier_io
        modifier_io.set_input(domain.modifiers["GroundFX"], "Relax Iterations", int(argv[argv.index("--iters") + 1]))
    if "--nobox" in argv:
        domain.groundfx.collider_collection.objects.unlink(box)
    if "--bump" in argv:  # a tall spike in the middle, no collider
        domain.groundfx.collider_collection.objects.unlink(box)
        from groundfx.core import modifier_io
        modifier_io.set_input(domain.modifiers["GroundFX"], "Material Height", 0.0)
        me = domain.data
        n = int(len(me.vertices) ** 0.5)
        co = np.zeros(len(me.vertices) * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        r = np.hypot(co[:, 0], co[:, 1])
        bump = np.where(r < 0.05, 0.10, 0.0).astype(np.float32)
        a = me.attributes.new("gfx_init", "FLOAT", "POINT")
        a.data.foreach_set("value", bump)
    scene = bpy.context.scene
    h0 = None
    for f in range(1, frames + 1):
        t = time.perf_counter()
        scene.frame_set(f)
        h, occ, carve = stats(domain)
        dt = (time.perf_counter() - t) * 1000
        if h is None:
            print(f"f{f}: no gfx_h")
            continue
        if h0 is None:
            h0 = h.sum()
        print(f"f{f:3d} {dt:6.0f}ms mass {h.sum() / h0:7.4f} "
              f"min {h.min():.4f} max {h.max():.4f} occ {int((occ > 0.5).sum())} "
              f"carve {carve.sum():.3f} nan {int(np.isnan(h).sum())}")


main()
