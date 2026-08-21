# SPDX-License-Identifier: GPL-3.0-or-later
"""E2-S2: the domain grid conforms to a terrain object (material on uneven ground)."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ELEM_SAND, ATTR_HEIGHT, MODIFIER_NAME


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _make_ramp(name, size=3.0, slope=0.25):
    """A flat grid tilted into a ramp: z = slope * x."""
    import numpy as np
    res = 8
    n = res + 1
    xs = (np.linspace(0.0, 1.0, n) - 0.5) * size
    gx, gy = np.meshgrid(xs, xs)
    z = slope * gx
    verts = np.column_stack((gx.ravel(), gy.ravel(), z.ravel()))
    idx = np.arange(n * n).reshape(n, n)
    faces = np.column_stack((idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(),
                             idx[1:, 1:].ravel(), idx[1:, :-1].ravel()))
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(faces.size)
    me.polygons.add(len(faces))
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 4))
    me.polygons.foreach_set("loop_total", np.full(len(faces), 4))
    me.update(); me.validate()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, slope


def test_grid_conforms_to_terrain_ramp():
    _reset()
    from groundfx.ops.op_add import create_domain, rebuild_grid, conform_grid_to_terrain

    ramp, slope = _make_ramp("Ramp")
    obj = create_domain(bpy.context, ELEM_SAND, size=2.0)
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()

    # Before: flat grid, all z ~ 0.
    zmax_flat = max(abs(v.co.z) for v in obj.data.vertices)
    harness.check("grid starts flat", zmax_flat < 1e-4, f"{zmax_flat}")

    obj.groundfx.terrain = ramp
    hits = conform_grid_to_terrain(obj, ramp, bpy.context)
    harness.check("most grid points hit the terrain", hits > 0.8 * len(obj.data.vertices),
                  f"{hits}/{len(obj.data.vertices)}")

    # After: vertex z should follow the ramp (z ~ slope*x) where it hit.
    worst = 0.0
    for v in obj.data.vertices:
        expected = slope * v.co.x
        worst = max(worst, abs(v.co.z - expected))
    harness.check("grid follows the ramp height", worst < 0.02,
                  f"max deviation {worst:.4f} m")

    # And the solved surface sits above the terrain (base + material height).
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    ha = ev.data.attributes.get(ATTR_HEIGHT)
    harness.check("material layer present on the ramp",
                  ha is not None and max(d.value for d in ha.data) > 0.0)
    for o in (ramp, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_rebuild_reconforms_to_terrain():
    _reset()
    from groundfx.ops.op_add import create_domain

    ramp, slope = _make_ramp("Ramp2")
    obj = create_domain(bpy.context, ELEM_SAND, size=2.0)
    obj.location = (0.0, 0.0, 0.0)
    obj.groundfx.terrain = ramp
    bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()

    bpy.ops.groundfx.rebuild_grid()
    tilted = max(v.co.z for v in obj.data.vertices) - min(v.co.z for v in obj.data.vertices)
    harness.check("rebuild conformed the grid to the ramp", tilted > 0.3,
                  f"z span {tilted:.3f}")
    for o in (ramp, obj):
        bpy.data.objects.remove(o, do_unlink=True)
