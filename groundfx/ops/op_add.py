# SPDX-License-Identifier: GPL-3.0-or-later
"""Add Sand / Snow / Mud — one click to a working domain.

Creates a grid mesh at the 3D cursor, attaches the ground-simulation modifier,
seeds sensible per-element defaults, and files the object under the GroundFX
collection. This is the E2 deliverable; the material assignment is a stub until
the shaders land in E8.
"""
from __future__ import annotations

import bpy

from ..core import modifier_io
from ..core.constants import (
    ELEMENTS, ELEMENT_LABELS, MODIFIER_NAME, COLLECTION_NAME,
    PROP_IS_DOMAIN, PROP_ELEMENT, OP_PREFIX,
    DEFAULT_DOMAIN_SIZE, QUALITY_MEDIUM,
)
from ..core.ng_library import ensure_node_group
from ..core.nodegroups import ng_ground_sim as gsim
from ..data import quality as qmod
from ..data import elements as emod
from ..utils import log


def get_groundfx_collection(context) -> bpy.types.Collection:
    """Return the top-level GroundFX collection, creating it if absent."""
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION_NAME)
        context.scene.collection.children.link(coll)
    return coll


def _make_grid_mesh(name: str, size: float, resolution: int) -> bpy.types.Mesh:
    """Build a flat grid mesh directly (no bpy.ops, so it works headless)."""
    import numpy as np

    n = resolution + 1
    xs = (np.linspace(0.0, 1.0, n) - 0.5) * size
    grid_x, grid_y = np.meshgrid(xs, xs)
    verts = np.column_stack(
        (grid_x.ravel(), grid_y.ravel(), np.zeros(n * n)))

    # Quad faces.
    idx = np.arange(n * n).reshape(n, n)
    v0 = idx[:-1, :-1].ravel()
    v1 = idx[:-1, 1:].ravel()
    v2 = idx[1:, 1:].ravel()
    v3 = idx[1:, :-1].ravel()
    faces = np.column_stack((v0, v1, v2, v3))

    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.ravel())
    mesh.loops.add(faces.size)
    mesh.polygons.add(len(faces))
    mesh.loops.foreach_set("vertex_index", faces.ravel())
    mesh.polygons.foreach_set("loop_start", np.arange(0, faces.size, 4))
    mesh.polygons.foreach_set("loop_total", np.full(len(faces), 4))
    # Smooth shading: a displaced height field reads as faceted spikes when
    # flat-shaded; smooth normals make berms and slopes look continuous (B2).
    mesh.polygons.foreach_set("use_smooth", np.ones(len(faces), dtype=bool))
    mesh.update()
    mesh.validate()
    return mesh


def create_domain(context, element: str,
                  size: float = DEFAULT_DOMAIN_SIZE) -> bpy.types.Object:
    """Create and return a fully wired GroundFX domain object."""
    quality_key = QUALITY_MEDIUM
    prof = qmod.profile(quality_key)

    name = f"GroundFX_{ELEMENT_LABELS[element]}"
    mesh = _make_grid_mesh(name, size, prof.resolution)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = context.scene.cursor.location

    get_groundfx_collection(context).objects.link(obj)

    # Node group + modifier.
    tree = ensure_node_group(gsim.NG_GROUND_SIM, gsim.build)
    modifier_io.invalidate(tree.name)
    md = obj.modifiers.new(MODIFIER_NAME, "NODES")
    md.node_group = tree

    # Object-level settings.
    st = obj.groundfx
    st.is_domain = True
    st.element = element
    st.quality = quality_key
    st.domain_size = size
    obj[PROP_IS_DOMAIN] = True
    obj[PROP_ELEMENT] = element

    # Seed modifier inputs from element physics + quality/grid geometry.
    ed = emod.defaults(element)
    modifier_io.set_input(md, gsim.IN_MATERIAL_HEIGHT, st.material_height, tag=False)
    modifier_io.set_input(md, gsim.IN_REPOSE, ed.repose_rad, tag=False)
    modifier_io.set_input(md, gsim.IN_COHESION, ed.cohesion, tag=False)
    modifier_io.set_input(md, gsim.IN_FLOW, ed.flow_rate, tag=False)
    modifier_io.set_input(md, gsim.IN_RELAX_ITERS, prof.relax_iterations, tag=False)
    modifier_io.set_input(md, gsim.IN_CELL_SIZE, size / prof.resolution, tag=False)
    modifier_io.set_input(md, gsim.IN_GRID_N, prof.resolution + 1, tag=False)
    modifier_io.set_input(md, gsim.IN_DISPLACE_RATIO, 0.7, tag=False)
    modifier_io.set_input(md, gsim.IN_DEPOSIT_ITERS, 6, tag=False)
    modifier_io.set_input(md, gsim.IN_CARVE_SUBSTEPS, prof.substeps, tag=False)
    modifier_io.set_input(md, gsim.IN_STICKINESS, ed.stickiness, tag=False)
    modifier_io.set_input(md, gsim.IN_RECOVERY, ed.recovery, tag=False)
    modifier_io.set_input(md, gsim.IN_BOW_WAVE, ed.bow_wave, tag=True)
    st.stickiness = ed.stickiness

    # Procedural material (E8): seed the Look sliders from the element defaults
    # and build/assign the matching material.
    from ..core.materials import mat_builder as matb
    look = matb.look_defaults(element)
    st.look_base_color = look.base_color
    st.look_roughness = look.roughness
    st.look_detail = look.detail
    st.wetness = look.base_wetness
    modifier_io.set_input(md, gsim.IN_COHESION,
                          min(1.0, ed.cohesion + 0.4 * look.base_wetness),
                          tag=False)
    mat = matb.build_material(
        element, base_color=look.base_color, roughness=look.roughness,
        detail=look.detail, wetness=look.base_wetness)
    matb.assign_material(obj, mat)

    # Auto-create the (empty) collider collection and wire it, so the user can
    # start marking colliders straight away (E4-T2). Lazy import avoids a
    # module-load cycle with op_collider.
    from .op_collider import ensure_collider_collection
    ensure_collider_collection(context, obj)

    log.info("created %s domain (%d^2, %.2f m, cell %.3f m)",
             element, prof.resolution, size, size / prof.resolution)
    return obj


def conform_grid_to_terrain(obj, terrain, context) -> int:
    """Drop each grid vertex onto ``terrain`` so the material rests on it.

    Casts a ray straight down from high above every grid point against the
    terrain's evaluated surface (via a BVH tree in world space) and sets the
    vertex height to the hit. Points that miss (outside the terrain) keep their
    flat height. Done once at build time — the solver reads this as ``gfx_base``,
    so no per-frame cost. Returns the number of vertices that hit (E2-T6/T7).
    """
    from mathutils.bvhtree import BVHTree

    deps = context.evaluated_depsgraph_get()
    ev = terrain.evaluated_get(deps)
    tmw = ev.matrix_world
    verts = [tmw @ v.co for v in ev.data.vertices]
    polys = [tuple(p.vertices) for p in ev.data.polygons]
    if not polys:
        return 0
    bvh = BVHTree.FromPolygons(verts, polys)

    ow = obj.matrix_world
    owi = ow.inverted()
    me = obj.data
    top = 1.0e4
    hits = 0
    for v in me.vertices:
        wp = ow @ v.co
        loc, _nrm, _idx, _dist = bvh.ray_cast((wp.x, wp.y, top), (0.0, 0.0, -1.0))
        if loc is not None:
            v.co.z = (owi @ loc).z
            hits += 1
    me.update()
    return hits


def expected_vertex_count(obj) -> int:
    """How many vertices the domain's grid should have at its quality."""
    return (qmod.profile(obj.groundfx.quality).resolution + 1) ** 2


def grid_is_current(obj) -> bool:
    """True if the mesh resolution matches the selected quality + size."""
    return obj.data is not None and len(obj.data.vertices) == expected_vertex_count(obj)


def rebuild_grid(obj) -> bool:
    """Rebuild the domain mesh at the current quality/size, re-pushing inputs.

    Changing Quality or Domain Size only moves numbers until the actual grid is
    rebuilt — the solver runs on whatever mesh it was given. This swaps in a
    fresh grid at the selected resolution, carries the GroundFX material across
    the mesh swap, and re-seeds the resolution-dependent solver inputs. The sim
    resets (new topology), which is the expected cost of changing resolution.
    """
    from ..core.materials import mat_builder as matb

    st = obj.groundfx
    md = obj.modifiers.get(MODIFIER_NAME)
    if md is None:
        return False
    prof = qmod.profile(st.quality)
    size = st.domain_size

    mat = matb.domain_material(obj)          # survive the mesh swap
    old = obj.data
    obj.data = _make_grid_mesh(obj.name, size, prof.resolution)
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    if mat is not None:
        matb.assign_material(obj, mat)
    # Conform to a terrain if one is set (E2-S2).
    terrain = st.terrain
    if terrain is not None and terrain is not obj:
        conform_grid_to_terrain(obj, terrain, bpy.context)

    modifier_io.set_input(md, gsim.IN_CELL_SIZE, size / prof.resolution, tag=False)
    modifier_io.set_input(md, gsim.IN_GRID_N, prof.resolution + 1, tag=False)
    modifier_io.set_input(md, gsim.IN_RELAX_ITERS, prof.relax_iterations, tag=False)
    modifier_io.set_input(md, gsim.IN_CARVE_SUBSTEPS, prof.substeps, tag=True)
    log.info("rebuilt %s grid: %d^2 (%.2f m, cell %.3f m)",
             obj.name, prof.resolution, size, size / prof.resolution)
    return True


def push_all_inputs(obj) -> bool:
    """Re-seed every solver input on ``obj`` from its current settings.

    Used by the repair path: after a node group is rebuilt (or a modifier
    recreated) the inputs need re-pushing. Physics with no per-object property
    (repose/cohesion/flow/bow) resets to the element defaults — a broken setup
    has no values to preserve, so element defaults are the sane recovery.
    """
    from ..core.materials import mat_builder as matb

    md = obj.modifiers.get(MODIFIER_NAME)
    if md is None or md.node_group is None:
        return False
    st = obj.groundfx
    prof = qmod.profile(st.quality)
    size = st.domain_size
    ed = emod.defaults(st.element)
    coh = min(1.0, ed.cohesion + 0.4 * st.wetness)  # wetness coupling (E8-T7)

    set = modifier_io.set_input
    set(md, gsim.IN_MATERIAL_HEIGHT, st.material_height, tag=False)
    set(md, gsim.IN_REPOSE, ed.repose_rad, tag=False)
    set(md, gsim.IN_COHESION, coh, tag=False)
    set(md, gsim.IN_FLOW, ed.flow_rate, tag=False)
    set(md, gsim.IN_RELAX_ITERS, prof.relax_iterations, tag=False)
    set(md, gsim.IN_CELL_SIZE, size / prof.resolution, tag=False)
    set(md, gsim.IN_GRID_N, prof.resolution + 1, tag=False)
    set(md, gsim.IN_DISPLACE_RATIO, 0.7, tag=False)
    set(md, gsim.IN_DEPOSIT_ITERS, 6, tag=False)
    set(md, gsim.IN_CARVE_SUBSTEPS, prof.substeps, tag=False)
    set(md, gsim.IN_STICKINESS, st.stickiness, tag=False)
    set(md, gsim.IN_RECOVERY, ed.recovery, tag=False)
    set(md, gsim.IN_BOW_WAVE, ed.bow_wave, tag=False)
    set(md, gsim.IN_CONTACT_AA, 1.0 if st.hero_contact else 0.0, tag=False)
    if st.collider_collection is not None:
        set(md, gsim.IN_COLLIDER_COLLECTION, st.collider_collection, tag=True)
    return True


def repair_domain(obj, context) -> bool:
    """Rebuild the node group and re-wire the modifier for a domain (E1-T9).

    Fixes the common breakages: a modifier whose node group was deleted, an
    out-of-date group (rebuilt by ``ensure_node_group``), or a missing modifier.
    """
    from ..core.materials import mat_builder as matb

    tree = ensure_node_group(gsim.NG_GROUND_SIM, gsim.build)
    modifier_io.invalidate(tree.name)
    md = obj.modifiers.get(MODIFIER_NAME)
    if md is None:
        md = obj.modifiers.new(MODIFIER_NAME, "NODES")
    md.node_group = tree
    push_all_inputs(obj)
    # A domain with no GroundFX material gets one back (unless the user has
    # their own material in the slot).
    if matb.domain_material(obj) is None and not obj.material_slots:
        matb.assign_material(obj, matb.build_material(obj.groundfx.element))
    return True


class GFX_OT_repair(bpy.types.Operator):
    """Rebuild broken or outdated GroundFX node setups"""

    bl_idname = f"{OP_PREFIX}.repair"
    bl_label = "Repair Node Setup"
    bl_options = {"REGISTER", "UNDO"}

    all_domains: bpy.props.BoolProperty(name="All Domains", default=False)

    def execute(self, context):
        if self.all_domains:
            domains = [o for o in context.scene.objects
                       if getattr(o.groundfx, "is_domain", False)]
        else:
            obj = context.active_object
            domains = [obj] if obj and getattr(obj.groundfx, "is_domain", False) \
                else []
        if not domains:
            self.report({"WARNING"}, "No GroundFX domain to repair")
            return {"CANCELLED"}
        for obj in domains:
            repair_domain(obj, context)
        self.report({"INFO"}, f"Repaired {len(domains)} domain(s)")
        return {"FINISHED"}


class GFX_OT_rebuild_grid(bpy.types.Operator):
    """Rebuild the grid at the current Quality and Domain Size"""

    bl_idname = f"{OP_PREFIX}.rebuild_grid"
    bl_label = "Rebuild Grid"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and getattr(obj.groundfx, "is_domain", False)

    def execute(self, context):
        obj = context.active_object
        if rebuild_grid(obj):
            prof = qmod.profile(obj.groundfx.quality)
            self.report({"INFO"}, f"Grid rebuilt at {prof.resolution}²")
        else:
            self.report({"WARNING"}, "No GroundFX modifier to rebuild")
        return {"FINISHED"}


class GFX_OT_add_ground(bpy.types.Operator):
    """Add a GroundFX domain of the given element at the 3D cursor"""

    bl_idname = f"{OP_PREFIX}.add_ground"
    bl_label = "Add GroundFX Ground"
    bl_options = {"REGISTER", "UNDO"}

    element: bpy.props.EnumProperty(
        name="Element",
        items=[(k, ELEMENT_LABELS[k], "") for k in ELEMENTS],
        default=ELEMENTS[0],
    )

    def execute(self, context):
        obj = create_domain(context, self.element)
        # Select and activate the new domain.
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self.report({"INFO"}, f"Added {ELEMENT_LABELS[self.element]} domain")
        return {"FINISHED"}


classes = (
    GFX_OT_add_ground,
    GFX_OT_rebuild_grid,
    GFX_OT_repair,
)
