# SPDX-License-Identifier: GPL-3.0-or-later
"""The ground simulation node group (solver v2).

A 2.5D height field of loose material over a static base, stepped once per
frame inside a Simulation zone. No Python runs per frame, so it plays in the
viewport and bakes like any other simulation.

Per frame:

1. **Colliders.** The collider collection is realised in domain space. Each
   vertex's velocity is its position minus last frame's (kept in the state),
   so rotation and deformation are exact, not just translation. With carve
   substeps > 1 the collider is also stamped at interpolated sub-frame poses:
   a fast object leaves one continuous trench instead of dashes.
2. **Carve.** A ray from under the base finds each column's collider
   underside ``lo``. Material above ``lo`` is removed; the cell is *occupied*.
3. **Displace.** ``Displacement Ratio`` of the removed volume is scattered
   onto the free ring just outside the footprint (the rest is compaction):
   every source cell sends its volume to the nearest ring cell of a query
   point nudged along the collider's motion (bow wave). The scatter is one
   Accumulate Field over grid+sources, so it is exact, order-free and costs
   no iterations however deep the footprint.
4. **Relax.** Avalanching toward the angle of repose with an exact pairwise
   flux over the 8-neighbourhood (E, N, NE, NW owned by each cell, read back
   by the partner). A pair only exchanges what exceeds the stable step
   ``dist * (tan(repose + comp*compaction_angle) + cohesion + yield/h)``,
   so every formula variant stays antisymmetric and mass-conserving. The
   ``yield/h`` term is a Bingham yield stress: thin mud stays put on a slope,
   thick mud flows. Occupied cells neither give nor take (the object holds
   the material against its faces).
5. **Fields** for the shaders: compaction with recovery, motion direction,
   disturbance age.

Grid layout contract (from ``op_add._make_grid_mesh``): vertex index =
row * N + col, x along columns. Verified against Blender 5.2.
"""
from __future__ import annotations

import math

from ..ng_builder import new_geometry_group
from ..ng_expr import make, V
from ..ng_zones import make_simulation_zone, make_repeat_zone
from ..constants import (
    NG_GROUND_SIM, ATTR_HEIGHT, ATTR_BASE, ATTR_OCC, ATTR_COMP, ATTR_AGE,
    ATTR_FLOW, ATTR_CARVE, DEFAULT_MATERIAL_HEIGHT,
)

# Group input socket names (also used by the property/socket mapping).
IN_GEOMETRY = "Geometry"
IN_MATERIAL_HEIGHT = "Material Height"
IN_COLLIDER_COLLECTION = "Colliders"
IN_CARVE_SUBSTEPS = "Carve Substeps"
IN_REPOSE = "Angle Of Repose"
IN_COHESION = "Cohesion"
IN_YIELD = "Yield"
IN_COMPACT_ANGLE = "Compaction Angle"
IN_FLOW = "Flow Rate"
IN_RELAX_ITERS = "Relax Iterations"
IN_STICKINESS = "Stickiness"
IN_RECOVERY = "Recovery"
IN_CELL_SIZE = "Cell Size"
IN_GRID_N = "Grid N"
IN_DISPLACE_RATIO = "Displacement Ratio"
IN_BOW_WAVE = "Bow Wave"
IN_CONTACT_AA = "Contact AA"
OUT_GEOMETRY = "Geometry"

STATE_PREV = "Colliders Prev"
MAX_SUBSTEPS = 4

_RAY_DROP = 1.0       # rays start this far under the base (metres)
_RAY_LENGTH = 50.0
_CONTACT_EPS = 0.0015  # collider within this of the surface = occupied
_PAIR_RATE = 0.12      # explicit flux factor; 8 pairs * 0.12 < 1 -> stable
_SQRT2 = math.sqrt(2.0)
# (d_col, d_row, distance in cells) for the four directions a cell owns.
_DIRS = ((1, 0, 1.0), (0, 1, 1.0), (1, 1, _SQRT2), (-1, 1, _SQRT2))


def _interface(b):
    b.input(IN_GEOMETRY, "NodeSocketGeometry")
    b.input(IN_COLLIDER_COLLECTION, "NodeSocketCollection",
            description="Every object in this collection pushes material")
    b.input(IN_MATERIAL_HEIGHT, "NodeSocketFloat",
            default=DEFAULT_MATERIAL_HEIGHT, min=0.0, subtype="DISTANCE")
    b.input(IN_REPOSE, "NodeSocketFloat", default=math.radians(34.0),
            min=0.0, max=math.radians(89.0), subtype="ANGLE")
    b.input(IN_COHESION, "NodeSocketFloat", default=0.02, min=0.0, max=4.0,
            description="Extra stable slope (tan) from moisture/cohesion")
    b.input(IN_YIELD, "NodeSocketFloat", default=0.0, min=0.0,
            subtype="DISTANCE",
            description="Bingham yield as a length: layers thinner than "
                        "this barely flow (mud)")
    b.input(IN_COMPACT_ANGLE, "NodeSocketFloat", default=math.radians(12.0),
            min=0.0, max=math.radians(60.0), subtype="ANGLE",
            description="Packed material holds this much steeper")
    b.input(IN_FLOW, "NodeSocketFloat", default=1.0, min=0.0, max=1.0,
            description="Avalanche speed (1 = free-flowing)")
    b.input(IN_RELAX_ITERS, "NodeSocketInt", default=8, min=0, max=128)
    b.input(IN_STICKINESS, "NodeSocketFloat", default=0.05, min=0.0, max=1.0,
            description="How readily material clings to colliders")
    b.input(IN_RECOVERY, "NodeSocketFloat", default=0.02, min=0.0, max=1.0)
    b.input(IN_CELL_SIZE, "NodeSocketFloat", default=2.0 / 128, min=1e-5,
            subtype="DISTANCE")
    b.input(IN_GRID_N, "NodeSocketInt", default=129, min=2)
    b.input(IN_DISPLACE_RATIO, "NodeSocketFloat", default=0.9, min=0.0,
            max=1.0, description="Share of displaced volume pushed aside "
                                 "(the rest is compacted)")
    b.input(IN_BOW_WAVE, "NodeSocketFloat", default=0.7, min=0.0, max=2.0,
            description="How far ahead of a moving collider material lands")
    b.input(IN_CARVE_SUBSTEPS, "NodeSocketInt", default=2, min=1,
            max=MAX_SUBSTEPS)
    b.input(IN_CONTACT_AA, "NodeSocketFloat", default=0.0, min=0.0, max=1.0,
            description="Reserved: sub-cell contact edge smoothing")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")


def _colliders(g, gin):
    """Realised collider geometry in domain space (no velocity yet)."""
    ci = g.node("GeometryNodeCollectionInfo",
                {"Collection": g.out(gin, IN_COLLIDER_COLLECTION),
                 "Separate Children": False, "Reset Children": False},
                transform_space="RELATIVE")
    real = g.node("GeometryNodeRealizeInstances", {0: g.out(ci, 0)})
    return g.out(real, 0)


def _swept(g, cur, prev, substeps):
    """Store per-vertex velocity and stamp sub-frame copies of the collider.

    Returns (swept geometry for the raycast, current geometry for the state).
    The velocity is only trusted when the topology matches last frame's.
    """
    n_cur = g.out(g.node("GeometryNodeAttributeDomainSize",
                         {0: cur}, component="MESH"), "Point Count")
    n_prev = g.out(g.node("GeometryNodeAttributeDomainSize",
                          {0: prev}, component="MESH"), "Point Count")
    same = g.math("COMPARE", n_cur, n_prev, 0.5)
    pos = g.position()
    p_prev = g.sample_index(prev, pos, g.index(), kind="FLOAT_VECTOR")
    vel = g.switch(same, g.vec(), pos - p_prev, kind="VECTOR")
    cur = g.store(cur, "gfx_cvel", vel, kind="FLOAT_VECTOR")
    v_attr = g.attr("gfx_cvel", "FLOAT_VECTOR")

    join = g.b.add("GeometryNodeJoinGeometry")
    for k in range(1, MAX_SUBSTEPS):
        # copy at t = 1 - k/S, only when k < S
        t_back = g.math("DIVIDE", float(k), substeps)
        sp = g.node("GeometryNodeSetPosition",
                    {"Geometry": cur, "Offset": v_attr * (t_back * -1.0)})
        use = g.math("LESS_THAN", float(k), substeps)
        sw = g.node("GeometryNodeSwitch",
                    {"Switch": use, "True": g.out(sp, 0)},
                    input_type="GEOMETRY")
        g.feed(join, 0, g.out(sw, 0))
    g.feed(join, 0, cur)
    return g.out(join, 0), cur


def _grid_helpers(g, n):
    i = g.index()
    col = i.fmod(n)
    row = (i / n).floor()
    return i, col, row


def _relax(g, b, geo, inp):
    """Repeat zone: pairwise 8-neighbour avalanche toward the repose angle.

    Multi-scale: the first iterations of every frame exchange between cells 4
    and then 2 apart (threshold scaled by distance), so a tall heap spreads
    over many cells in a few iterations; the rest work on direct neighbours
    and shape the final slope. A long pair only trades if the cell halfway is
    neither occupied nor higher than both ends - mass never tunnels through a
    berm or a thin collider. Every pair flux is owned by one cell and read
    back by its partner, so mass is conserved exactly.
    """
    rz = make_repeat_zone(b, [("GEOMETRY", "Geometry")])
    g.feed(rz.input, "Iterations", inp["iters"])
    g.feed(rz.input, "Geometry", geo)
    geo = V(g, rz.input.outputs["Geometry"])
    it = V(g, rz.input.outputs["Iteration"])
    stride = 1.0 + it.lt(3.5) + it.lt(1.5) * 2.0   # 4, 4, 2, 2, 1, 1, ...
    half = (stride * 0.5).floor()

    n, cell = inp["n"], inp["cell"]
    i, col, row = _grid_helpers(g, n)
    h = g.attr(ATTR_HEIGHT)
    base = g.attr(ATTR_BASE)
    occ = g.attr(ATTR_OCC)
    comp = g.attr(ATTR_COMP)
    s = base + h
    packed = g.vec(s, h, occ)

    tan_eff = g.math("TANGENT",
                     (inp["repose"] + comp * inp["compact"]).min(math.radians(85)))
    slope_ok = tan_eff + inp["cohesion"]
    rate = inp["flow"] * _PAIR_RATE
    free_i = 1.0 - occ

    fluxes = []
    for dc, dr, dist in _DIRS:
        step = dc + dr * n
        cj = col + stride * dc
        ok = g.math("MULTIPLY",
                    g.math("MULTIPLY", cj.gt(-0.5), cj.lt(n - 0.5)),
                    (row + stride * dr).lt(n - 0.5))
        nb = g.sample_index(geo, packed, i + stride * step, kind="FLOAT_VECTOR")
        mid = g.sample_index(geo, packed, i + half * step, kind="FLOAT_VECTOR")
        s_j, h_j, occ_j = nb.x, nb.y, nb.z
        path_ok = g.math("MULTIPLY", mid.x.lt(s.max(s_j) + 1e-6),
                         mid.z.lt(0.5))
        diff = s - s_j
        h_pair = ((h + h_j) * 0.5).max(1e-4)
        stable = (slope_ok + inp["yield"] / h_pair) * (cell * dist * stride)
        over = (diff.abs() - stable).max(0.0) * rate
        h_src = g.switch(diff.gt(0.0), h_j, h)
        mag = over.min(h_src * 0.125)
        f = diff.sign() * mag * ok * path_ok * free_i * (1.0 - occ_j)
        fluxes.append(f)

    cap_geo, caps = g.capture(geo, fluxes)
    out_sum = caps[0] + caps[1] + caps[2] + caps[3]
    inflow = None
    for (dc, dr, _), fcap in zip(_DIRS, caps):
        src = i - stride * (dc + dr * n)
        val = g.sample_index(cap_geo, fcap, src)
        inflow = val if inflow is None else inflow + val
    h_new = (g.attr(ATTR_HEIGHT) - out_sum + inflow).max(0.0)
    geo2 = g.store(cap_geo, ATTR_HEIGHT, h_new)
    g.feed(rz.output, "Geometry", geo2)
    return V(g, rz.output.outputs["Geometry"])


def _displace(g, geo, inp, pushed, vel):
    """Scatter ``pushed`` from occupied cells onto the free ring outside."""
    i = g.index()
    occ = g.attr(ATTR_OCC)
    cell = inp["cell"]

    # Ring: free cells within a few cells of the footprint.
    blur = g.node("GeometryNodeBlurAttribute",
                  {"Value": occ, "Iterations": 3}, data_type="FLOAT")
    near = g.out(blur, 0).gt(0.002)
    ring_sel = g.math("MULTIPLY", near, occ.lt(0.5))
    # Grid index must be stored on the MESH: an Index field evaluated after
    # Mesh to Points would count ring points, not grid vertices.
    geo = g.store(geo, "gfx_src_i", i)
    ring = g.node("GeometryNodeMeshToPoints",
                  {"Mesh": geo, "Selection": ring_sel})
    ring = g.out(ring, 0)

    # Sources: one point per cell that lost material this frame.
    geo = g.store(geo, "gfx_push", pushed)
    geo = g.store(geo, "gfx_vh", vel, kind="FLOAT_VECTOR")
    push_a = g.attr("gfx_push")
    src = g.node("GeometryNodeMeshToPoints",
                 {"Mesh": geo, "Selection": push_a.gt(1e-7)})
    src = g.out(src, 0)
    v = g.attr("gfx_vh", "FLOAT_VECTOR")
    vh = g.vec(v.x, v.y, 0.0)
    speed = vh.length()
    ahead = vh.normalize() * ((speed / cell).min(1.0) * inp["bow"] * 0.08)
    jit = g.vec(g.random(11, -1.5, 1.5) * cell, g.random(12, -1.5, 1.5) * cell, 0.0)
    q = g.position() + ahead + jit
    near_i = g.out(g.node("GeometryNodeSampleNearest",
                          {"Geometry": ring, "Sample Position": q},
                          domain="POINT"), 0)
    tgt = g.sample_index(ring, g.attr("gfx_src_i"), near_i)
    src = g.store(src, "gfx_grp", tgt)
    src = g.store(src, "gfx_amt", push_a)

    grid_pts = g.out(g.node("GeometryNodeMeshToPoints", {"Mesh": geo}), 0)
    grid_pts = g.store(grid_pts, "gfx_grp", i)
    grid_pts = g.store(grid_pts, "gfx_amt", 0.0)
    join = g.b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, src)       # Join puts the LAST linked input first:
    g.feed(join, 0, grid_pts)  # grid points keep indices 0..N-1.
    joined = g.out(join, 0)
    acc = g.node("GeometryNodeAccumulateField",
                 {"Value": g.attr("gfx_amt"),
                  "Group ID": g.attr("gfx_grp").round()},
                 data_type="FLOAT", domain="POINT")
    arrive = g.sample_index(joined, g.out(acc, "Total"), i)
    return geo, arrive


def build(name: str = NG_GROUND_SIM):
    tree = new_geometry_group(name)
    b, g = make(tree)
    _interface(b)
    gin, gout = b.group_io()

    def I(key):  # noqa: E743 - group input as V
        return g.out(gin, key)

    inp = {
        "n": I(IN_GRID_N), "cell": I(IN_CELL_SIZE), "repose": I(IN_REPOSE),
        "cohesion": I(IN_COHESION), "yield": I(IN_YIELD),
        "compact": I(IN_COMPACT_ANGLE), "flow": I(IN_FLOW),
        "iters": I(IN_RELAX_ITERS), "bow": I(IN_BOW_WAVE),
    }

    # ---- initial state ------------------------------------------------------
    geo0 = I(IN_GEOMETRY)
    geo0 = g.store(geo0, ATTR_BASE, g.position().z)
    # Optional painted start layer (gfx_init) on top of the uniform height.
    geo0 = g.store(geo0, ATTR_HEIGHT, I(IN_MATERIAL_HEIGHT) + g.attr("gfx_init"))
    for a in (ATTR_OCC, ATTR_COMP, ATTR_CARVE):
        geo0 = g.store(geo0, a, 0.0)
    geo0 = g.store(geo0, ATTR_AGE, 1000.0)
    geo0 = g.store(geo0, ATTR_FLOW, g.vec(), kind="FLOAT_VECTOR")

    sim = make_simulation_zone(b, [("GEOMETRY", STATE_PREV)])
    g.feed(sim.input, "Geometry", geo0)
    g.feed(sim.input, STATE_PREV, _colliders(g, gin))
    geo = V(g, sim.input.outputs["Geometry"])
    prev = V(g, sim.input.outputs[STATE_PREV])

    # ---- 1. colliders -------------------------------------------------------
    cur = _colliders(g, gin)
    swept, cur = _swept(g, cur, prev, I(IN_CARVE_SUBSTEPS))

    # ---- 2. carve -------------------------------------------------------------
    pos = g.position()
    base = g.attr(ATTR_BASE)
    h = g.attr(ATTR_HEIGHT)
    origin = g.vec(pos.x, pos.y, base - _RAY_DROP)
    ray = g.node("GeometryNodeRaycast",
                 {"Target Geometry": swept,
                  "Attribute": g.attr("gfx_cvel", "FLOAT_VECTOR"),
                  "Source Position": origin, "Ray Direction": (0.0, 0.0, 1.0),
                  "Ray Length": _RAY_LENGTH},
                 data_type="FLOAT_VECTOR")
    hit = g.out(ray, "Is Hit")
    lo = g.switch(hit, 1e6, g.out(ray, "Hit Position").z)
    vel = g.switch(hit, g.vec(), g.out(ray, "Attribute"), kind="VECTOR")
    surf = base + h
    occ = lo.lt(surf + _CONTACT_EPS)
    removed = (surf - lo).max(0.0).min(h)
    geo, caps = g.capture(geo, [occ, removed, vel])
    occ, removed, vel = caps
    geo = g.store(geo, ATTR_OCC, occ)
    geo = g.store(geo, ATTR_CARVE, removed)
    geo = g.store(geo, "gfx_vel", vel, kind="FLOAT_VECTOR")
    geo = g.store(geo, ATTR_HEIGHT, g.attr(ATTR_HEIGHT) - removed)

    # ---- 3. displace ----------------------------------------------------------
    pushed = removed * I(IN_DISPLACE_RATIO)
    geo, arrive = _displace(g, geo, inp, pushed, vel)
    geo = g.store(geo, ATTR_HEIGHT, g.attr(ATTR_HEIGHT) + arrive)

    # ---- 4. relax ---------------------------------------------------------------
    geo = _relax(g, b, geo, inp)

    # ---- 5. fields ----------------------------------------------------------------
    occ_a = g.attr(ATTR_OCC)
    comp = (g.attr(ATTR_COMP) * (1.0 - I(IN_RECOVERY) * 0.3)).max(occ_a)
    geo = g.store(geo, ATTR_COMP, comp)
    vel = g.attr("gfx_vel", "FLOAT_VECTOR")
    vflat = g.vec(vel.x, vel.y, 0.0)
    flow = g.mix(g.attr(ATTR_FLOW, "FLOAT_VECTOR"), vflat.normalize(),
                 g.math("MULTIPLY", occ_a, vflat.length().gt(1e-6)))
    geo = g.store(geo, ATTR_FLOW, flow, kind="FLOAT_VECTOR")
    age = g.switch(g.attr(ATTR_CARVE).gt(1e-6), g.attr(ATTR_AGE) + 1.0, 0.0)
    geo = g.store(geo, ATTR_AGE, age)

    g.feed(sim.output, "Geometry", geo)
    g.feed(sim.output, STATE_PREV, cur)
    geo = V(g, sim.output.outputs["Geometry"])

    # ---- display: surface = base + h --------------------------------------------
    p = g.position()
    out_pos = g.vec(p.x, p.y, g.attr(ATTR_BASE) + g.attr(ATTR_HEIGHT))
    sp = g.node("GeometryNodeSetPosition", {"Geometry": geo, "Position": out_pos})
    g.feed(gout, OUT_GEOMETRY, g.out(sp, 0))

    b.layout()
    return tree
