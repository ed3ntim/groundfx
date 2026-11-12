# SPDX-License-Identifier: GPL-3.0-or-later
"""Material clinging to collider flanks (coat objects).

* a coat object exists per collider while Cling To Colliders is on, follows
  the element and goes away with the collider or the toggle;
* nothing clings before the object has touched the ground;
* after ploughing, lumps sit on the collider's faces, low on the flanks and
  not on the untouched top;
* cling 0 leaves the object clean.
"""
from __future__ import annotations

import bpy
import numpy as np

import harness

from groundfx.core.constants import (
    ELEM_SAND, ELEM_MUD, ELEM_SNOW, COAT_MODIFIER_NAME,
)
from groundfx.core import modifier_io
from groundfx.core.nodegroups import ng_coat as ncoat
from groundfx.ops import op_coat

_S = 0.08   # half size of the test cube


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _scene(element=ELEM_SAND):
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    scene = bpy.context.scene
    domain = create_domain(bpy.context, element, size=1.0)
    me = bpy.data.meshes.new("c")
    s = _S
    me.from_pydata([(x, y, z) for x in (-s, s) for y in (-s, s) for z in (-s, s)],
                   [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                        (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    cube = bpy.data.objects.new("c", me)
    scene.collection.objects.link(cube)
    ensure_collider_collection(bpy.context, domain).objects.link(cube)
    cube.groundfx.is_collider = True
    op_coat.sync_coats(bpy.context, domain)
    return domain, cube


def _verts(obj):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    co = np.zeros(len(ev.data.vertices) * 3)
    ev.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _plough(domain, cube, frames=24, depth=0.03):
    scene = bpy.context.scene
    h = domain.groundfx.material_height
    for f in range(1, frames + 1):
        t = min(1.0, (f - 1) / 14.0)
        cube.location = (-0.2 + 0.3 * t, 0.0, h + _S - depth)
        scene.frame_set(f)


def test_coat_lifecycle():
    _reset()
    domain, cube = _scene()
    coat = op_coat.find_coat(domain, cube)
    harness.check("coat object created", coat is not None)
    harness.check("coat is not a collider",
                  coat.name not in domain.groundfx.collider_collection.objects)
    harness.check("coat uses the sand group",
                  coat.modifiers[COAT_MODIFIER_NAME].node_group.name
                  == ncoat.group_name(ELEM_SAND))
    domain.groundfx.element = ELEM_MUD
    coat = op_coat.find_coat(domain, cube)
    harness.check("element switch swaps the coat group",
                  coat is not None
                  and coat.modifiers[COAT_MODIFIER_NAME].node_group.name
                  == ncoat.group_name(ELEM_MUD))
    domain.groundfx.element = ELEM_SNOW
    harness.check("element without a coat drops it",
                  op_coat.find_coat(domain, cube) is None)
    domain.groundfx.element = ELEM_SAND
    harness.check("and it comes back", op_coat.find_coat(domain, cube) is not None)
    domain.groundfx.coat_colliders = False
    harness.check("toggle off removes the coat",
                  op_coat.find_coat(domain, cube) is None)
    domain.groundfx.coat_colliders = True
    domain.groundfx.collider_collection.objects.unlink(cube)
    op_coat.sync_coats(bpy.context, domain)
    harness.check("coat leaves with the collider",
                  op_coat.find_coat(domain, cube) is None)


def test_clean_until_it_touches():
    _reset()
    domain, cube = _scene()
    scene = bpy.context.scene
    h = domain.groundfx.material_height
    for f in range(1, 6):
        cube.location = (0.0, 0.0, h + _S + 0.2)    # hovering well above
        scene.frame_set(f)
    coat = op_coat.find_coat(domain, cube)
    harness.check("hovering object stays clean", len(_verts(coat)) == 0,
                  f"{len(_verts(coat))} verts")


def test_ploughing_coats_the_flanks():
    _reset()
    domain, cube = _scene()
    _plough(domain, cube)
    coat = op_coat.find_coat(domain, cube)
    co = _verts(coat)
    harness.check("ploughing leaves material on the object", len(co) > 100,
                  f"{len(co)} verts")
    if len(co) == 0:
        return
    c = np.array(cube.location)
    rel = co - c
    tol = 0.004
    harness.check("lumps sit on the collider, not in the air",
                  np.abs(rel).max() <= _S + tol,
                  f"max offset {np.abs(rel).max():.4f}")
    on_face = (np.abs(np.abs(rel).max(axis=1) - _S) < tol)
    harness.check("lumps lie on its faces", on_face.mean() > 0.98,
                  f"{on_face.mean():.3f}")
    harness.check("the untouched top stays clean",
                  (rel[:, 2] > _S - 0.002).mean() < 0.01,
                  f"{(rel[:, 2] > _S - 0.002).mean():.3f}")
    harness.check("the coat is densest low on the flanks",
                  np.median(rel[:, 2]) < -_S * 0.3,
                  f"median z {np.median(rel[:, 2]):.4f}")


def test_cling_zero_stays_clean():
    _reset()
    domain, cube = _scene()
    coat = op_coat.find_coat(domain, cube)
    modifier_io.set_input(coat.modifiers[COAT_MODIFIER_NAME], ncoat.IN_CLING, 0.0)
    _plough(domain, cube)
    harness.check("cling 0 leaves the object clean", len(_verts(coat)) == 0,
                  f"{len(_verts(coat))} verts")


def test_mud_spatters_higher_than_sand():
    _reset()
    heights = {}
    for element in (ELEM_SAND, ELEM_MUD):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        domain, cube = _scene(element)
        _plough(domain, cube)
        co = _verts(op_coat.find_coat(domain, cube))
        heights[element] = (np.percentile(co[:, 2], 99) if len(co) else -1.0)
    harness.check("both elements leave a coat",
                  heights[ELEM_SAND] > 0 and heights[ELEM_MUD] > 0, f"{heights}")
    harness.check("mud reaches higher up the object than sand",
                  heights[ELEM_MUD] > heights[ELEM_SAND] + 0.005, f"{heights}")
