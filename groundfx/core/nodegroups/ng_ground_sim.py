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
    ATTR_FLOW, ATTR_CARVE, ATTR_COV, ATTR_ZHI, ATTR_TOP, ATTR_DIST, ATTR_DAMP,
    ATTR_LO, DEFAULT_MATERIAL_HEIGHT,
)
from . import ng_ejecta as ejecta

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
IN_DRYING = "Drying"
IN_SPRAY = "Spray"
IN_SPRAY_LIFT = "Spray Lift"
IN_SPRAY_DRAG = "Spray Drag"
OUT_GEOMETRY = "Geometry"

STATE_PREV = "Colliders Prev"
STATE_EJECTA = "Ejecta"
MAX_SUBSTEPS = 4

_RAY_DROP = 1.0       # rays start this far under the base (metres)
_RAY_LENGTH = 50.0
_CONTACT_EPS = 0.0015  # collider within this of the surface = occupied
_PAIR_RATE = 0.12      # explicit flux factor; 8 pairs * 0.12 < 1 -> stable
_TOP_HIDE = 0.0004     # thinner layers on a collider stay invisible (no z-fight)
_RING_REACH = 0.04     # metres around the footprint that take displaced volume
_DIST_FULL = 0.003    # metres of height change that count as fully disturbed
_DAMP_DEPTH = 0.03     # metres from rest level at which material is fully damp
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
    b.input(IN_DRYING, "NodeSocketFloat", default=0.006, min=0.0, max=1.0,
            description="How fast freshly exposed (damp, darker) material "
                        "dries per frame")
    b.input(IN_SPRAY, "NodeSocketFloat", default=0.0, min=0.0, max=1.0,
            description="Share of fast-displaced material that leaves the "
                        "ground and flies (0 = everything stays in the bed)")
    b.input(IN_SPRAY_DRAG, "NodeSocketFloat", default=1.0, min=0.0, max=50.0,
            description="Air drag of thrown material relative to sand: "
                        "light powder stalls, heavy clots carry")
    b.input(IN_SPRAY_LIFT, "NodeSocketFloat", default=1.0, min=0.0, max=3.0,
            description="How steeply thrown material leaves the ground")
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
    """Repeat zone of pairwise 8-neighbour avalanching toward the repose angle.

    Every column *exposes* one surface: free columns their ground
    (base + h), columns a collider spans the collider's top plus the material
    lying on it (``gfx_zhi + gfx_top``). Colliders are therefore not walls of
    infinite height: a bow wave that grows past an object's top spills onto
    it, material on a tilted or overloaded object slides off its edges, and
    material under a collider is never touched. The available mass is ``h``
    or ``gfx_top`` accordingly.

    Each cell owns its E, N, NE, NW pairs and computes their flux once; the
    partner reads it back, so mass is conserved exactly whatever the
    threshold. Multi-scale: the first iterations of a frame trade between
    cells 4 and then 2 apart (threshold scaled by distance) so a tall heap
    spreads in a few iterations; a long pair only trades if the cell halfway
    is not covered and not higher than both ends (no tunnelling through a
    berm or a thin collider).
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
    comp = g.attr(ATTR_COMP)
    cov = g.attr(ATTR_COV)
    covered = cov.gt(0.5)
    top = g.attr(ATTR_TOP)
    s = g.switch(covered, g.attr(ATTR_BASE) + h, g.attr(ATTR_ZHI) + top)
    m = g.switch(covered, h, top)
    packed = g.vec(s, m, cov)

    tan_eff = g.math("TANGENT",
                     (inp["repose"] + comp * inp["compact"]).min(math.radians(85)))
    slope_ok = tan_eff + inp["cohesion"]
    rate = inp["flow"] * _PAIR_RATE

    fluxes = []
    for dc, dr, dist in _DIRS:
        step = dc + dr * n
        cj = col + stride * dc
        ok = g.math("MULTIPLY",
                    g.math("MULTIPLY", cj.gt(-0.5), cj.lt(n - 0.5)),
                    (row + stride * dr).lt(n - 0.5))
        nb = g.sample_index(geo, packed, i + stride * step, kind="FLOAT_VECTOR")
        mid = g.sample_index(geo, packed, i + half * step, kind="FLOAT_VECTOR")
        s_j, m_j, cov_j = nb.x, nb.y, nb.z
        # Long pairs stay on open ground: no collider at either end or
        # halfway, and no ridge in between. Direct neighbours always trade.
        long_ok = g.math("MULTIPLY", mid.x.lt(s.max(s_j) + 1e-6),
                         (mid.z + cov.max(cov_j)).lt(0.5))
        path_ok = g.math("MAXIMUM", stride.lt(1.5), long_ok)
        # sticky material clings to an object's surface
        stick = inp["stick"] * 1.5 * cov.max(cov_j)
        diff = s - s_j
        m_pair = ((m + m_j) * 0.5).max(1e-4)
        stable = (slope_ok + stick + inp["yield"] / m_pair) * (cell * dist * stride)
        over = (diff.abs() - stable).max(0.0) * rate
        m_src = g.switch(diff.gt(0.0), m_j, m)
        mag = over.min(m_src * 0.125)
        fluxes.append(diff.sign() * mag * ok * path_ok)

    cap_geo, caps = g.capture(geo, fluxes)
    out_sum = caps[0] + caps[1] + caps[2] + caps[3]
    inflow = None
    for (dc, dr, _), fcap in zip(_DIRS, caps):
        src = i - stride * (dc + dr * n)
        val = g.sample_index(cap_geo, fcap, src)
        inflow = val if inflow is None else inflow + val
    delta = inflow - out_sum
    cov2 = g.attr(ATTR_COV).gt(0.5)
    geo2 = g.store(cap_geo, ATTR_TOP, (g.attr(ATTR_TOP) + delta * cov2).max(0.0))
    geo2 = g.store(geo2, ATTR_HEIGHT,
                   (g.attr(ATTR_HEIGHT) + delta * (1.0 - cov2)).max(0.0))
    g.feed(rz.output, "Geometry", geo2)
    return V(g, rz.output.outputs["Geometry"])


def _scatter(g, geo, amount, target):
    """Exact scatter: return a field with, per grid vertex i, the sum of
    ``amount`` over all vertices whose ``target`` index is i.

    Grid points (amount 0, group = own index) and source points (group =
    target) are joined and summed per group with Accumulate Field; the grid
    points keep indices 0..N-1 because Join puts the LAST linked input first.
    """
    i = g.index()
    geo = g.store(geo, "gfx_s_amt", amount)
    geo = g.store(geo, "gfx_s_tgt", target)
    amt = g.attr("gfx_s_amt")
    src = g.out(g.node("GeometryNodeMeshToPoints",
                       {"Mesh": geo, "Selection": amt.gt(1e-9)}), 0)
    grid_pts = g.out(g.node("GeometryNodeMeshToPoints", {"Mesh": geo}), 0)
    grid_pts = g.store(grid_pts, "gfx_s_tgt", i)
    grid_pts = g.store(grid_pts, "gfx_s_amt", 0.0)
    join = g.b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, src)
    g.feed(join, 0, grid_pts)
    joined = g.out(join, 0)
    acc = g.node("GeometryNodeAccumulateField",
                 {"Value": g.attr("gfx_s_amt"),
                  "Group ID": g.attr("gfx_s_tgt").round()},
                 data_type="FLOAT", domain="POINT")
    return geo, g.sample_index(joined, g.out(acc, "Total"), i)


def _advect_top(g, geo, inp):
    """Carry the material lying on colliders along with them (last frame's
    collider velocity per cell), exactly mass-conserving."""
    n, cell = inp["n"], inp["cell"]
    i, col, row = _grid_helpers(g, n)
    v = g.attr("gfx_vel", "FLOAT_VECTOR")
    c2 = (col + v.x / cell).round()
    r2 = (row + v.y / cell).round()
    inside = g.math("MULTIPLY",
                    g.math("MULTIPLY", c2.gt(-0.5), c2.lt(n - 0.5)),
                    g.math("MULTIPLY", r2.gt(-0.5), r2.lt(n - 0.5)))
    tgt = g.switch(inside, i, r2 * n + c2)
    return _scatter(g, geo, g.attr(ATTR_TOP), tgt)


def _displace(g, geo, inp, pushed, vel):
    """Scatter ``pushed`` from occupied cells onto the free ring outside."""
    i = g.index()
    occ = g.attr(ATTR_OCC)
    cell = inp["cell"]

    # Ring: free cells within a few cells of the footprint.
    # The ring's reach is a length, not a cell count: on a fine grid three
    # cells are a centimetre, and a whole frame's volume dumped there towers
    # over the object instead of forming a bow wave.
    reach = (_RING_REACH / cell).round().clamp(3.0, 14.0)
    blur = g.node("GeometryNodeBlurAttribute",
                  {"Value": occ, "Iterations": reach}, data_type="FLOAT")
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
    # Target per grid vertex: the ring cell nearest to a query point nudged
    # along the collider motion (bow wave) and jittered over a few cells.
    v = g.attr("gfx_vh", "FLOAT_VECTOR")
    vh = g.vec(v.x, v.y, 0.0)
    speed = vh.length()
    # Each cell throws a different distance, so the volume spreads over the
    # depth of the ring instead of piling on its inner edge.
    throw = g.random(13, 0.15, 1.0)
    ahead = vh.normalize() * ((speed / cell).min(1.0) * inp["bow"] * 0.08 * throw)
    jr = (cell * 1.5).max(_RING_REACH * 0.3)
    jit = g.vec(g.random(11, -1.0, 1.0) * jr, g.random(12, -1.0, 1.0) * jr, 0.0)
    # Step 1: the nearest point of the ring gives the way out of the
    # footprint. Step 2: throw a random distance further along that way, so
    # cells deep inside (an object dropped in, or overlapping at the start)
    # fill the whole ring rather than stacking a wall on its inner row.
    pos = g.position()
    edge_i = g.out(g.node("GeometryNodeSampleNearest",
                          {"Geometry": ring, "Sample Position": pos},
                          domain="POINT"), 0)
    edge_p = g.sample_index(ring, g.position(), edge_i, kind="FLOAT_VECTOR")
    out_dir = edge_p - pos
    out_dir = g.vec(out_dir.x, out_dir.y, 0.0).normalize()
    q = edge_p + out_dir * (g.random(14, 0.0, 0.8) * _RING_REACH) + ahead + jit
    near_i = g.out(g.node("GeometryNodeSampleNearest",
                          {"Geometry": ring, "Sample Position": q},
                          domain="POINT"), 0)
    tgt = g.sample_index(ring, g.attr("gfx_src_i"), near_i)

    geo = g.store(geo, "gfx_tgt", tgt, selection=g.attr("gfx_push").gt(1e-9))
    return _scatter(g, geo, g.attr("gfx_push"), g.attr("gfx_tgt"))


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
        "stick": I(IN_STICKINESS), "lift": I(IN_SPRAY_LIFT), "drag": I(IN_SPRAY_DRAG),
    }

    # ---- initial state ------------------------------------------------------
    geo0 = I(IN_GEOMETRY)
    geo0 = g.store(geo0, ATTR_BASE, g.position().z)
    # Optional painted start layer (gfx_init) on top of the uniform height.
    geo0 = g.store(geo0, ATTR_HEIGHT, I(IN_MATERIAL_HEIGHT) + g.attr("gfx_init"))
    geo0 = g.store(geo0, "gfx_rest", I(IN_MATERIAL_HEIGHT) + g.attr("gfx_init"))
    for a in (ATTR_OCC, ATTR_COMP, ATTR_CARVE, ATTR_COV, ATTR_ZHI, ATTR_TOP,
              ATTR_DIST, ATTR_DAMP):
        geo0 = g.store(geo0, a, 0.0)
    geo0 = g.store(geo0, ATTR_LO, 1e6)
    geo0 = g.store(geo0, ATTR_AGE, 1000.0)
    geo0 = g.store(geo0, ATTR_FLOW, g.vec(), kind="FLOAT_VECTOR")
    geo0 = g.store(geo0, "gfx_vel", g.vec(), kind="FLOAT_VECTOR")

    sim = make_simulation_zone(b, [("GEOMETRY", STATE_PREV),
                                   ("GEOMETRY", STATE_EJECTA)])
    g.feed(sim.input, "Geometry", geo0)
    g.feed(sim.input, STATE_PREV, _colliders(g, gin))
    geo = V(g, sim.input.outputs["Geometry"])
    prev = V(g, sim.input.outputs[STATE_PREV])
    parcels = V(g, sim.input.outputs[STATE_EJECTA])
    dt = V(g, sim.input.outputs["Delta Time"]).max(1e-4)
    # Height at the start of the step: the change over the step marks the
    # surface as disturbed (look fields, no physics feedback).
    geo = g.store(geo, "gfx_h0", g.attr(ATTR_HEIGHT))

    # ---- 1. colliders -------------------------------------------------------
    cur = _colliders(g, gin)
    swept, cur = _swept(g, cur, prev, I(IN_CARVE_SUBSTEPS))

    # ---- 1b. material riding on colliders moves with them -------------------
    geo, arrive_top = _advect_top(g, geo, inp)
    geo = g.store(geo, ATTR_TOP, arrive_top)

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
    # Top of the collider over this column, for material lying on it.
    ray_top = g.node("GeometryNodeRaycast",
                     {"Target Geometry": cur,
                      "Source Position": g.vec(pos.x, pos.y, base + _RAY_LENGTH * 0.5),
                      "Ray Direction": (0.0, 0.0, -1.0),
                      "Ray Length": _RAY_LENGTH},
                     data_type="FLOAT")
    zhi = g.out(ray_top, "Hit Position").z
    covered = g.math("MULTIPLY", hit, g.out(ray_top, "Is Hit"))
    surf = base + h
    occ = lo.lt(surf + _CONTACT_EPS)
    removed = (surf - lo).max(0.0).min(h)
    geo, caps = g.capture(geo, [occ, removed, vel, covered, zhi, lo])
    occ, removed, vel, covered, zhi, lo = caps
    # Material on a collider that has left this column falls to the ground.
    top = g.attr(ATTR_TOP)
    geo = g.store(geo, ATTR_HEIGHT, g.attr(ATTR_HEIGHT) + top * (1.0 - covered))
    geo = g.store(geo, ATTR_TOP, top * covered)
    geo = g.store(geo, ATTR_COV, covered)
    geo = g.store(geo, ATTR_ZHI, zhi)
    geo = g.store(geo, ATTR_LO, lo)
    geo = g.store(geo, ATTR_OCC, occ)
    geo = g.store(geo, ATTR_CARVE, removed)
    geo = g.store(geo, "gfx_vel", vel, kind="FLOAT_VECTOR")
    geo = g.store(geo, ATTR_HEIGHT, g.attr(ATTR_HEIGHT) - removed)

    # ---- 3. displace ----------------------------------------------------------
    pushed = removed * I(IN_DISPLACE_RATIO)
    geo, arrive = _displace(g, geo, inp, pushed, vel)

    # ---- 3b. airborne: fast contact throws part of that volume ---------------
    # This frame's share of the ring volume is launched, the rest joins the
    # bed as before. Parcels already in the air fly on and land.
    geo, born = ejecta.emit(g, geo, arrive, inp, dt, I(IN_SPRAY))
    geo, parcels = ejecta.step(g, geo, parcels, inp, dt)
    pj = b.add("GeometryNodeJoinGeometry")
    g.feed(pj, 0, born)
    g.feed(pj, 0, parcels)
    parcels = g.out(pj, 0)

    # ---- 4. relax: ground avalanches, then spill onto / off colliders --------
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
    # Disturbance: wherever the height moved this step. gfx_dist only ever
    # grows (ripples do not come back). gfx_damp marks damp material from
    # below the dry crust: it scales with how far the surface is from its
    # rest level (a thin spill of surface sand stays dry, a deep cut or a
    # thick heap is damp) and dries out again over time.
    moved = ((g.attr(ATTR_HEIGHT) - g.attr("gfx_h0")).abs() / _DIST_FULL
             + g.attr(ATTR_OCC)).min(1.0)
    geo = g.store(geo, ATTR_DIST, (g.attr(ATTR_DIST) + moved).min(1.0))
    depth = ((g.attr(ATTR_HEIGHT) - g.attr("gfx_rest")).abs() / _DAMP_DEPTH).min(1.0)
    fresh = ((moved * 3.0).min(1.0) * depth).max(g.attr(ATTR_OCC))
    damp = (g.attr(ATTR_DAMP) * (1.0 - I(IN_DRYING))).max(fresh)
    geo = g.store(geo, ATTR_DAMP, damp)

    g.feed(sim.output, "Geometry", geo)
    g.feed(sim.output, STATE_PREV, cur)
    g.feed(sim.output, STATE_EJECTA, parcels)
    geo = V(g, sim.output.outputs["Geometry"])
    parcels = V(g, sim.output.outputs[STATE_EJECTA])

    # ---- display: surface = base + h --------------------------------------------
    # Close the gap at collider walls. A height field cannot hold a vertical
    # face: the cell under the object is cut down, the free cell beside it is
    # full, and the mesh joins them with a ramp one cell wide, which shows as
    # a gap along the wall. So the outermost cells under the object are drawn
    # at the height of the free material next to them: the ramp now lies
    # inside the object. Display only, the simulated height is untouched.
    # Never above the object's own top, so thin objects are not poked through.
    occ_d = g.attr(ATTR_OCC)
    free = 1.0 - occ_d
    h_d = g.attr(ATTR_HEIGHT)
    num = g.out(g.node("GeometryNodeBlurAttribute",
                       {"Value": h_d * free, "Iterations": 2},
                       data_type="FLOAT"), 0)
    den = g.out(g.node("GeometryNodeBlurAttribute",
                       {"Value": free, "Iterations": 2},
                       data_type="FLOAT"), 0)
    beside = num / den.max(1e-6)
    lid = g.switch(g.attr(ATTR_COV).gt(0.5), 1e6,
                   g.attr(ATTR_ZHI) - g.attr(ATTR_BASE) - _TOP_HIDE)
    filled = h_d.max(beside.min(lid))
    edge = g.math("MULTIPLY", occ_d.gt(0.5), den.gt(0.02))
    h_show = g.switch(edge, h_d, filled)
    p = g.position()
    out_pos = g.vec(p.x, p.y, g.attr(ATTR_BASE) + h_show)
    sp = g.node("GeometryNodeSetPosition", {"Geometry": geo, "Position": out_pos})
    ground = g.out(sp, 0)

    # Material lying on colliders: the covered part of the grid lifted to the
    # collider top + layer. Kept as an instance so the domain's mesh stays the
    # plain simulation grid (bake/freeze/readers rely on that).
    # The sheet reaches half a cell past the collider's edge and closes down
    # onto the collider's top plane there, so it never shows an open edge.
    cov = g.attr(ATTR_COV)
    t_vis = (g.attr(ATTR_TOP) - _TOP_HIDE).max(0.0) * cov
    cw = g.out(g.node("GeometryNodeBlurAttribute",
                      {"Value": cov, "Iterations": 1}, data_type="FLOAT"), 0)
    zw = g.out(g.node("GeometryNodeBlurAttribute",
                      {"Value": g.attr(ATTR_ZHI) * cov, "Iterations": 1},
                      data_type="FLOAT"), 0)
    z_edge = g.switch(cov.gt(0.5), zw / cw.max(1e-6), g.attr(ATTR_ZHI))
    geo_t = g.store(geo, "gfx_zt", z_edge + t_vis - _TOP_HIDE)
    geo_t = g.store(geo_t, "gfx_tv", t_vis)
    geo_t = g.store(geo_t, ATTR_DIST, 1.0)   # material on an object: no ripples
    keep = g.math("MULTIPLY", g.attr("gfx_tv").gt(0.0), cw.gt(1e-3))
    dele = g.node("GeometryNodeDeleteGeometry",
                  {"Geometry": geo_t, "Selection": keep.lt(1e-3)},
                  domain="FACE", mode="ALL")
    top_pos = g.vec(p.x, p.y, g.attr("gfx_zt"))
    tsp = g.node("GeometryNodeSetPosition",
                 {"Geometry": g.out(dele, 0), "Position": top_pos})
    inst = g.node("GeometryNodeGeometryToInstance", {0: g.out(tsp, 0)})
    join = b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, ejecta.for_output(g, parcels))
    g.feed(join, 0, g.out(inst, 0))
    g.feed(join, 0, ground)
    g.feed(gout, OUT_GEOMETRY, g.out(join, 0))

    b.layout()
    return tree
