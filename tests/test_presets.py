# SPDX-License-Identifier: GPL-3.0-or-later
"""E5-S2 tests: named presets apply their physics to a domain."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ELEM_SAND, MODIFIER_NAME


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_preset_catalogue():
    _reset()
    from groundfx.data import presets as pmod
    from groundfx.core.constants import ELEMENTS

    presets = pmod.all_presets()
    harness.check("at least 8 presets", len(presets) >= 8, f"{len(presets)}")
    per_elem = {e: sum(1 for p in presets if p.element == e) for e in ELEMENTS}
    harness.check("every element has presets",
                  all(v > 0 for v in per_elem.values()), f"{per_elem}")


def test_apply_preset_changes_physics():
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.core import modifier_io
    from groundfx.core.nodegroups import ng_ground_sim as gsim
    from groundfx.data import presets as pmod

    obj = create_domain(bpy.context, ELEM_SAND)
    md = obj.modifiers[MODIFIER_NAME]
    bpy.context.view_layer.objects.active = obj

    wet = pmod.get("WET_SAND")
    bpy.ops.groundfx.apply_preset(preset="WET_SAND")
    harness.check(
        "preset repose applied",
        abs(modifier_io.get_input(md, gsim.IN_REPOSE) - wet.repose_rad) < 1e-5,
        f"{modifier_io.get_input(md, gsim.IN_REPOSE):.4f} vs {wet.repose_rad:.4f}")
    harness.check(
        "preset cohesion applied",
        abs(modifier_io.get_input(md, gsim.IN_COHESION) - wet.cohesion) < 1e-5)
    harness.check(
        "preset material height applied",
        abs(obj.groundfx.material_height - wet.material_height) < 1e-5)

    # A cross-element preset also switches the element (via the helper; the
    # operator's dropdown is filtered to the active element, B4).
    from groundfx.ops.op_preset import apply_preset
    mud = pmod.get("THICK_MUD")
    apply_preset(obj, mud)
    harness.check("preset switched element to mud",
                  obj.groundfx.element == "MUD")
    harness.check(
        "mud preset cohesion applied",
        abs(modifier_io.get_input(md, gsim.IN_COHESION) - mud.cohesion) < 1e-5)


def test_preset_items_filtered_by_element():
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_preset import _preset_items

    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj
    keys = {i[0] for i in _preset_items(None, bpy.context)}
    harness.check("sand domain lists only sand presets",
                  "WET_SAND" in keys and "THICK_MUD" not in keys, f"{keys}")
