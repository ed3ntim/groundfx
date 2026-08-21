# SPDX-License-Identifier: GPL-3.0-or-later
"""E6-S1: Quality/Size take effect via an explicit grid rebuild.

Changing Quality only updates the readout until the grid is rebuilt; these
tests pin that the rebuild actually re-resolutions the mesh, re-pushes the
resolution-dependent solver inputs, and keeps the GroundFX material.
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import (
    ELEM_SAND, MODIFIER_NAME, QUALITY_HIGH, QUALITY_MEDIUM,
)
from groundfx.core import modifier_io
from groundfx.core.nodegroups import ng_ground_sim as gsim
from groundfx.data import quality as qmod


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_quality_change_needs_rebuild_then_matches():
    _reset()
    from groundfx.ops.op_add import create_domain, grid_is_current, expected_vertex_count

    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj
    harness.check("fresh domain grid is current", grid_is_current(obj))

    mat_before = obj.active_material

    # Bump quality: the mesh no longer matches until we rebuild.
    obj.groundfx.quality = QUALITY_HIGH
    harness.check("grid marked outdated after quality change",
                  not grid_is_current(obj))

    bpy.ops.groundfx.rebuild_grid()
    md = obj.modifiers[MODIFIER_NAME]
    prof = qmod.profile(QUALITY_HIGH)
    harness.check("grid current again after rebuild", grid_is_current(obj))
    harness.check("mesh re-resolutioned",
                  len(obj.data.vertices) == expected_vertex_count(obj),
                  f"{len(obj.data.vertices)} vs {expected_vertex_count(obj)}")
    harness.check(
        "grid_n input re-pushed",
        modifier_io.get_input(md, gsim.IN_GRID_N) == prof.resolution + 1,
        f"{modifier_io.get_input(md, gsim.IN_GRID_N)}")
    harness.check(
        "cell_size input re-pushed",
        abs(modifier_io.get_input(md, gsim.IN_CELL_SIZE)
            - obj.groundfx.domain_size / prof.resolution) < 1e-6)
    harness.check("material survived the mesh swap",
                  obj.active_material is not None
                  and obj.active_material.get("gfx_generated"))
    bpy.data.objects.remove(obj, do_unlink=True)
