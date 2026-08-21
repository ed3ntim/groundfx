# SPDX-License-Identifier: GPL-3.0-or-later
"""E8 acceptance: procedural materials, their physics link, and the lifecycle.

Shaders can't be asserted by a pixel here, so these tests pin the *structure*
and the *lifecycle* — the parts that break silently:

* every element builds a Principled graph with a linked surface, wired to the
  solver's ``gfx_comp`` attribute so tracks read differently from undisturbed
  material (E8-T5/T6);
* adding a domain assigns exactly one GroundFX material (E8-T1);
* switching the element swaps that material in place, leaving a single slot
  (E8-S1), and never touches a material the user assigned themselves (E8-T10);
* the wetness slider moves both the shader and the solver cohesion (E8-T7).
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import (
    ELEM_SAND, ELEM_SNOW, ELEM_MUD, MODIFIER_NAME, MAT_CTRL_WETNESS,
    MAT_CTRL_ROUGHNESS, ATTR_COMP,
)
from groundfx.core.materials import mat_builder as matb
from groundfx.core import modifier_io
from groundfx.core.nodegroups import ng_ground_sim as gsim


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _has_node(mat, pred):
    return any(pred(n) for n in mat.node_tree.nodes)


def test_each_element_builds_a_valid_graph():
    _reset()
    for element in (ELEM_SAND, ELEM_SNOW, ELEM_MUD):
        mat = matb.build_material(element)
        harness.check(f"{element}: stamped generated", matb.is_generated(mat))
        out = next((n for n in mat.node_tree.nodes
                    if n.type == "OUTPUT_MATERIAL"), None)
        harness.check(f"{element}: surface linked",
                      out is not None and out.inputs["Surface"].is_linked)
        harness.check(f"{element}: has Principled",
                      _has_node(mat, lambda n: n.type == "BSDF_PRINCIPLED"))
        harness.check(
            f"{element}: reads gfx_comp",
            _has_node(mat, lambda n: getattr(n, "attribute_name", "") == ATTR_COMP))
        harness.check(f"{element}: control nodes present",
                      mat.node_tree.nodes.get(MAT_CTRL_WETNESS) is not None
                      and mat.node_tree.nodes.get(MAT_CTRL_ROUGHNESS) is not None)


def test_add_assigns_single_material():
    _reset()
    from groundfx.ops.op_add import create_domain
    obj = create_domain(bpy.context, ELEM_SAND)
    gen = [s.material for s in obj.material_slots if matb.is_generated(s.material)]
    harness.check("exactly one GroundFX material slot", len(gen) == 1,
                  f"slots: {[s.material.name if s.material else None for s in obj.material_slots]}")
    harness.check("no empty slot",
                  all(s.material is not None for s in obj.material_slots))
    bpy.data.objects.remove(obj, do_unlink=True)


def test_element_switch_swaps_material_in_place():
    _reset()
    from groundfx.ops.op_add import create_domain
    obj = create_domain(bpy.context, ELEM_SAND)
    obj.groundfx.element = ELEM_SNOW
    mat = matb.domain_material(obj)
    harness.check("switched to snow material",
                  mat is not None and mat.name.startswith("GFX_Snow"))
    n_slots = len(obj.material_slots)
    harness.check("still a single slot after switch", n_slots == 1, f"{n_slots}")
    harness.check("no empty slot after switch",
                  all(s.material is not None for s in obj.material_slots))
    bpy.data.objects.remove(obj, do_unlink=True)


def test_user_material_is_never_overwritten():
    _reset()
    from groundfx.ops.op_add import create_domain
    obj = create_domain(bpy.context, ELEM_SAND)
    # Replace with the user's own material, then switch element.
    user = bpy.data.materials.new("UserOwn")
    obj.data.materials.clear()
    obj.data.materials.append(user)
    obj.groundfx.element = ELEM_MUD
    names = [s.material.name for s in obj.material_slots if s.material]
    harness.check("user's material kept", "UserOwn" in names, f"{names}")
    harness.check("no GroundFX material forced in",
                  matb.domain_material(obj) is None, f"{names}")
    bpy.data.objects.remove(obj, do_unlink=True)


def test_wetness_moves_look_and_physics():
    _reset()
    from groundfx.ops.op_add import create_domain
    obj = create_domain(bpy.context, ELEM_SAND)  # sand rests dry -> clear signal
    md = obj.modifiers[MODIFIER_NAME]
    coh0 = modifier_io.get_input(md, gsim.IN_COHESION)

    obj.groundfx.wetness = 0.8
    coh1 = modifier_io.get_input(md, gsim.IN_COHESION)
    matwet = matb.domain_material(obj).node_tree.nodes[MAT_CTRL_WETNESS] \
        .outputs[0].default_value

    harness.check("wetness raised cohesion", coh1 > coh0 + 0.1,
                  f"{coh0:.3f} -> {coh1:.3f}")
    harness.check("wetness reached the shader", abs(matwet - 0.8) < 1e-4,
                  f"material wetness = {matwet:.3f}")
    bpy.data.objects.remove(obj, do_unlink=True)
