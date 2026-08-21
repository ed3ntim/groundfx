# SPDX-License-Identifier: GPL-3.0-or-later
"""E5-S1 tests: switching element swaps the solver physics atomically."""
from __future__ import annotations

import math

import bpy

import harness

from groundfx.core.constants import ELEM_SAND, ELEM_MUD, MODIFIER_NAME


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_element_switch_pushes_physics():
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.core import modifier_io
    from groundfx.core.nodegroups import ng_ground_sim as gsim
    from groundfx.data import elements as emod

    obj = create_domain(bpy.context, ELEM_SAND)
    md = obj.modifiers[MODIFIER_NAME]

    sand = emod.defaults(ELEM_SAND)
    harness.check(
        "sand repose seeded",
        abs(modifier_io.get_input(md, gsim.IN_REPOSE) - sand.repose_rad) < 1e-5,
        f"{modifier_io.get_input(md, gsim.IN_REPOSE):.4f} vs {sand.repose_rad:.4f}")

    # Switch to mud -> physics must follow immediately.
    obj.groundfx.element = ELEM_MUD
    mud = emod.defaults(ELEM_MUD)
    harness.check(
        "mud repose pushed",
        abs(modifier_io.get_input(md, gsim.IN_REPOSE) - mud.repose_rad) < 1e-5,
        f"{modifier_io.get_input(md, gsim.IN_REPOSE):.4f} vs {mud.repose_rad:.4f}")
    harness.check(
        "mud cohesion pushed",
        abs(modifier_io.get_input(md, gsim.IN_COHESION) - mud.cohesion) < 1e-5)
    harness.check(
        "mud bow wave pushed",
        abs(modifier_io.get_input(md, gsim.IN_BOW_WAVE) - mud.bow_wave) < 1e-5)
    harness.check("element custom-prop updated", obj["gfx_element"] == ELEM_MUD)

    # Sanity: mud is flatter than sand.
    harness.check("mud repose below sand", mud.repose_rad < sand.repose_rad,
                  f"{math.degrees(mud.repose_rad):.0f} < "
                  f"{math.degrees(sand.repose_rad):.0f}")
