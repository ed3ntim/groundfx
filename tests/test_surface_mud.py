# SPDX-License-Identifier: GPL-3.0-or-later
"""Gen 3 mud: surface stage with standing water.

* mud gets its own surface group (no ripple nodes), sand keeps its own;
* the water sheet is one quad at the water table, on by default, and can be
  switched off;
* ``gfx_shore`` marks ground at or below the water (1) and well above (0),
  and a track cut below the water table is flooded;
* the water material exists once and is separate from the mud material.
"""
from __future__ import annotations

import bpy
import numpy as np

import harness

from groundfx.core.constants import (
    ELEM_SAND, ELEM_MUD, SURFACE_MODIFIER_NAME, ATTR_SHORE, MAT_WATER,
)
from groundfx.core.materials import mat_builder as matb
from groundfx.core.nodegroups import ng_surface as nsurf


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _eval(obj):
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get())


def _positions(obj):
    ev = _eval(obj)
    co = np.zeros(len(ev.data.vertices) * 3)
    ev.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _attr(obj, name):
    a = _eval(obj).data.attributes.get(name)
    out = np.zeros(len(a.data))
    a.data.foreach_get("value", out)
    return out


def _mud(size=1.0):
    from groundfx.ops.op_add import create_domain
    domain = create_domain(bpy.context, ELEM_MUD, size=size, surface=True)
    domain.groundfx.pebbles = 0.0    # no pebbles, no straw
    # no clots either: the tests below count and index the grid vertices
    from groundfx.core import modifier_io
    modifier_io.set_input(domain.modifiers[SURFACE_MODIFIER_NAME],
                          nsurf.IN_CRUMBS, 0.0)
    bpy.context.scene.frame_set(1)
    return domain


def test_mud_has_its_own_surface_group():
    _reset()
    from groundfx.ops.op_add import create_domain
    mud = _mud()
    sand = create_domain(bpy.context, ELEM_SAND, surface=True)
    g_mud = mud.modifiers[SURFACE_MODIFIER_NAME].node_group
    g_sand = sand.modifiers[SURFACE_MODIFIER_NAME].node_group
    harness.check("mud uses the mud group",
                  g_mud.name == nsurf.group_name(ELEM_MUD), g_mud.name)
    harness.check("sand uses the sand group",
                  g_sand.name == nsurf.group_name(ELEM_SAND), g_sand.name)
    mud.groundfx.element = ELEM_SAND
    harness.check("element switch swaps the group",
                  mud.modifiers[SURFACE_MODIFIER_NAME].node_group is g_sand)


def test_water_sheet_toggles():
    _reset()
    from groundfx.ops.op_add import expected_vertex_count
    mud = _mud()
    n_grid = expected_vertex_count(mud)
    co = _positions(mud)
    harness.check("water adds exactly one quad", len(co) == n_grid + 4,
                  f"{len(co)} vs {n_grid} + 4")
    st = mud.groundfx
    level = st.material_height + st.water_level
    harness.check("sheet lies at the water table",
                  np.allclose(co[n_grid:, 2], level, atol=1e-6),
                  f"{co[n_grid:, 2]} vs {level}")
    mats = {m.name for m in _eval(mud).data.materials if m}
    harness.check("sheet wears the water material", MAT_WATER in mats, f"{mats}")
    harness.check("water material is not the mud material",
                  matb.water_material() is not matb.domain_material(mud))
    st.water = False
    bpy.context.view_layer.update()
    harness.check("water off removes the sheet",
                  len(_positions(mud)) == n_grid)


def test_shore_follows_the_water_table():
    _reset()
    from groundfx.ops.op_add import expected_vertex_count
    mud = _mud()
    n = expected_vertex_count(mud)
    st = mud.groundfx
    st.undulation = 0.03            # strong relief: clear hollows and rises
    bpy.context.view_layer.update()
    co = _positions(mud)[:n]
    shore = _attr(mud, ATTR_SHORE)[:n]
    level = st.material_height + st.water_level
    below = co[:, 2] <= level
    high = co[:, 2] > level + 0.013
    harness.check("the flat has hollows below the water", below.mean() > 0.02,
                  f"{below.mean():.3f}")
    harness.check("and ground above it", high.mean() > 0.02, f"{high.mean():.3f}")
    harness.check("ground under water is fully soaked",
                  shore[below].min() > 0.999, f"{shore[below].min():.3f}")
    harness.check("high ground is not", shore[high].max() < 1e-3,
                  f"{shore[high].max():.3f}")
    st.water = False
    bpy.context.view_layer.update()
    harness.check("no water, no shore", _attr(mud, ATTR_SHORE)[:n].max() == 0.0)


def test_track_floods():
    _reset()
    from groundfx.ops.op_add import expected_vertex_count
    from groundfx.ops.op_collider import ensure_collider_collection
    scene = bpy.context.scene
    mud = _mud()
    mud.groundfx.undulation = 0.0          # level ground: only the track dips
    me = bpy.data.meshes.new("c")
    s = 0.08
    me.from_pydata([(x, y, z) for x in (-s, s) for y in (-s, s) for z in (-s, s)],
                   [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                        (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    cube = bpy.data.objects.new("c", me)
    scene.collection.objects.link(cube)
    ensure_collider_collection(bpy.context, mud).objects.link(cube)
    cube.groundfx.is_collider = True
    h = mud.groundfx.material_height
    for f in range(1, 22):
        t = min(1.0, (f - 1) / 14.0)
        cube.location = (-0.2 + 0.3 * t, 0.0, h + s - 0.03)
        scene.frame_set(f)
    n = expected_vertex_count(mud)
    co = _positions(mud)[:n]
    shore = _attr(mud, ATTR_SHORE)[:n]
    track = (np.abs(co[:, 1]) < 0.04) & (co[:, 0] > -0.2) & (co[:, 0] < -0.05)
    far = np.abs(co[:, 1]) > 0.4
    harness.check("track behind the object is under water",
                  shore[track].mean() > 0.9, f"{shore[track].mean():.3f}")
    harness.check("untouched ground is clearly less soaked than the track",
                  shore[far].mean() < shore[track].mean() - 0.2,
                  f"{shore[far].mean():.3f} vs {shore[track].mean():.3f}")
