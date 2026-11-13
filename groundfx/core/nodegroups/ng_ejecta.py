# SPDX-License-Identifier: GPL-3.0-or-later
"""Airborne material (gen 4): the third state next to bed and top layer.

A height field can only move material sideways, cell to cell. Real sand that
is hit fast leaves the ground: it flies as a sheet, breaks into streaks and
single grains, falls back and only then becomes part of the bed again. That
phase is what makes footage of sand read as real, and no amount of surface
detail replaces it.

The solver therefore launches part of the displaced volume as *parcels*:
points that carry a volume and fly ballistically inside the same simulation
zone. The coupling is exact in both directions:

* **Launch.** Volume the displacement step would have put on the ring around
  the footprint is split by the collider's speed. Slow contact keeps it in
  the bed (the rolling bow wave of solver v2); fast contact throws it. The
  parcel starts on the ring with the collider's velocity plus an outward and
  an upward share, both scattered, so a moving edge throws a sheet forward
  and an impact throws a crown.
* **Flight.** Gravity plus quadratic air drag, integrated semi-implicitly.
  Drag grows as the parcel gets smaller: a dense clump carries, a thin veil
  stalls and rains down early (the rule DNEG used for the sand of *Dune*).
* **Landing.** A parcel that reaches the bed, or the top of a collider, puts
  its volume back into that cell with the same exact scatter the displacement
  uses. From then on it avalanches like any other material.

Mass is conserved: bed + top layer + airborne volume only ever lose what
leaves the domain. Parcels are few (thousands); the display stage
(``ng_spray``) turns each into hundreds of grains.
"""
from __future__ import annotations

from ..ng_expr import V
from ..constants import (
    ATTR_HEIGHT, ATTR_BASE, ATTR_OCC, ATTR_COV, ATTR_ZHI, ATTR_TOP, ATTR_LO,
    ATTR_E_VEL, ATTR_E_VOL, ATTR_E_VOL0, ATTR_E_AGE, ATTR_E_DRAG, ATTR_E_SEED,
    ATTR_E_LAND, ATTR_E_V0,
)
from .. import surface_fn as sfn

GRAVITY = 9.81
_V_LO = 0.25          # m/s: below this nothing leaves the ground
_V_HI = 2.2           # m/s: from here on nearly all displaced volume flies
_MIN_AIR = 4e-5       # metres of layer per cell that are worth a parcel
_PARCEL_LAYER = 0.0012  # one parcel per this much layer on a cell
_MAX_DUP = 6
_DRAG = 0.35          # 1/m, quadratic drag of a typical parcel
_VOL_REF = 2.5e-8     # m^3, parcel volume the drag above refers to
_TOP_TOL = 0.008      # metres under a collider's top that still count as "on it"
GHOST_FRAMES = 4      # landed parcels stay this long for the display stage
_MAX_AGE = 12.0       # seconds; safety net for parcels that never land


def grid_index(g, p, n, cell):
    """Grid vertex index under position ``p`` and whether ``p`` is inside."""
    half = (n - 1.0) * 0.5
    col = (p.x / cell + half).round()
    row = (p.y / cell + half).round()
    inside = g.math("MULTIPLY",
                    g.math("MULTIPLY", col.gt(-0.5), col.lt(n - 0.5)),
                    g.math("MULTIPLY", row.gt(-0.5), row.lt(n - 0.5)))
    col = col.max(0.0).min(n - 1.0)
    row = row.max(0.0).min(n - 1.0)
    return row * n + col, inside


def _deposit(g, geo, parcels, names):
    """Sum the per-parcel amounts ``names`` into their target grid cells.

    Same trick as the displacement scatter: parcels and grid points are
    joined, summed per target index with Accumulate Field, and read back at
    the grid points (which come first: Join puts the last linked input
    first). Returns one field per name, evaluated on the grid.
    """
    i = g.index()
    grid_pts = g.out(g.node("GeometryNodeMeshToPoints", {"Mesh": geo}), 0)
    grid_pts = g.store(grid_pts, "gfx_s_tgt", i)
    for name in names:
        grid_pts = g.store(grid_pts, name, 0.0)
    join = g.b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, parcels)
    g.feed(join, 0, grid_pts)
    joined = g.out(join, 0)
    out = []
    for name in names:
        acc = g.node("GeometryNodeAccumulateField",
                     {"Value": g.attr(name),
                      "Group ID": g.attr("gfx_s_tgt").round()},
                     data_type="FLOAT", domain="POINT")
        out.append(g.sample_index(joined, g.out(acc, "Total"), i))
    return out


def step(g, geo, parcels, inp, dt):
    """Fly every parcel one frame and land those that reach a surface.

    Returns (grid with the landed volume added, surviving parcels).
    """
    n, cell = inp["n"], inp["cell"]
    # Not Domain Size: in 5.2 it crashes on a point cloud whose last point
    # was just deleted. A statistic over the points is safe on empty input.
    count = g.stat(parcels, 1.0, out="Sum")

    p = g.position()
    v = g.attr(ATTR_E_VEL, "FLOAT_VECTOR")
    land = g.attr(ATTR_E_LAND)
    vol = g.attr(ATTR_E_VOL)
    flying = land.lt(0.5)

    vg = v + g.vec(0.0, 0.0, dt * -GRAVITY)
    v2 = vg * (1.0 / (1.0 + g.attr(ATTR_E_DRAG) * vg.length() * dt))
    p2 = p + v2 * dt

    idx, inside = grid_index(g, p2, n, cell)
    a = g.sample_index(geo, g.vec(g.attr(ATTR_BASE) + g.attr(ATTR_HEIGHT),
                                  g.attr(ATTR_ZHI), g.attr(ATTR_COV)),
                       idx, kind="FLOAT_VECTOR")
    b = g.sample_index(geo, g.vec(g.attr(ATTR_TOP), g.attr(ATTR_LO), 0.0),
                       idx, kind="FLOAT_VECTOR")
    cvel = g.sample_index(geo, g.attr("gfx_vel", "FLOAT_VECTOR"), idx,
                          kind="FLOAT_VECTOR")
    s_bed, zhi, cov = a.x, a.y, a.z
    top, lo = b.x, b.y
    covered = g.math("MULTIPLY", cov.gt(0.5), inside)
    # Over a collider a parcel either comes down on its top, or it has run
    # into a flank: then it is inside the object, rides along with the face
    # and drops to the ground beside it.
    above = g.math("MULTIPLY", covered, p2.z.gt(zhi - _TOP_TOL))
    flank = g.math("MULTIPLY",
                   g.math("MULTIPLY", covered, 1.0 - above),
                   g.math("MULTIPLY", p2.z.gt(lo), flying))
    p_fl = g.vec(p.x + cvel.x, p.y + cvel.y, p2.z)
    v_fl = g.vec(cvel.x / dt, cvel.y / dt, v2.z.min(0.0))
    p3 = g.switch(flank, p2, p_fl, kind="VECTOR")
    v3 = g.switch(flank, v2, v_fl, kind="VECTOR")

    hit_top = g.math("MULTIPLY", above, p2.z.lt(zhi + top))
    hit_bed = g.math("MULTIPLY", 1.0 - above, p2.z.lt(s_bed))
    landed = g.math("MULTIPLY", g.math("MAXIMUM", hit_top, hit_bed), flying)
    amt = vol / (cell * cell) * inside * landed
    parcels, caps = g.capture(parcels, [p3, v3, landed, amt * (1.0 - hit_top),
                                        amt * hit_top, idx])
    p3, v3, landed, amt_bed, amt_top, idx = caps

    parcels = g.store(parcels, "gfx_s_tgt", idx)
    parcels = g.store(parcels, "gfx_s_bed", amt_bed)
    parcels = g.store(parcels, "gfx_s_top", amt_top)
    dep_bed, dep_top = _deposit(g, geo, parcels, ("gfx_s_bed", "gfx_s_top"))
    some = count.gt(0.5)
    geo = g.store(geo, ATTR_HEIGHT,
                  g.attr(ATTR_HEIGHT) + g.switch(some, 0.0, dep_bed))
    geo = g.store(geo, ATTR_TOP,
                  g.attr(ATTR_TOP) + g.switch(some, 0.0, dep_top))

    parcels = g.out(g.node("GeometryNodeSetPosition",
                           {"Geometry": parcels, "Position": p3}), 0)
    parcels = g.store(parcels, ATTR_E_VEL, v3, kind="FLOAT_VECTOR")
    parcels = g.store(parcels, ATTR_E_AGE, g.attr(ATTR_E_AGE) + dt)
    parcels = g.store(parcels, ATTR_E_VOL, g.attr(ATTR_E_VOL) * (1.0 - landed))
    land = g.attr(ATTR_E_LAND)
    parcels = g.store(parcels, ATTR_E_LAND,
                      g.switch(land.gt(0.5), landed, land + 1.0))
    gone = g.math("MAXIMUM", g.attr(ATTR_E_LAND).gt(GHOST_FRAMES + 0.5),
                  g.attr(ATTR_E_AGE).gt(_MAX_AGE))
    parcels = g.out(g.node("GeometryNodeDeleteGeometry",
                           {"Geometry": parcels, "Selection": gone},
                           domain="POINT"), 0)
    return geo, parcels


def emit(g, geo, arrive, inp, dt, spray):
    """Split the volume arriving on the ring into bed and airborne share.

    ``arrive`` is the layer (metres) the displacement step delivers per
    cell. Returns (grid, layer that stays in the bed, new parcels).
    """
    cell = inp["cell"]
    occ_pts = g.out(g.node("GeometryNodeMeshToPoints",
                           {"Mesh": geo,
                            "Selection": g.attr(ATTR_OCC).gt(0.5)}), 0)
    near = g.out(g.node("GeometryNodeSampleNearest",
                        {"Geometry": occ_pts,
                         "Sample Position": g.position()},
                        domain="POINT"), 0)
    cv = g.sample_index(occ_pts, g.attr("gfx_vel", "FLOAT_VECTOR"), near,
                        kind="FLOAT_VECTOR")
    cp = g.sample_index(occ_pts, g.position(), near, kind="FLOAT_VECTOR")
    speed = cv.length() / dt
    launch = spray * sfn.smoothstep((speed - _V_LO) / (_V_HI - _V_LO))
    air = arrive * launch
    air = air * air.gt(_MIN_AIR)

    geo = g.store(geo, "gfx_arr", arrive)
    geo = g.store(geo, "gfx_air", 0.0)
    sel = g.attr("gfx_arr").gt(1e-9)
    geo = g.store(geo, "gfx_air", air, selection=sel)
    geo = g.store(geo, "gfx_ecv", cv, kind="FLOAT_VECTOR", selection=sel)
    geo = g.store(geo, "gfx_ecp", cp, kind="FLOAT_VECTOR", selection=sel)
    air = g.attr("gfx_air")
    stay = g.attr("gfx_arr") - air
    # Parcels leave from the surface as it was. At speed the displacement
    # dumps a whole frame's bow volume on a few ring cells, a tower the
    # relaxation flattens within the same frame; launching from its top
    # would start the spray half a metre up in the air.
    before = geo
    geo = g.store(geo, ATTR_HEIGHT, g.attr(ATTR_HEIGHT) + stay)

    pts = g.out(g.node("GeometryNodeMeshToPoints",
                       {"Mesh": before, "Selection": air.gt(0.0)}), 0)
    n_dup = (air / _PARCEL_LAYER).round().max(1.0).min(float(_MAX_DUP))
    dup = g.node("GeometryNodeDuplicateElements",
                 {"Geometry": pts, "Amount": n_dup}, domain="POINT")
    pts = g.out(dup, "Geometry")

    frame = g.out(g.b.add("GeometryNodeInputSceneTime"), "Frame")
    ident = g.index()

    def rnd(j, lo=0.0, hi=1.0):
        return g.random(frame * 37.0 + float(j), lo, hi, ident)

    cv = g.attr("gfx_ecv", "FLOAT_VECTOR")
    cp = g.attr("gfx_ecp", "FLOAT_VECTOR")
    pos = g.position()
    vc = cv * (1.0 / dt)
    sp = vc.length()
    vh = g.vec(vc.x, vc.y, 0.0)
    out_dir = pos - cp
    out_dir = g.vec(out_dir.x, out_dir.y, 0.0).normalize()
    ang = rnd(6, 0.0, 6.2832)
    swirl = g.vec(g.math("COSINE", ang), g.math("SINE", ang), 0.0)
    # Pushed material cannot leave much faster than what pushes it: the bulk
    # stays below the collider's speed. The few fastest grains leave low and
    # flat, the rest steeper and slower (20 to 80 degrees in experiments).
    boost = 1.0 + rnd(4).pow(6.0) * 0.9
    # Ahead of the moving face material is being pushed: it cannot be slower
    # than the face, or the face runs it over again within the frame (the
    # spray then sticks to the object as a column). It squeezes out a little
    # faster instead. Beside the object nothing pushes: it is dragged along
    # at a fraction and thrown outward, which opens the sheet into a fan.
    ahead = out_dir.dot(vh.normalize()).max(0.0)
    along = g.mix(rnd(1, 0.25, 0.85), rnd(12, 1.03, 1.45), ahead)
    side = sp * rnd(2, 0.10, 0.65) * (1.0 - ahead * 0.6)
    horiz = (vh * along + out_dir * side
             + swirl * (sp * rnd(7, 0.0, 0.15))) * boost
    # Steep throws are rare: most material leaves at 15 to 40 degrees.
    up = sp * (0.10 + rnd(3).pow(2.2) * 0.80) * inp["lift"]
    v0 = horiz + g.vec(0.0, 0.0, up)

    vol = g.attr("gfx_air") * (cell * cell) / n_dup
    drag = (_DRAG * rnd(5, 0.4, 2.2)
            * (_VOL_REF / vol.max(1e-12)).pow(1.0 / 3.0).max(0.4).min(4.0))
    # Leave at a random moment within the frame: without it every frame's
    # parcels start on the same line and the spray strobes.
    tau = rnd(8) * dt
    start = g.vec(pos.x + rnd(9, -0.5, 0.5) * cell,
                  pos.y + rnd(10, -0.5, 0.5) * cell,
                  g.attr(ATTR_BASE) + g.attr(ATTR_HEIGHT)
                  + rnd(13) * g.attr("gfx_air").min(0.03) + 0.0005)
    start = start + v0 * tau + g.vec(0.0, 0.0, tau * tau * (-0.5 * GRAVITY))
    v_now = v0 + g.vec(0.0, 0.0, tau * -GRAVITY)

    pts, caps = g.capture(pts, [start, v_now, vol, drag, tau, rnd(11),
                                v0.length()])
    start, v_now, vol, drag, tau, seed, speed0 = caps
    # The points were cut from the grid and carry all its fields. None of
    # them means anything on a parcel, and the display stage multiplies
    # every attribute by hundreds of grains.
    pts = g.out(g.node("GeometryNodeRemoveAttribute",
                       {"Geometry": pts, "Name": "gfx_*",
                        "Pattern Mode": "Wildcard"}),  0)
    pts = g.out(g.node("GeometryNodeSetPosition",
                       {"Geometry": pts, "Position": start}), 0)
    pts = g.store(pts, ATTR_E_VEL, v_now, kind="FLOAT_VECTOR")
    pts = g.store(pts, ATTR_E_VOL, vol)
    pts = g.store(pts, ATTR_E_VOL0, vol)
    pts = g.store(pts, ATTR_E_DRAG, drag)
    pts = g.store(pts, ATTR_E_AGE, tau)
    pts = g.store(pts, ATTR_E_SEED, seed)
    pts = g.store(pts, ATTR_E_V0, speed0)
    pts = g.store(pts, ATTR_E_LAND, 0.0)
    return geo, pts


def for_output(g, parcels):
    """Parcels as they leave the solver: a plain point cloud whose radius is
    that of a sphere of the parcel's volume, so even without the display
    stage the spray shows as coarse lumps. Landed parcels are kept (the
    display stage lets their grains finish the fall) but have no size."""
    vol = g.attr(ATTR_E_VOL).max(0.0)
    radius = (vol * 0.2387).pow(1.0 / 3.0) * g.attr(ATTR_E_LAND).lt(0.5)
    return V(g, g.node("GeometryNodeSetPointRadius",
                       {"Points": parcels, "Radius": radius}).outputs[0])
