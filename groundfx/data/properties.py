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
    ELEMENTS, ELEMENT_LABELS, QUALITY_LEVELS, MODIFIER_NAME, PROP_ELEMENT,
    PROP_IS_COLLIDER, DEFAULT_DOMAIN_SIZE, DEFAULT_MATERIAL_HEIGHT,
    PROXY_MODES, PROXY_MODE_LABELS,
)
from ..core.nodegroups import ng_ground_sim as gsim
from ..core.materials import mat_builder as matb
from ..data import quality as qmod
from ..data import elements as emod

# Extra cohesion at full wetness: the wetness slider stiffens the material as it
# darkens it, so one control moves both physics and look (E8-T7).
_WET_COHESION_GAIN = 0.4

# Guards the look/element callbacks against re-entrancy while a switch rewrites
# several properties in a row.
_look_guard = False


def _effective_cohesion(element, wetness):
    ed = emod.defaults(element)
    return min(1.0, ed.cohesion + _WET_COHESION_GAIN * float(wetness))


def _element_items(self, context):
    return [(k, ELEMENT_LABELS[k], f"{ELEMENT_LABELS[k]} material") for k in ELEMENTS]


def _quality_items(self, context):
    return [(k, qmod.profile(k).label,
             f"{qmod.profile(k).label} quality "
             f"({qmod.profile(k).resolution}^2)") for k in QUALITY_LEVELS]


def _domain_modifier(obj):
    return obj.modifiers.get(MODIFIER_NAME) if obj else None


def _push_element(self, context):
    """Switch the material: push the new element's physics to the solver (E5-S1).

    The shader swap lands in E8; for now the physics parameters change
    atomically so the behaviour matches the chosen element immediately.
    """
    global _look_guard
    obj = self.id_data
    obj[PROP_ELEMENT] = self.element
    md = _domain_modifier(obj)
    if not md:
        return
    ed = emod.defaults(self.element)
    look = matb.look_defaults(self.element)
    emod.push_physics(md, ed, tag=False)

    # Reset the Look to the new element's defaults (snow should look like snow),
    # then rebuild the material from those — but only if the domain still wears
    # a GroundFX material; a user's own material is left alone (E8-T10).
    _look_guard = True
    self.wetness = look.base_wetness
    self.look_base_color = look.base_color
    self.look_roughness = look.roughness
    self.look_detail = look.detail
    self.stickiness = ed.stickiness
    # The airborne phase belongs to the full look: a bare domain stays bare.
    self.spray = ed.spray if self.surface_detail else 0.0
    _look_guard = False
    modifier_io.set_input(md, gsim.IN_STICKINESS, ed.stickiness, tag=False)
    modifier_io.set_input(md, gsim.IN_RECOVERY, ed.recovery, tag=False)
    modifier_io.set_input(md, gsim.IN_COHESION,
                          _effective_cohesion(self.element, self.wetness),
                          tag=True)
    if matb.domain_material(obj) is not None or not obj.material_slots:
        mat = matb.build_material(
            self.element, base_color=look.base_color, roughness=look.roughness,
            detail=look.detail, wetness=look.base_wetness)
        matb.assign_material(obj, mat)
    _sync_surface(self, context)


def _sync_surface(self, context):
    """Surface stage on/off and its inputs, plus the shader's copy of the
    ripple parameters (geometry and shading use the same function)."""
    obj = self.id_data
    from ..ops.op_surface import sync_surface
    from ..ops.op_spray import sync_spray
    sync_surface(obj)
    sync_spray(obj)        # stays the last stage, after the surface
    _sync_coats(self, context)
    matb.update_controls(matb.domain_material(obj),
                         ripple_length=self.ripple_length,
                         ripple_height=self.ripple_height,
                         wind=self.wind_direction)


def _sync_spray(self, context):
    """Airborne phase: solver input and the grain display stage."""
    if _look_guard:
        return
    obj = self.id_data
    if not self.is_domain:
        return
    from ..ops.op_spray import sync_spray
    sync_spray(obj)


def _sync_coats(self, context):
    """Coat objects follow the collider list, the element and the toggle."""
    obj = self.id_data
    if not self.is_domain:
        return
    from ..ops.op_coat import sync_coats
    sync_coats(context or bpy.context, obj)


def _push_drying(self, context):
    md = _domain_modifier(self.id_data)
    if md:
        modifier_io.set_input(md, gsim.IN_DRYING, self.drying)


# Guards the pick callback against the recursion of clearing its own pointer.
_pick_guard = False


def _pick_collider(self, context):
    """Add the picked object to this domain's collider collection (B3).

    Lets the user add a collider straight from an eyedropper/search field
    instead of selecting it and running the operator. The field resets to empty
    so the next pick fires again.
    """
    global _pick_guard
    if _pick_guard:
        return
    domain = self.id_data
    picked = self.collider_pick
    if picked is None:
        return
    if picked is not domain and not picked.groundfx.is_domain \
            and picked.groundfx.proxy_source is None:
        from ..ops.op_collider import ensure_collider_collection
        coll = ensure_collider_collection(context, domain)
        if picked.name not in coll.objects:
            coll.objects.link(picked)
        picked.groundfx.is_collider = True
        picked[PROP_IS_COLLIDER] = True
        domain.update_tag()
        _sync_coats(self, context)
    _pick_guard = True
    self.collider_pick = None
    _pick_guard = False


def _push_material_height(self, context):
    obj = self.id_data
    md = _domain_modifier(obj)
    if md:
        modifier_io.set_input(md, gsim.IN_MATERIAL_HEIGHT, self.material_height)
        from ..ops.op_surface import push_surface_inputs
        push_surface_inputs(obj)


def _push_collider_collection(self, context):
    obj = self.id_data
    md = _domain_modifier(obj)
    if md:
        modifier_io.set_input(md, gsim.IN_COLLIDER_COLLECTION,
                              self.collider_collection)


def _push_hero_contact(self, context):
    obj = self.id_data
    md = _domain_modifier(obj)
    if md:
        modifier_io.set_input(md, gsim.IN_CONTACT_AA,
                              1.0 if self.hero_contact else 0.0)


def _push_stickiness(self, context):
    """Push the static-friction margin into the solver (P1)."""
    if _look_guard:
        return
    md = _domain_modifier(self.id_data)
    if md:
        modifier_io.set_input(md, gsim.IN_STICKINESS, self.stickiness)


def _push_look(self, context):
    """Push the colour/roughness/detail sliders into the domain material."""
    if _look_guard:
        return
    matb.update_controls(matb.domain_material(self.id_data),
                         base_color=self.look_base_color,
                         roughness=self.look_roughness,
                         detail=self.look_detail)


def _push_wetness(self, context):
    """Wetness moves both look (darker, glossier) and physics (cohesion)."""
    if _look_guard:
        return
    obj = self.id_data
    matb.update_controls(matb.domain_material(obj), wetness=self.wetness)
    md = _domain_modifier(obj)
    if md:
        modifier_io.set_input(md, gsim.IN_COHESION,
                              _effective_cohesion(self.element, self.wetness))


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

    coat_source: bpy.props.PointerProperty(
        name="Coat Source", type=bpy.types.Object,
        description="Set on a coat object; the collider it coats")

    coat_domain: bpy.props.PointerProperty(
        name="Coat Domain", type=bpy.types.Object,
        description="Set on a coat object; the domain whose material it is")

    coat_colliders: bpy.props.BoolProperty(
        name="Cling To Colliders", default=True, update=_sync_coats,
        description="Material sticks to the flanks of colliders: grains "
                    "where they were buried, spatter while they move")

    proxy_source: bpy.props.PointerProperty(
        name="Proxy Source", type=bpy.types.Object,
        description="Set on a proxy object; points at the collider it stands in for")

    element: bpy.props.EnumProperty(
        name="Element", items=_element_items, update=_push_element,
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

    measured_ms: bpy.props.FloatProperty(
        name="Measured ms/frame", default=-1.0,
        description="Last benchmark result (negative = not measured yet)")

    collider_pick: bpy.props.PointerProperty(
        name="Add Collider", type=bpy.types.Object, update=_pick_collider,
        description="Pick an object to add it to this domain's colliders")

    hero_contact: bpy.props.BoolProperty(
        name="Hero Contact", default=False, update=_push_hero_contact,
        description="Supersample the contact edge for a silhouette-accurate "
                    "imprint (product/hero shots). Costs more per frame")

    terrain: bpy.props.PointerProperty(
        name="Terrain", type=bpy.types.Object,
        description="Ground the material rests on: the grid conforms to this "
                    "object's surface on Rebuild (empty = flat plane)")

    # --- Look (E8): four sliders that drive the generated material ----------
    look_base_color: bpy.props.FloatVectorProperty(
        name="Base Color", subtype="COLOR", size=3, min=0.0, max=1.0,
        default=(0.60, 0.47, 0.29), update=_push_look,
        description="Dry albedo of the material")

    look_roughness: bpy.props.FloatProperty(
        name="Roughness", default=0.85, min=0.0, max=1.0, update=_push_look,
        description="Surface roughness when dry (wetness lowers it)")

    look_detail: bpy.props.FloatProperty(
        name="Detail", default=0.5, min=0.0, max=2.0, update=_push_look,
        description="Strength of the procedural grain bump")

    wetness: bpy.props.FloatProperty(
        name="Wetness", default=0.0, min=0.0, max=1.0, update=_push_wetness,
        description="Moisture: darkens and glosses the look and stiffens the "
                    "material (raises cohesion) at the same time")

    # --- Surface stage (gen 3): meso relief between cell and grain ----------
    surface_detail: bpy.props.BoolProperty(
        name="Surface Detail", default=False, update=_sync_surface,
        description="Display stage after the solver: subdivides the grid in "
                    "renders and adds ripples and the relief of disturbed "
                    "material as real geometry")

    ripple_height: bpy.props.FloatProperty(
        name="Ripple Height", default=matb.RIPPLE_HEIGHT, min=0.0, max=0.05,
        subtype="DISTANCE", update=_sync_surface,
        description="Crest-to-trough height of the wind ripples on "
                    "undisturbed material (0 = smooth)")

    ripple_length: bpy.props.FloatProperty(
        name="Ripple Length", default=matb.RIPPLE_LENGTH, min=0.01, max=1.0,
        subtype="DISTANCE", update=_sync_surface,
        description="Distance from crest to crest")

    wind_direction: bpy.props.FloatProperty(
        name="Wind Direction", default=matb.WIND_ANGLE, subtype="ANGLE",
        update=_sync_surface,
        description="Direction the wind blows; ripple crests run across it")

    clod_height: bpy.props.FloatProperty(
        name="Clod Height", default=0.004, min=0.0, max=0.05,
        subtype="DISTANCE", update=_sync_surface,
        description="Relief of material the simulation has disturbed")

    pebbles: bpy.props.FloatProperty(
        name="Pebbles", default=140.0, min=0.0, max=20000.0,
        update=_sync_surface,
        description="Small stones and shell fragments per square metre")

    undulation: bpy.props.FloatProperty(
        name="Undulation", default=0.012, min=0.0, max=0.1,
        subtype="DISTANCE", update=_sync_surface,
        description="Broad unevenness of the resting surface. Hollows "
                    "fill with water")

    water: bpy.props.BoolProperty(
        name="Standing Water", default=True, update=_sync_surface,
        description="A water table that fills hollows and every track")

    water_level: bpy.props.FloatProperty(
        name="Water Level", default=-0.004, min=-1.0, max=1.0,
        subtype="DISTANCE", update=_sync_surface,
        description="Water table relative to the resting surface. Higher "
                    "floods more of the ground")

    surround: bpy.props.BoolProperty(
        name="Surround", default=False, update=_sync_surface,
        description="Embed the domain in a large static field of the same "
                    "material, out to the horizon")

    drying: bpy.props.FloatProperty(
        name="Drying", default=0.006, min=0.0, max=1.0, update=_push_drying,
        description="How fast freshly dug-up (darker, damp) material dries "
                    "per frame. 0 keeps every track dark")

    # --- Spray (gen 4): material that leaves the ground ---------------------
    spray: bpy.props.FloatProperty(
        name="Spray", default=0.0, min=0.0, max=1.0, update=_sync_spray,
        description="Share of fast-displaced material that leaves the "
                    "ground and flies. 0 keeps everything in the bed")

    spray_lift: bpy.props.FloatProperty(
        name="Lift", default=1.0, min=0.0, max=3.0, update=_sync_spray,
        description="How steeply thrown material leaves the ground")

    spray_grain: bpy.props.FloatProperty(
        name="Grain Size", default=0.0005, min=0.00005, max=0.02,
        subtype="DISTANCE", update=_sync_spray,
        description="Diameter of a typical airborne grain")

    spray_detail: bpy.props.FloatProperty(
        name="Detail", default=1.0, min=0.01, max=4.0, update=_sync_spray,
        description="Grains drawn per real grain in renders. 1 shows about "
                    "as many as real sand would; lower is faster, each "
                    "grain then gets larger")

    stickiness: bpy.props.FloatProperty(
        name="Stickiness", default=0.05, min=0.0, max=1.0,
        update=_push_stickiness,
        description="Static friction: how far past the repose angle the "
                    "material holds before it starts to flow. Higher = stays "
                    "caught in grooves, heaps sit without draining flat")


classes = (
    GroundFXObjectSettings,
)


def register_pointers():
    bpy.types.Object.groundfx = bpy.props.PointerProperty(
        type=GroundFXObjectSettings)
    # Scene-wide flag: whether the Live Sculpt modal is currently running. The
    # panel button reads it (depress state) and a second click clears it.
    bpy.types.Scene.gfx_live_active = bpy.props.BoolProperty(
        name="Live Sculpt Active", default=False)


def unregister_pointers():
    if hasattr(bpy.types.Object, "groundfx"):
        del bpy.types.Object.groundfx
    if hasattr(bpy.types.Scene, "gfx_live_active"):
        del bpy.types.Scene.gfx_live_active
