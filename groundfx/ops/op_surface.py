# SPDX-License-Identifier: GPL-3.0-or-later
"""Attach and feed the surface stage (gen 3) on a domain.

The stage is a second Geometry Nodes modifier after the solver. It exists
per element: so far only sand has one. Everything here is idempotent, so the
property callbacks, the rebuild path and the repair path can all call
``sync_surface`` without caring about the current state.
"""
from __future__ import annotations

import math

from ..core import modifier_io
from ..core.constants import (
    ELEM_SAND, ELEM_MUD, MODIFIER_NAME, SURFACE_MODIFIER_NAME,
)
from ..core.ng_library import ensure_node_group
from ..core.nodegroups import ng_surface as nsurf
from ..data import quality as qmod

# Elements that have a surface stage.
SURFACE_ELEMENTS = (ELEM_SAND, ELEM_MUD)


def render_level(resolution: int) -> int:
    """Subdivision level that brings the grid to about 1000 cells a side."""
    return max(1, min(3, round(math.log2(1024 / max(1, resolution)))))


def surface_modifier(obj):
    return obj.modifiers.get(SURFACE_MODIFIER_NAME) if obj else None


def remove_surface(obj) -> None:
    md = surface_modifier(obj)
    if md is not None:
        obj.modifiers.remove(md)


def _move_after_solver(obj, md) -> None:
    names = [m.name for m in obj.modifiers]
    if MODIFIER_NAME not in names:
        return
    want = names.index(MODIFIER_NAME) + 1
    have = names.index(md.name)
    if have != want:
        obj.modifiers.move(have, want if have > want else want - 1)


def push_surface_inputs(obj, *, tag=True) -> bool:
    md = surface_modifier(obj)
    if md is None or md.node_group is None:
        return False
    st = obj.groundfx
    prof = qmod.profile(st.quality)
    set_ = modifier_io.set_input
    set_(md, nsurf.IN_RENDER_LEVEL, render_level(prof.resolution), tag=False)
    set_(md, nsurf.IN_VIEW_LEVEL, 0, tag=False)
    set_(md, nsurf.IN_RIPPLE_HEIGHT, st.ripple_height, tag=False)
    set_(md, nsurf.IN_RIPPLE_LENGTH, st.ripple_length, tag=False)
    set_(md, nsurf.IN_WIND, st.wind_direction, tag=False)
    set_(md, nsurf.IN_CLOD_HEIGHT, st.clod_height, tag=False)
    set_(md, nsurf.IN_PEBBLES, st.pebbles, tag=False)
    set_(md, nsurf.IN_SURROUND, st.surround, tag=False)
    from ..core.materials import mat_builder as matb
    set_(md, nsurf.IN_MATERIAL, matb.domain_material(obj), tag=False)
    set_(md, nsurf.IN_UNDULATION, st.undulation, tag=False)
    set_(md, nsurf.IN_WATER, st.water, tag=False)
    set_(md, nsurf.IN_WATER_LEVEL, st.water_level, tag=False)
    set_(md, nsurf.IN_WATER_MATERIAL,
         matb.water_material() if st.element == ELEM_MUD else None, tag=False)
    set_(md, nsurf.IN_DOMAIN_SIZE, st.domain_size, tag=False)
    set_(md, nsurf.IN_MATERIAL_HEIGHT, st.material_height, tag=tag)
    return True


def sync_surface(obj, *, tag=True) -> bool:
    """Make the modifier stack match ``obj.groundfx``. Returns whether the
    domain has a surface stage afterwards."""
    st = obj.groundfx
    wanted = st.surface_detail and st.element in SURFACE_ELEMENTS
    if not wanted:
        remove_surface(obj)
        if tag:
            obj.update_tag()
        return False
    element = st.element
    tree = ensure_node_group(nsurf.group_name(element),
                             lambda name: nsurf.build(name, element))
    modifier_io.invalidate(tree.name)
    md = surface_modifier(obj)
    if md is None:
        md = obj.modifiers.new(SURFACE_MODIFIER_NAME, "NODES")
    md.node_group = tree
    _move_after_solver(obj, md)
    push_surface_inputs(obj, tag=tag)
    return True
