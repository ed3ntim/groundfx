# SPDX-License-Identifier: GPL-3.0-or-later
"""Property groups exposed on objects and the scene.

Object-level settings live on ``object.groundfx``. Their update callbacks push
values straight into the geometry-node modifier, so editing a slider in the UI
reruns the solver immediately.
"""
from __future__ import annotations

import bpy

from ..core import modifier_io
from ..core.constants import (
    ELEMENTS, ELEMENT_LABELS, QUALITY_LEVELS, MODIFIER_NAME,
    DEFAULT_DOMAIN_SIZE, DEFAULT_MATERIAL_HEIGHT,
    PROXY_MODES, PROXY_MODE_LABELS,
)
from ..core.nodegroups import ng_ground_sim as gsim
from ..data import quality as qmod


def _element_items(self, context):
    return [(k, ELEMENT_LABELS[k], f"{ELEMENT_LABELS[k]} material") for k in ELEMENTS]


def _quality_items(self, context):
    return [(k, qmod.profile(k).label,
             f"{qmod.profile(k).label} quality "
             f"({qmod.profile(k).resolution}^2)") for k in QUALITY_LEVELS]


def _domain_modifier(obj):
    return obj.modifiers.get(MODIFIER_NAME) if obj else None


def _push_material_height(self, context):
    obj = self.id_data
    md = _domain_modifier(obj)
    if md:
        modifier_io.set_input(md, gsim.IN_MATERIAL_HEIGHT, self.material_height)


def _push_collider_collection(self, context):
    obj = self.id_data
    md = _domain_modifier(obj)
    if md:
        modifier_io.set_input(md, gsim.IN_COLLIDER_COLLECTION,
                              self.collider_collection)


class GroundFXObjectSettings(bpy.types.PropertyGroup):
    is_domain: bpy.props.BoolProperty(
        name="Is GroundFX Domain", default=False)

    is_collider: bpy.props.BoolProperty(
        name="Is GroundFX Collider", default=False)

    collider_proxy: bpy.props.EnumProperty(
        name="Proxy", default=0,
        items=[(m, PROXY_MODE_LABELS[m], PROXY_MODE_LABELS[m])
               for m in PROXY_MODES],
        description="How this collider is presented to the raycast")

    proxy_source: bpy.props.PointerProperty(
        name="Proxy Source", type=bpy.types.Object,
        description="Set on a proxy object; points at the collider it stands in for")

    element: bpy.props.EnumProperty(
        name="Element", items=_element_items,
        description="Material type this domain simulates")

    quality: bpy.props.EnumProperty(
        name="Quality", items=_quality_items, default=1,  # Medium
        description="Performance vs. fidelity level")

    domain_size: bpy.props.FloatProperty(
        name="Domain Size", default=DEFAULT_DOMAIN_SIZE, min=0.05, max=200.0,
        subtype="DISTANCE",
        description="Side length of the square domain in metres")

    material_height: bpy.props.FloatProperty(
        name="Material Height", default=DEFAULT_MATERIAL_HEIGHT,
        min=0.0, max=5.0, subtype="DISTANCE", update=_push_material_height,
        description="Resting thickness of the material layer")

    collider_collection: bpy.props.PointerProperty(
        name="Colliders", type=bpy.types.Collection,
        update=_push_collider_collection,
        description="Collection of objects that carve this material")

    collider_active: bpy.props.IntProperty(
        name="Active Collider", default=0,
        description="Selected row in the collider list")


classes = (
    GroundFXObjectSettings,
)


def register_pointers():
    bpy.types.Object.groundfx = bpy.props.PointerProperty(
        type=GroundFXObjectSettings)


def unregister_pointers():
    if hasattr(bpy.types.Object, "groundfx"):
        del bpy.types.Object.groundfx
