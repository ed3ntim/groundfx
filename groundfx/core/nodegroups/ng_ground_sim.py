# SPDX-License-Identifier: GPL-3.0-or-later
"""The ground simulation node group.

M1 scope — a minimal but *real* solver: it establishes the material layer,
then each frame carves the surface down where a collider intrudes, so a moving
object leaves a visible trench. Piling (E3-S3), slope relaxation (E3-S2) and
multi-collider support (E4) extend this same group later; the interface is
already shaped for them.

Carve trick: cast a ray straight up from just below the base. The first hit is
the collider's *underside*. If that underside sits below the current material
surface, the surface is pushed down to it. No Python runs per frame — the whole
thing is nodes, so it bakes.

Verified against Blender 5.2.
"""
from __future__ import annotations

import bpy

import math

from ..ng_builder import NodeTreeBuilder, new_geometry_group
from ..ng_zones import make_simulation_zone
from . import ng_relax
from . import ng_deposit
from ..constants import (
    NG_GROUND_SIM, ATTR_HEIGHT, ATTR_BASE, ATTR_CARVE, ATTR_CARVE_PREV,
    ATTR_OCC, ATTR_OCC_PREV, ATTR_PILE, ATTR_COMP, DEFAULT_MATERIAL_HEIGHT,
)

# Group input socket names (also used by the property/socket mapping).
IN_GEOMETRY = "Geometry"
IN_MATERIAL_HEIGHT = "Material Height"
IN_COLLIDER_COLLECTION = "Colliders"
IN_COLLIDER_OFFSET = "Collider Offset"
IN_CONTACT_AA = "Contact AA"
IN_CARVE_SUBSTEPS = "Carve Substeps"
IN_REPOSE = "Angle Of Repose"
IN_COHESION = "Cohesion"
IN_FLOW = "Flow Rate"
IN_RELAX_ITERS = "Relax Iterations"
IN_CELL_SIZE = "Cell Size"
IN_GRID_N = "Grid N"
IN_DISPLACE_RATIO = "Displacement Ratio"
IN_DEPOSIT_ITERS = "Deposit Iterations"
IN_DEPOSIT_SPREAD = "Deposit Spread"
IN_DEPOSIT_RATE = "Deposit Rate"
IN_BOW_WAVE = "Bow Wave"
OUT_GEOMETRY = "Geometry"

_RAY_LENGTH = 10.0  # metres; ample for the close-up domain scale

# Tolerance for "the collider is touching this cell" (metres). Large enough to
# survive the raycast's own precision, far below anything visible.
_CONTACT_EPS = 1e-4

# The swept carve is unrolled to this many taps and masked down to the live
# ``Carve Substeps`` count. Four covers the quality ladder (ultra = 3) with a
# spare; a substep count above it just clamps to four taps.
_MAX_SUBSTEPS = 4


def _store_float(b, geo_socket_node, geo_key, name, value_node, value_key):
    """Append a Store Named Attribute(FLOAT, POINT) to the geometry chain."""
    store = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                  domain="POINT", inputs={"Name": name})
    b.link(geo_socket_node, geo_key, store, "Geometry")
    b.link(value_node, value_key, store, "Value")
    return store


def build(name: str = NG_GROUND_SIM) -> bpy.types.GeometryNodeTree:
    tree = new_geometry_group(name)
    b = NodeTreeBuilder(tree)

    # -- interface ----------------------------------------------------------
    b.input(IN_GEOMETRY, "NodeSocketGeometry")
    b.input(IN_MATERIAL_HEIGHT, "NodeSocketFloat",
            default=DEFAULT_MATERIAL_HEIGHT, min=0.0, max=5.0,
            subtype="DISTANCE",
            description="Resting thickness of the material layer")
    b.input(IN_COLLIDER_COLLECTION, "NodeSocketCollection",
            description="Collection of objects that carve the material; the "
                        "ray targets the union of everything inside it")
    b.input(IN_COLLIDER_OFFSET, "NodeSocketFloat", default=0.0,
            min=-0.5, max=0.5, subtype="DISTANCE",
            description="Penetration tolerance added to the collider surface")
    b.input(IN_CONTACT_AA, "NodeSocketFloat", default=0.0, min=0.0, max=1.0,
            description="Hero mode: sub-cell supersampling of the contact edge "
                        "(0 = one ray/vertex, 1 = anti-aliased silhouette)")
    b.input(IN_CARVE_SUBSTEPS, "NodeSocketInt", default=1, min=1, max=8,
            description="Sub-frame carve samples along the collider's motion. "
                        "1 = imprint only at this frame's position (fast objects "
                        "leave a dashed trench); higher fills the gap into a "
                        "continuous trench. No effect below one cell of motion")
    b.input(IN_REPOSE, "NodeSocketFloat", default=math.radians(34.0),
            min=0.0, max=math.radians(85.0), subtype="ANGLE",
            description="Angle of repose: the steepest stable slope")
    b.input(IN_COHESION, "NodeSocketFloat", default=0.02, min=0.0, max=1.0,
            description="Extra slope the material holds before flowing (yield)")
    b.input(IN_FLOW, "NodeSocketFloat", default=0.8, min=0.0, max=1.0,
            description="How fast excess material flows downhill")
    b.input(IN_RELAX_ITERS, "NodeSocketInt", default=4, min=0, max=64,
            description="Relaxation iterations per frame (quality-driven)")
    b.input(IN_CELL_SIZE, "NodeSocketFloat", default=0.0156, min=1e-5, max=10.0,
            subtype="DISTANCE",
            description="Grid cell size = domain size / resolution")
    b.input(IN_GRID_N, "NodeSocketInt", default=129, min=2, max=8192,
            description="Vertices per side = resolution + 1")
    b.input(IN_DISPLACE_RATIO, "NodeSocketFloat", default=0.7, min=0.0, max=1.0,
            description="Share of carved material that heaps up (rest compacts)")
    b.input(IN_DEPOSIT_ITERS, "NodeSocketInt", default=6, min=0, max=64,
            description="Iterations spreading displaced material to the rim")
    b.input(IN_DEPOSIT_SPREAD, "NodeSocketFloat", default=0.5, min=0.0, max=1.0,
            description="Share of a cell's displaced material that moves on per "
                        "deposit step (lower = more local berm). 1.0 decouples "
                        "the grid into a comb of one-cell teeth")
    b.input(IN_DEPOSIT_RATE, "NodeSocketFloat", default=0.5, min=0.01, max=1.0,
            description="Share of the material a free cell lays down as height "
                        "per deposit step (lower = wider, softer rim ramp)")
    b.input(IN_BOW_WAVE, "NodeSocketFloat", default=0.6, min=0.0, max=1.0,
            description="How strongly displaced material heaps up ahead of a "
                        "moving collider (0 = isotropic rim, 1 = full bow wave)")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")

    gin, gout = b.group_io()

    # -- initial state: set base = current Z, h = material height -----------
    pos = b.add("GeometryNodeInputPosition")
    sep = b.add("ShaderNodeSeparateXYZ")
    b.link(pos, "Position", sep, "Vector")

    init_base = _store_float(b, gin, IN_GEOMETRY, ATTR_BASE, sep, "Z")
    # h = Material Height (broadcast scalar) on every point.
    init_h = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                   domain="POINT", inputs={"Name": ATTR_HEIGHT})
    b.link(init_base, "Geometry", init_h, "Geometry")
    b.link(gin, IN_MATERIAL_HEIGHT, init_h, "Value")
    # pile and compaction start empty.
    zero = b.add("ShaderNodeValue", label="0")
    zero.outputs[0].default_value = 0.0
    init_pile = _store_float(b, init_h, "Geometry", ATTR_PILE, zero, "Value")
    init_comp = _store_float(b, init_pile, "Geometry", ATTR_COMP, zero, "Value")
    init_occ = _store_float(b, init_comp, "Geometry", ATTR_OCC, zero, "Value")

    # -- simulation zone (geometry state carries the attributes) ------------
    zone = make_simulation_zone(b, state_items=[])
    b.link(init_occ, "Geometry", zone.input, "Geometry")

    sim_geo = zone.input  # geometry available at the zone's input node output

    # Read previous-frame attributes.
    read_base = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                      inputs={"Name": ATTR_BASE})
    read_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_HEIGHT})

    # surface_old = base + h
    surface_old = b.add("ShaderNodeMath", operation="ADD",
                        label="surface = base + h")
    b.link(read_base, "Attribute", surface_old, 0)
    b.link(read_h, "Attribute", surface_old, 1)

    # Ray source well below base so it starts *under* any collider: cast up
    # from (x, y, base - RAY_LENGTH) to hit the collider's underside first.
    src_z = b.add("ShaderNodeMath", operation="SUBTRACT",
                  inputs={1: _RAY_LENGTH}, label="base - RAY_LENGTH")
    b.link(read_base, "Attribute", src_z, 0)
    pos2 = b.add("GeometryNodeInputPosition")
    sep2 = b.add("ShaderNodeSeparateXYZ")
    b.link(pos2, "Position", sep2, "Vector")
    # Union of every collider in the collection. Collection Info returns the
    # members as instances in the domain's local space (RELATIVE); Realize
    # Instances turns them into real geometry so the ray can hit any of them.
    # This is what lifts the M1 single-collider limit to arbitrary many (E4).
    coll_info = b.add("GeometryNodeCollectionInfo", transform_space="RELATIVE",
                      inputs={"Separate Children": False,
                              "Reset Children": False})
    b.link(gin, IN_COLLIDER_COLLECTION, coll_info, "Collection")
    realize = b.add("GeometryNodeRealizeInstances")
    b.link(coll_info, "Instances", realize, "Geometry")

    # --- supersampled contact carve (E4-S4, hero silhouettes) --------------
    # One ray per vertex hard-quantises the imprint edge to the grid, which
    # facets a product's silhouette at close-up scale. We instead cast a
    # quincunx of five rays spread up to half a cell and average the resulting
    # surface, so a cell that the collider only partly covers carves partly:
    # the edge takes sub-cell coverage values and follows the real contour.
    # Contact AA scales the spread; at 0 all five samples collapse onto the
    # vertex, so the result is identical to the original single-ray carve.
    half = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.5},
                 label="0.5 * cell * AA")
    cell_aa = b.add("ShaderNodeMath", operation="MULTIPLY", label="cell * AA")
    b.link(gin, IN_CELL_SIZE, cell_aa, 0)
    b.link(gin, IN_CONTACT_AA, cell_aa, 1)
    b.link(cell_aa, "Value", half, 0)

    def _sample(oxm, oym):
        """One up-ray at vertex XY offset by (oxm,oym)*half.

        Returns ``(surface, covered)``: the surface this sample allows, and 1.0
        if the collider's underside sits at or below the old surface here, i.e.
        the collider *stands on* this spot. Averaging the five coverages gives
        a sub-cell coverage fraction, which is what the deposit and relaxation
        masks want — a footprint that does not flicker between frames.
        """
        if oxm == 0 and oym == 0:
            sx, sxk, sy, syk = sep2, "X", sep2, "Y"
        else:
            ox = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: oxm})
            b.link(half, "Value", ox, 0)
            oy = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: oym})
            b.link(half, "Value", oy, 0)
            sx = b.add("ShaderNodeMath", operation="ADD")
            b.link(sep2, "X", sx, 0)
            b.link(ox, "Value", sx, 1)
            sy = b.add("ShaderNodeMath", operation="ADD")
            b.link(sep2, "Y", sy, 0)
            b.link(oy, "Value", sy, 1)
            sxk, syk = "Value", "Value"
        srcv = b.add("ShaderNodeCombineXYZ")
        b.link(sx, sxk, srcv, "X")
        b.link(sy, syk, srcv, "Y")
        b.link(src_z, "Value", srcv, "Z")
        ray = b.add("GeometryNodeRaycast", data_type="FLOAT",
                    inputs={"Ray Length": 2.0 * _RAY_LENGTH,
                            "Ray Direction": (0.0, 0.0, 1.0)})
        b.link(realize, "Geometry", ray, "Target Geometry")
        b.link(srcv, "Vector", ray, "Source Position")
        hsep = b.add("ShaderNodeSeparateXYZ")
        b.link(ray, "Hit Position", hsep, "Vector")
        hz = b.add("ShaderNodeMath", operation="ADD", label="hit_z + offset")
        b.link(hsep, "Z", hz, 0)
        b.link(gin, IN_COLLIDER_OFFSET, hz, 1)
        cand = b.add("GeometryNodeSwitch", input_type="FLOAT")
        b.link(ray, "Is Hit", cand, "Switch")
        b.link(surface_old, "Value", cand, "False")
        b.link(hz, "Value", cand, "True")
        low = b.add("ShaderNodeMath", operation="MINIMUM")
        b.link(cand, "Output", low, 0)
        b.link(surface_old, "Value", low, 1)
        ns = b.add("ShaderNodeMath", operation="MAXIMUM", label="max(_, base)")
        b.link(low, "Value", ns, 0)
        b.link(read_base, "Attribute", ns, 1)
        # covered = hit AND underside <= old surface (+ a hair of tolerance)
        surf_tol = b.add("ShaderNodeMath", operation="ADD",
                         inputs={1: _CONTACT_EPS}, label="surface + eps")
        b.link(surface_old, "Value", surf_tol, 0)
        below = b.add("ShaderNodeMath", operation="LESS_THAN",
                      label="underside <= surface")
        b.link(hz, "Value", below, 0)
        b.link(surf_tol, "Value", below, 1)
        covered = b.add("GeometryNodeSwitch", input_type="FLOAT",
                        inputs={"False": 0.0}, label="covered")
        b.link(ray, "Is Hit", covered, "Switch")
        b.link(below, "Value", covered, "True")
        return ns, covered

    samples = [_sample(0, 0), _sample(1, 1), _sample(1, -1),
               _sample(-1, 1), _sample(-1, -1)]

    def _avg5(nodes, keys, label):
        a = b.add("ShaderNodeMath", operation="ADD")
        b.link(nodes[0], keys[0], a, 0)
        b.link(nodes[1], keys[1], a, 1)
        c = b.add("ShaderNodeMath", operation="ADD")
        b.link(nodes[2], keys[2], c, 0)
        b.link(nodes[3], keys[3], c, 1)
        ac = b.add("ShaderNodeMath", operation="ADD")
        b.link(a, "Value", ac, 0)
        b.link(c, "Value", ac, 1)
        total = b.add("ShaderNodeMath", operation="ADD", label="sum 5 samples")
        b.link(ac, "Value", total, 0)
        b.link(nodes[4], keys[4], total, 1)
        avg = b.add("ShaderNodeMath", operation="DIVIDE", inputs={1: 5.0},
                    label=label)
        b.link(total, "Value", avg, 0)
        return avg

    surf_q = _avg5([s[0] for s in samples], ["Value"] * 5, "surf @ frame pos")
    occupancy = _avg5([s[1] for s in samples], ["Output"] * 5, "coverage = avg")

    # --- swept carve (E3-S5 substeps) --------------------------------------
    # The carve above only imprints at the collider's position *this* frame, so
    # a collider crossing several cells per frame leaves a dashed trench: one
    # lump per frame, ripple period == per-frame travel (B2's residue). We fill
    # the gap by sampling the same imprint depth at a few sub-frame positions
    # along the motion and taking the deepest. Because pressing the collider in
    # cuts to a fixed underside, the depth at an intermediate position equals
    # the depth we just computed one motion-vector back -- so we do not need to
    # move any geometry: we read ``surf_q`` at grid cells offset by v*(t/T).
    #
    # v is the footprint centroid shift between frames (same estimator the bow
    # wave uses), gated to zero unless the collider had contact in *both* frames
    # so the first touch doesn't smear. When |v| < one cell the offsets round to
    # zero and every tap lands on the current cell, so the result is bit-for-bit
    # the single-position carve: slow motion is identical at any substep count
    # (E3-T21), and a still collider (Contact-AA path) is untouched.
    cell_node, cell_key = (gin, IN_CELL_SIZE)
    grid_node, grid_key = (gin, IN_GRID_N)
    subs_node, subs_key = (gin, IN_CARVE_SUBSTEPS)

    def _mask_gt(field_node, field_key, thresh, label):
        m = b.add("ShaderNodeMath", operation="GREATER_THAN",
                  inputs={1: thresh}, label=label)
        b.link(field_node, field_key, m, 0)
        return m

    def _centroid(sel_node, sel_key, axis_key):
        stat = b.add("GeometryNodeAttributeStatistic", data_type="FLOAT",
                     domain="POINT")
        b.link(sim_geo, "Geometry", stat, "Geometry")
        b.link(sel_node, sel_key, stat, "Selection")
        b.link(sep2, axis_key, stat, "Attribute")
        return stat

    occ_prev_attr = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                          inputs={"Name": ATTR_OCC})
    mask_now = _mask_gt(occupancy, "Value", 0.5, "covered now")
    mask_prev = _mask_gt(occ_prev_attr, "Attribute", 0.5, "covered before")
    cx_now = _centroid(mask_now, "Value", "X")
    cy_now = _centroid(mask_now, "Value", "Y")
    cx_prev = _centroid(mask_prev, "Value", "X")
    cy_prev = _centroid(mask_prev, "Value", "Y")

    def _delta(now_stat, prev_stat, label):
        d = b.add("ShaderNodeMath", operation="SUBTRACT", label=label)
        b.link(now_stat, "Mean", d, 0)
        b.link(prev_stat, "Mean", d, 1)
        return d

    vx_m = _delta(cx_now, cx_prev, "vx")
    vy_m = _delta(cy_now, cy_prev, "vy")
    # Gate: both frames must have touched, or v is meaningless (first contact).
    now_has = _mask_gt(mask_now, "Value", 0.5, "any contact now")
    now_hi = b.add("GeometryNodeAttributeStatistic", data_type="FLOAT",
                   domain="POINT")
    b.link(sim_geo, "Geometry", now_hi, "Geometry")
    b.link(occupancy, "Value", now_hi, "Attribute")
    prev_hi = b.add("GeometryNodeAttributeStatistic", data_type="FLOAT",
                    domain="POINT")
    b.link(sim_geo, "Geometry", prev_hi, "Geometry")
    b.link(occ_prev_attr, "Attribute", prev_hi, "Attribute")
    now_touch = _mask_gt(now_hi, "Max", 0.5, "touch now")
    prev_touch = _mask_gt(prev_hi, "Max", 0.5, "touch before")
    gate = b.add("ShaderNodeMath", operation="MULTIPLY", label="both touched")
    b.link(now_touch, "Value", gate, 0)
    b.link(prev_touch, "Value", gate, 1)

    def _v_cells(v_node, label):
        g = b.add("ShaderNodeMath", operation="MULTIPLY", label=f"{label} gated")
        b.link(v_node, "Value", g, 0)
        b.link(gate, "Value", g, 1)
        c = b.add("ShaderNodeMath", operation="DIVIDE", label=f"{label}/cell")
        b.link(g, "Value", c, 0)
        b.link(cell_node, cell_key, c, 1)
        return c

    vx_cells = _v_cells(vx_m, "vx")
    vy_cells = _v_cells(vy_m, "vy")

    # 1/T, computed once; the per-tap fraction is t * (1/T).
    inv_t = b.add("ShaderNodeMath", operation="DIVIDE", label="1/substeps")
    b.set_default(inv_t, 0, 1.0)
    b.link(subs_node, subs_key, inv_t, 1)

    # This cell's grid coordinates.
    idx = b.add("GeometryNodeInputIndex")
    col = b.add("ShaderNodeMath", operation="MODULO", label="col")
    b.link(idx, "Index", col, 0)
    b.link(grid_node, grid_key, col, 1)
    row_f = b.add("ShaderNodeMath", operation="DIVIDE")
    b.link(idx, "Index", row_f, 0)
    b.link(grid_node, grid_key, row_f, 1)
    row = b.add("ShaderNodeMath", operation="FLOOR", label="row")
    b.link(row_f, "Value", row, 0)

    def _in_range(coord_node, coord_key, label):
        """1.0 if 0 <= coord < N."""
        lo = b.add("ShaderNodeMath", operation="GREATER_THAN", inputs={1: -0.5},
                   label=f"{label}>=0")
        b.link(coord_node, coord_key, lo, 0)
        hi = b.add("ShaderNodeMath", operation="LESS_THAN", label=f"{label}<N")
        b.link(coord_node, coord_key, hi, 0)
        b.link(grid_node, grid_key, hi, 1)
        both = b.add("ShaderNodeMath", operation="MULTIPLY")
        b.link(lo, "Value", both, 0)
        b.link(hi, "Value", both, 1)
        return both

    def _tap(t, acc):
        """Fold one sub-frame sample at fraction t/T into the running minimum."""
        frac = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={0: float(t)},
                     label=f"frac {t}")
        b.link(inv_t, "Value", frac, 1)
        offx = b.add("ShaderNodeMath", operation="ROUND", label=f"offx {t}")
        ox = b.add("ShaderNodeMath", operation="MULTIPLY")
        b.link(vx_cells, "Value", ox, 0)
        b.link(frac, "Value", ox, 1)
        b.link(ox, "Value", offx, 0)
        offy = b.add("ShaderNodeMath", operation="ROUND", label=f"offy {t}")
        oy = b.add("ShaderNodeMath", operation="MULTIPLY")
        b.link(vy_cells, "Value", oy, 0)
        b.link(frac, "Value", oy, 1)
        b.link(oy, "Value", offy, 0)
        tcol = b.add("ShaderNodeMath", operation="ADD", label=f"tap col {t}")
        b.link(col, "Value", tcol, 0)
        b.link(offx, "Value", tcol, 1)
        trow = b.add("ShaderNodeMath", operation="ADD", label=f"tap row {t}")
        b.link(row, "Value", trow, 0)
        b.link(offy, "Value", trow, 1)
        tidx = b.add("ShaderNodeMath", operation="MULTIPLY_ADD",
                     label=f"tap idx {t}")
        b.link(trow, "Value", tidx, 0)
        b.link(grid_node, grid_key, tidx, 1)
        b.link(tcol, "Value", tidx, 2)
        sample = b.add("GeometryNodeSampleIndex", data_type="FLOAT",
                       domain="POINT", clamp=True)
        b.link(sim_geo, "Geometry", sample, "Geometry")
        b.link(surf_q, "Value", sample, "Value")
        b.link(tidx, "Value", sample, "Index")
        # valid = t <= T  AND  tap stays on the grid.
        active = b.add("ShaderNodeMath", operation="LESS_THAN",
                       inputs={0: float(t) - 0.5}, label=f"t<=T {t}")
        b.link(subs_node, subs_key, active, 1)
        in_c = _in_range(tcol, "Value", f"col {t}")
        in_r = _in_range(trow, "Value", f"row {t}")
        valid = b.add("ShaderNodeMath", operation="MULTIPLY", label=f"valid {t}")
        v_ar = b.add("ShaderNodeMath", operation="MULTIPLY")
        b.link(in_c, "Value", v_ar, 0)
        b.link(in_r, "Value", v_ar, 1)
        b.link(active, "Value", valid, 0)
        b.link(v_ar, "Value", valid, 1)
        # candidate = valid ? sample : surf_q  (so an invalid tap can't deepen)
        diff = b.add("ShaderNodeMath", operation="SUBTRACT")
        b.link(sample, "Value", diff, 0)
        b.link(surf_q, "Value", diff, 1)
        masked = b.add("ShaderNodeMath", operation="MULTIPLY")
        b.link(diff, "Value", masked, 0)
        b.link(valid, "Value", masked, 1)
        cand = b.add("ShaderNodeMath", operation="ADD", label=f"cand {t}")
        b.link(surf_q, "Value", cand, 0)
        b.link(masked, "Value", cand, 1)
        out = b.add("ShaderNodeMath", operation="MINIMUM", label=f"swept {t}")
        b.link(acc[0], acc[1], out, 0)
        b.link(cand, "Value", out, 1)
        return out, "Value"

    swept = (surf_q, "Value")
    for t in range(1, _MAX_SUBSTEPS + 1):
        swept = _tap(t, swept)
    new_surface = b.add("ShaderNodeMath", operation="ADD", inputs={1: 0.0},
                        label="swept surface")
    b.link(swept[0], swept[1], new_surface, 0)

    # new_h = new_surface - base ; carve = surface_old - new_surface
    new_h = b.add("ShaderNodeMath", operation="SUBTRACT", label="new_h")
    b.link(new_surface, "Value", new_h, 0)
    b.link(read_base, "Attribute", new_h, 1)
    carve = b.add("ShaderNodeMath", operation="SUBTRACT", label="carve")
    b.link(surface_old, "Value", carve, 0)
    b.link(new_surface, "Value", carve, 1)

    # Split carved material into displaced (heaps up) and compacted (packs down).
    displaced = b.add("ShaderNodeMath", operation="MULTIPLY",
                      label="carve * ratio")
    b.link(carve, "Value", displaced, 0)
    b.link(gin, IN_DISPLACE_RATIO, displaced, 1)
    compacted = b.add("ShaderNodeMath", operation="SUBTRACT",
                      label="carve - displaced")
    b.link(carve, "Value", compacted, 0)
    b.link(displaced, "Value", compacted, 1)

    # Accumulate pile and compaction onto their previous-frame values.
    prev_pile = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                      inputs={"Name": ATTR_PILE})
    acc_pile = b.add("ShaderNodeMath", operation="ADD", label="pile + displaced")
    b.link(prev_pile, "Attribute", acc_pile, 0)
    b.link(displaced, "Value", acc_pile, 1)
    prev_comp = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                      inputs={"Name": ATTR_COMP})
    acc_comp = b.add("ShaderNodeMath", operation="ADD", label="comp + compacted")
    b.link(prev_comp, "Attribute", acc_comp, 0)
    b.link(compacted, "Value", acc_comp, 1)

    # Store updated attributes. IMPORTANT: gfx_h is stored LAST. Named-attribute
    # fields re-evaluate against the geometry they flow through, so carve/pile/
    # comp (which read the *old* gfx_h via surface_old) must be stored before
    # gfx_h is overwritten, or they would re-read the already-carved height and
    # collapse to zero.
    # carve_prev := last frame's carve, captured BEFORE gfx_carve is
    # overwritten (E4-T9). The deposit step diffs the two to read off the
    # collider's motion direction for the bow wave.
    prev_carve = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                       inputs={"Name": ATTR_CARVE})
    store_carve_prev = _store_float(b, sim_geo, "Geometry", ATTR_CARVE_PREV,
                                    prev_carve, "Attribute")
    store_carve = _store_float(b, store_carve_prev, "Geometry", ATTR_CARVE,
                               carve, "Value")
    # Same shift for the coverage mask: occ_prev := last frame's occ, captured
    # before occ is overwritten. The deposit reads both to get the collider's
    # motion from the footprint's centroid shift.
    prev_occ = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                     inputs={"Name": ATTR_OCC})
    store_occ_prev = _store_float(b, store_carve, "Geometry", ATTR_OCC_PREV,
                                  prev_occ, "Attribute")
    store_occ = _store_float(b, store_occ_prev, "Geometry", ATTR_OCC,
                             occupancy, "Value")
    store_pile = _store_float(b, store_occ, "Geometry", ATTR_PILE,
                              acc_pile, "Value")
    store_comp = _store_float(b, store_pile, "Geometry", ATTR_COMP,
                              acc_comp, "Value")
    store_h = _store_float(b, store_comp, "Geometry", ATTR_HEIGHT, new_h, "Value")

    # --- deposit: displaced material heaps up at the rim -------------------
    deposit_node, deposit_key = ng_deposit.add_deposit(
        b, store_h, "Geometry",
        refs={
            "iterations": (gin, IN_DEPOSIT_ITERS),
            "grid_n": (gin, IN_GRID_N),
            "cell_size": (gin, IN_CELL_SIZE),
            "bow_wave": (gin, IN_BOW_WAVE),
            "spread": (gin, IN_DEPOSIT_SPREAD),
            "rate": (gin, IN_DEPOSIT_RATE),
        },
    )

    # --- relaxation: material flows to its angle of repose -----------------
    relax_node, relax_key = ng_relax.add_relaxation(
        b, deposit_node, deposit_key,
        refs={
            "repose": (gin, IN_REPOSE),
            "cohesion": (gin, IN_COHESION),
            "flow": (gin, IN_FLOW),
            "iterations": (gin, IN_RELAX_ITERS),
            "cell_size": (gin, IN_CELL_SIZE),
            "grid_n": (gin, IN_GRID_N),
        },
    )

    # Displace points to the relaxed surface: pos.z = base + h.
    final_base = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                       inputs={"Name": ATTR_BASE})
    final_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                    inputs={"Name": ATTR_HEIGHT})
    final_surface = b.add("ShaderNodeMath", operation="ADD",
                          label="final surface")
    b.link(final_base, "Attribute", final_surface, 0)
    b.link(final_h, "Attribute", final_surface, 1)

    new_pos = b.add("ShaderNodeCombineXYZ")
    b.link(sep2, "X", new_pos, "X")
    b.link(sep2, "Y", new_pos, "Y")
    b.link(final_surface, "Value", new_pos, "Z")
    set_pos = b.add("GeometryNodeSetPosition")
    b.link(relax_node, relax_key, set_pos, "Geometry")
    b.link(new_pos, "Vector", set_pos, "Position")

    b.link(set_pos, "Geometry", zone.output, "Geometry")
    b.link(zone.output, "Geometry", gout, OUT_GEOMETRY)

    b.layout()
    return tree
