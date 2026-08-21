# SPDX-License-Identifier: GPL-3.0-or-later
"""E1-T9: the repair operator rebuilds a broken/missing node setup."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ELEM_SAND, MODIFIER_NAME
from groundfx.core import modifier_io
from groundfx.core.nodegroups import ng_ground_sim as gsim


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_repair_restores_a_cleared_node_group():
    _reset()
    from groundfx.ops.op_add import create_domain

    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj
    md = obj.modifiers[MODIFIER_NAME]

    # Break it: drop the node group, as a deleted data-block would.
    md.node_group = None
    harness.check("node group cleared", md.node_group is None)

    bpy.ops.groundfx.repair()
    md = obj.modifiers[MODIFIER_NAME]
    harness.check("repair restored the node group", md.node_group is not None)
    harness.check(
        "repair re-pushed grid_n",
        modifier_io.get_input(md, gsim.IN_GRID_N) > 2,
        f"{modifier_io.get_input(md, gsim.IN_GRID_N)}")
    bpy.data.objects.remove(obj, do_unlink=True)


def test_repair_recreates_a_missing_modifier():
    _reset()
    from groundfx.ops.op_add import create_domain

    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj
    obj.modifiers.remove(obj.modifiers[MODIFIER_NAME])
    harness.check("modifier removed", obj.modifiers.get(MODIFIER_NAME) is None)

    bpy.ops.groundfx.repair()
    harness.check("repair recreated the modifier",
                  obj.modifiers.get(MODIFIER_NAME) is not None)
    bpy.data.objects.remove(obj, do_unlink=True)
