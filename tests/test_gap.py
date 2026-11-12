# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawn surface meets collider walls without a gap.

A height field joins the cut cell under an object and the full cell beside
it with a ramp. The display raises the outermost cells under the object to
the height of the free material next to them, so the ramp lies inside the
object. The simulated height (``gfx_h``) is not touched.
"""
from __future__ import annotations

import bpy
import numpy as np

import harness

from groundfx.core.constants import ELEM_SAND

_S = 0.1


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _attr(ev, name):
    out = np.zeros(len(ev.data.vertices))
    ev.data.attributes[name].data.foreach_get("value", out)
    return out


def test_surface_meets_the_wall():
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    scene = bpy.context.scene
    domain = create_domain(bpy.context, ELEM_SAND, size=1.0)
    me = bpy.data.meshes.new("c")
    s = _S
    me.from_pydata([(x, y, z) for x in (-s, s) for y in (-s, s) for z in (-s, s)],
                   [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                        (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    cube = bpy.data.objects.new("c", me)
    scene.collection.objects.link(cube)
    ensure_collider_collection(bpy.context, domain).objects.link(cube)
    h0 = domain.groundfx.material_height
    for f in range(1, 12):
        cube.location = (0.0, 0.0, h0 + s - 0.03)   # pressed 3 cm in, at rest
        scene.frame_set(f)

    ev = domain.evaluated_get(bpy.context.evaluated_depsgraph_get())
    n = len(ev.data.vertices)
    co = np.zeros(n * 3)
    ev.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    h = _attr(ev, "gfx_h")
    occ = _attr(ev, "gfx_occ") > 0.5
    cell = 1.0 / 128
    d = np.maximum(np.abs(co[:, 0]), np.abs(co[:, 1]))     # square distance
    rim = occ & (d > s - 1.2 * cell)                        # outermost row inside
    core = occ & (d < s - 4 * cell)                         # well under the object
    outside = (~occ) & (d < s + 1.5 * cell)                 # first free row

    harness.check("there are rim, core and outside cells",
                  rim.any() and core.any() and outside.any())
    bottom = h0 - 0.03
    harness.check("simulated height under the object is still the cut",
                  abs(h[rim].mean() - bottom) < 2e-3, f"{h[rim].mean():.4f}")
    harness.check("rim is drawn at the level of the material beside it",
                  co[rim, 2].mean() > co[outside, 2].mean() - 0.006,
                  f"rim {co[rim, 2].mean():.4f} outside {co[outside, 2].mean():.4f}")
    harness.check("deep under the object the drawn surface is the cut",
                  np.abs(co[core, 2] - h[core]).max() < 1e-5)
    harness.check("free cells are drawn where they are simulated",
                  np.abs(co[~occ, 2] - h[~occ]).max() < 1e-5)
