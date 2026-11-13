# SPDX-License-Identifier: GPL-3.0-or-later
"""Attach and feed the spray stage (gen 4) on a domain.

Two things follow ``obj.groundfx.spray``: the solver input that decides how
much fast-displaced material leaves the ground, and the display modifier
that turns the flying parcels into grains. The modifier is the last GroundFX
stage on the domain (it needs the finished ground to land grains on).
Idempotent, like ``sync_surface``.

The three elements share solver and display stage and differ in a profile:
what one airborne piece is (a sand grain, a clot of mud, a crumb of snow),
how the air treats it and how far a parcel's pieces drift apart.
"""
from __future__ import annotations

import bpy

from ..core import modifier_io
from ..core.constants import (
    ELEM_SAND, ELEM_SNOW, ELEM_MUD, MODIFIER_NAME, SURFACE_MODIFIER_NAME,
    SPRAY_MODIFIER_NAME, NG_SPRAY,
)
from ..core.ng_library import ensure_node_group
from ..core.nodegroups import ng_spray as nspray
from ..core.nodegroups import ng_ground_sim as gsim


class SprayProfile:
    __slots__ = ("grain", "drag", "spread", "clumps", "max_grains")

    def __init__(self, grain, drag, spread, clumps, max_grains):
        self.grain = grain            # metres, diameter of a typical piece
        self.drag = drag              # air drag relative to sand
        self.spread = spread          # velocity scatter, share of launch speed
        self.clumps = clumps          # size factor of the rare big pieces
        self.max_grains = max_grains  # pieces per parcel at most


PROFILES = {
    # Dry grains: many, small, each on its own.
    ELEM_SAND: SprayProfile(0.0005, 1.0, 0.07, 2.5, 240),
    # Powder and crumbs: a tenth of sand's density, so the air stops it
    # within a few hand widths and it hangs; crumbs of packed snow fly on.
    ELEM_SNOW: SprayProfile(0.001, 20.0, 0.16, 3.0, 240),
    # Wet and cohesive: leaves in few heavy clots and strings, stays
    # together, hardly feels the air.
    ELEM_MUD: SprayProfile(0.009, 0.5, 0.04, 1.6, 5),
}

# Elements whose airborne phase has a look.
SPRAY_ELEMENTS = tuple(PROFILES)


def profile(element: str) -> SprayProfile:
    return PROFILES.get(element, PROFILES[ELEM_SAND])


def spray_modifier(obj):
    return obj.modifiers.get(SPRAY_MODIFIER_NAME) if obj else None


def remove_spray(obj) -> None:
    md = spray_modifier(obj)
    if md is not None:
        obj.modifiers.remove(md)


def _move_to_end_of_stack(obj, md) -> None:
    """After the surface stage if there is one, else after the solver."""
    names = [m.name for m in obj.modifiers]
    anchor = SURFACE_MODIFIER_NAME if SURFACE_MODIFIER_NAME in names \
        else MODIFIER_NAME
    if anchor not in names:
        return
    want = names.index(anchor) + 1
    have = names.index(md.name)
    if have != want:
        obj.modifiers.move(have, want if have > want else want - 1)


def push_spray_inputs(obj, *, tag=True) -> bool:
    st = obj.groundfx
    prof = profile(st.element)
    solver = obj.modifiers.get(MODIFIER_NAME)
    if solver is not None and solver.node_group is not None:
        amount = st.spray if st.element in SPRAY_ELEMENTS else 0.0
        modifier_io.set_input(solver, gsim.IN_SPRAY, amount, tag=False)
        modifier_io.set_input(solver, gsim.IN_SPRAY_DRAG, prof.drag, tag=False)
        modifier_io.set_input(solver, gsim.IN_SPRAY_LIFT, st.spray_lift,
                              tag=False)
    md = spray_modifier(obj)
    if md is None or md.node_group is None:
        if tag:
            obj.update_tag()
        return False
    from ..core.materials import mat_spray
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base if scene else 24.0
    set_ = modifier_io.set_input
    set_(md, nspray.IN_GRAIN, st.spray_grain, tag=False)
    set_(md, nspray.IN_DETAIL, st.spray_detail, tag=False)
    set_(md, nspray.IN_SPREAD, prof.spread, tag=False)
    set_(md, nspray.IN_CLUMPS, prof.clumps, tag=False)
    set_(md, nspray.IN_MAX, prof.max_grains, tag=False)
    set_(md, nspray.IN_FRAME_TIME, 1.0 / max(1.0, fps), tag=False)
    set_(md, nspray.IN_MATERIAL, mat_spray.spray_material(st.element),
         tag=tag)
    return True


def sync_spray(obj, *, tag=True) -> bool:
    """Make solver input and modifier stack match ``obj.groundfx``. Returns
    whether the domain has a spray stage afterwards."""
    st = obj.groundfx
    wanted = st.spray > 0.0 and st.element in SPRAY_ELEMENTS
    if not wanted:
        remove_spray(obj)
        push_spray_inputs(obj, tag=tag)
        return False
    tree = ensure_node_group(NG_SPRAY, nspray.build)
    modifier_io.invalidate(tree.name)
    md = spray_modifier(obj)
    if md is None:
        md = obj.modifiers.new(SPRAY_MODIFIER_NAME, "NODES")
    md.node_group = tree
    _move_to_end_of_stack(obj, md)
    push_spray_inputs(obj, tag=tag)
    return True
