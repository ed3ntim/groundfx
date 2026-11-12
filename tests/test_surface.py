# SPDX-License-Identifier: GPL-3.0-or-later
"""Gen 3 surface stage and look fields.

* the solver reports disturbance (``gfx_dist``) and damp material
  (``gfx_damp``) where a collider ploughed, and nowhere else;
* damp material dries, disturbance stays;
* the surface stage is opt-in, sits right after the solver, leaves the
  simulation grid untouched in the viewport, adds ripples as geometry and
  wipes them out where the ground is disturbed;
* an element without a surface stage never gets the modifier.
"""
from __future__ import annotations

import bpy
import numpy as np

import harness

from groundfx.core.constants import (
    ELEM_SAND, ELEM_SNOW, MODIFIER_NAME, SURFACE_MODIFIER_NAME,
    ATTR_DIST, ATTR_DAMP, MAT_CTRL_RIPPLE_LEN,
)
from groundfx.core.materials import mat_builder as matb


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _attr(obj, name):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    a = ev.data.attributes.get(name)
    out = np.zeros(len(a.data))
    a.data.foreach_get("value", out)
    return out


def _positions(obj):
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    co = np.zeros(len(ev.data.vertices) * 3)
    ev.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def _plough(surface=False, frames=24):
    """A cube dragged through a sand domain. Returns (domain, cube)."""
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_collider import ensure_collider_collection
    scene = bpy.context.scene
    domain = create_domain(bpy.context, ELEM_SAND, size=1.0, surface=surface)
    if surface:
        domain.groundfx.clod_height = 0.0
    me = bpy.data.meshes.new("c")
    s = 0.08
    me.from_pydata([(x, y, z) for x in (-s, s) for y in (-s, s) for z in (-s, s)],
                   [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                        (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    cube = bpy.data.objects.new("c", me)
    scene.collection.objects.link(cube)
    ensure_collider_collection(bpy.context, domain).objects.link(cube)
    cube.groundfx.is_collider = True
    h = domain.groundfx.material_height
    for f in range(1, frames + 1):
        t = min(1.0, (f - 1) / 14.0)
        cube.location = (-0.2 + 0.3 * t, 0.0, h + s - 0.03)
        scene.frame_set(f)
    return domain, cube


def test_solver_marks_disturbed_and_damp():
    _reset()
    domain, _ = _plough()
    dist = _attr(domain, ATTR_DIST)
    damp = _attr(domain, ATTR_DAMP)
    co = _positions(domain)
    far = (np.abs(co[:, 1]) > 0.35)
    track = (np.abs(co[:, 1]) < 0.05) & (co[:, 0] > -0.2) & (co[:, 0] < 0.05)
    harness.check("track is disturbed", dist[track].min() > 0.99,
                  f"min {dist[track].min():.3f}")
    harness.check("far ground is undisturbed", dist[far].max() == 0.0,
                  f"max {dist[far].max():.4f}")
    harness.check("far ground is dry", damp[far].max() == 0.0)
    harness.check("track is damp", damp[track].mean() > 0.4,
                  f"mean {damp[track].mean():.3f}")
    harness.check("fields stay in 0..1",
                  dist.min() >= 0.0 and dist.max() <= 1.0
                  and damp.min() >= 0.0 and damp.max() <= 1.0)


def test_damp_dries_disturbance_stays():
    _reset()
    domain, cube = _plough()
    scene = bpy.context.scene
    cube.location.z += 1.0          # lift the collider out
    scene.frame_set(scene.frame_current + 1)
    d0, w0 = _attr(domain, ATTR_DIST).sum(), _attr(domain, ATTR_DAMP).sum()
    for _ in range(40):
        scene.frame_set(scene.frame_current + 1)
    d1, w1 = _attr(domain, ATTR_DIST).sum(), _attr(domain, ATTR_DAMP).sum()
    harness.check("disturbance does not fade", d1 >= d0 - 1e-3,
                  f"{d0:.2f} -> {d1:.2f}")
    harness.check("damp material dries", w1 < w0 * 0.9, f"{w0:.2f} -> {w1:.2f}")


def test_surface_is_opt_in_and_ordered():
    _reset()
    from groundfx.ops.op_add import create_domain
    plain = create_domain(bpy.context, ELEM_SAND)
    harness.check("no surface stage by default",
                  plain.modifiers.get(SURFACE_MODIFIER_NAME) is None)
    plain.groundfx.surface_detail = True
    names = [m.name for m in plain.modifiers]
    harness.check("toggle adds the stage right after the solver",
                  names[:2] == [MODIFIER_NAME, SURFACE_MODIFIER_NAME], f"{names}")
    plain.groundfx.surface_detail = False
    harness.check("toggle removes it again",
                  plain.modifiers.get(SURFACE_MODIFIER_NAME) is None)

    snow = create_domain(bpy.context, ELEM_SNOW, surface=True)
    harness.check("element without a stage gets none",
                  snow.modifiers.get(SURFACE_MODIFIER_NAME) is None)
    snow.groundfx.element = ELEM_SAND
    harness.check("switching to sand attaches it",
                  snow.modifiers.get(SURFACE_MODIFIER_NAME) is not None)
    snow.groundfx.element = ELEM_SNOW
    harness.check("switching away removes it",
                  snow.modifiers.get(SURFACE_MODIFIER_NAME) is None)


def test_viewport_keeps_grid_and_adds_ripples():
    _reset()
    from groundfx.ops.op_add import create_domain, expected_vertex_count
    domain = create_domain(bpy.context, ELEM_SAND, size=1.0, surface=True)
    bpy.context.scene.frame_set(1)
    co = _positions(domain)
    harness.check("viewport level 0 keeps the simulation grid",
                  len(co) == expected_vertex_count(domain),
                  f"{len(co)} vs {expected_vertex_count(domain)}")
    z = co[:, 2] - domain.groundfx.material_height
    amp = domain.groundfx.ripple_height
    harness.check("ripples are geometry", z.std() > amp * 0.1,
                  f"std {z.std() * 1000:.2f} mm")
    harness.check("ripples stay within their height",
                  np.abs(z).max() <= amp * 0.5 * 1.25 + 1e-6,
                  f"max {np.abs(z).max() * 1000:.2f} mm")
    domain.groundfx.ripple_height = 0.0
    bpy.context.view_layer.update()
    z0 = _positions(domain)[:, 2] - domain.groundfx.material_height
    harness.check("ripple height 0 is flat", np.abs(z0).max() < 1e-6,
                  f"{np.abs(z0).max():.2e}")


def test_ripples_vanish_where_disturbed():
    _reset()
    domain, _ = _plough(surface=True)
    domain.modifiers[SURFACE_MODIFIER_NAME].show_viewport = True
    ev = domain.evaluated_get(bpy.context.evaluated_depsgraph_get())
    n_grid = (128 + 1) ** 2        # crumbs are appended after the grid
    co = _positions(domain)[:n_grid]
    h = np.zeros(len(ev.data.vertices))
    ev.data.attributes["gfx_h"].data.foreach_get("value", h)
    relief = co[:, 2] - h[:n_grid]   # what the stage added (flat base at 0)
    dist = _attr(domain, ATTR_DIST)[:n_grid]
    inside = (dist > 0.999) & (np.abs(co[:, 1]) < 0.04)
    outside = dist < 1e-6
    harness.check("undisturbed ground has ripple relief",
                  np.abs(relief[outside]).max() > 5e-4)
    harness.check("disturbed ground has none",
                  inside.any() and np.abs(relief[inside]).max() < 1e-5,
                  f"{np.abs(relief[inside]).max() if inside.any() else -1:.2e}")


def test_ripple_sliders_reach_shader():
    _reset()
    from groundfx.ops.op_add import create_domain
    domain = create_domain(bpy.context, ELEM_SAND, surface=True)
    domain.groundfx.ripple_length = 0.11
    node = matb.domain_material(domain).node_tree.nodes[MAT_CTRL_RIPPLE_LEN]
    harness.check("ripple length pushed into the material",
                  abs(node.outputs[0].default_value - 0.11) < 1e-6)


def test_surround_adds_geometry_with_material():
    _reset()
    from groundfx.ops.op_add import create_domain, expected_vertex_count
    domain = create_domain(bpy.context, ELEM_SAND, size=1.0, surface=True)
    domain.groundfx.surround = True
    bpy.context.view_layer.update()
    co = _positions(domain)
    harness.check("surround adds vertices",
                  len(co) > expected_vertex_count(domain))
    harness.check("surround reaches far beyond the domain",
                  np.abs(co[:, 0]).max() > 20.0, f"{np.abs(co[:, 0]).max():.1f}")
    ev = domain.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mats = {m.name for m in ev.data.materials if m}
    harness.check("everything wears the domain material",
                  mats == {matb.domain_material(domain).name}, f"{mats}")
