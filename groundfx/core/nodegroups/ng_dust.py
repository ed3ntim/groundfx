# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Dust (gen 4, Blender 5.3+): the fraction that does not come down.

Thrown sand is not only grains. The finest part of it stays in the air for
seconds, drifts and thins out, long after every grain has landed. In
footage that haze is what ties the spray to the air around it; a sheet of
grains without it looks cut out.

Dust is display only. It lives in a small simulation zone of its own inside
the spray stage and never feeds back into the solver:

* **Source.** Every parcel leaves one puff when it is launched and one when
  it lands, weighted by its volume.
* **Motion.** A puff keeps a share of the parcel's velocity and loses it to
  the air within a fraction of a second, then drifts in a slow turbulent
  field and sinks a little.
* **Volume.** Each puff is drawn as a handful of points scattered over a
  radius that grows with its age (diffusion), and all points are summed
  into a density grid with Rasterize Points. That node is why this needs
  5.3: density from overlapping points adds up, so a busy launch zone is
  thick and a lone late puff is a wisp. Points to Volume in 5.2 only knows
  inside or outside.
"""
from __future__ import annotations

from ..ng_expr import V
from ..ng_zones import make_simulation_zone
from ..constants import ATTR_E_VEL, ATTR_E_VOL0, ATTR_E_AGE, ATTR_E_SEED, ATTR_E_LAND
from .. import surface_fn as sfn

GRID_NAME = "density"
_VOL_REF = 2.5e-8      # m^3, parcel volume that counts as weight 1
_SUB = 6               # points drawn per puff
_VOXEL = 0.012         # metres
_STOP = 7.0            # 1/s, how fast the air takes a puff's speed
_TURB = 0.22           # m/s, strength of the drift field
_SINK = 0.03           # m/s
_GROW = 0.07           # m/s, radius growth of a puff
_GAIN = 0.9            # density per unit weight and sub point
_POWDER_DENSITY = 9.0e4   # puffs per m^2 of ground the object ploughs, per frame
_POWDER_ARR = 0.004       # metres of displaced layer that give the full cloud
_POWDER_V_LO = 0.25       # m/s, below this nothing is whirled up
_POWDER_V_HI = 1.8        # m/s, full cloud
_POWDER_WEIGHT = 110.0     # dust weight of one powder puff (a parcel puff: about 1)
_POWDER_R0 = 0.03         # metres, radius of a fresh powder puff
_POWDER_GROW = 0.055      # m/s
_POWDER_LIFT = 0.9        # m/s, upper limit of the upward speed of a puff
_POWDER_SIDE = 0.85       # sideways push, at most this share of the speed


def supported() -> bool:
    import bpy
    return bpy.app.version >= (5, 3, 0)


def _powder(g, ground, powder, frame_time):
    """New puffs raised by the moving object itself (powder snow).

    Dry powder does not need to be thrown to get into the air: whatever
    ploughs through it whirls the fines up, and they hang for seconds. The
    source is the ground that received displaced material this frame (the
    solver's ``gfx_arr``), weighted by how fast the object moves there
    (``gfx_ecv``). Points are scattered by area, so the amount does not
    depend on the subdivision of the surface stage.
    """
    arr = g.attr("gfx_arr")
    speed = g.attr("gfx_ecv", "FLOAT_VECTOR").length() / frame_time
    fast = sfn.smoothstep((speed - _POWDER_V_LO) / (_POWDER_V_HI - _POWDER_V_LO))
    dens = powder * _POWDER_DENSITY * fast * (arr / _POWDER_ARR).clamp(0.0, 1.0)
    # no powder: an empty mesh, and the density is never evaluated
    src = g.out(g.node("GeometryNodeSwitch",
                       {"Switch": powder.gt(0.0), "True": ground},
                       input_type="GEOMETRY"), 0)
    frame = g.out(g.b.add("GeometryNodeInputSceneTime"), "Frame")
    dist = g.node("GeometryNodeDistributePointsOnFaces",
                  {"Mesh": src, "Density": dens, "Seed": frame},
                  distribute_method="RANDOM")
    pts = g.out(dist, "Points")
    ident = g.index()

    def rnd(j, lo=0.0, hi=1.0):
        return g.random(frame * 53.0 + float(j), lo, hi, ident)

    cv = g.attr("gfx_ecv", "FLOAT_VECTOR") * (1.0 / frame_time)
    ang = rnd(1, 0.0, 6.2832)
    sp = cv.length()
    # dragged along with the object, pushed aside and carried up by the air
    # it displaces. The lift is weak: powder rolls out low along the ground
    # and only a few puffs rise; the faster the object, the higher they go,
    # but far below the object's own speed.
    lift = (sp * rnd(4, 0.0, 1.0).pow(2.5) * 0.45).min(_POWDER_LIFT)
    v_new = (g.vec(cv.x, cv.y, 0.0) * rnd(2, 0.25, 0.7)
             + g.vec(g.math("COSINE", ang), g.math("SINE", ang), 0.0)
             * (sp * rnd(3, 0.15, _POWDER_SIDE))
             + g.vec(0.0, 0.0, lift + 0.05))
    pts, caps = g.capture(pts, [v_new, rnd(5, 0.5, 1.6) * _POWDER_WEIGHT,
                                rnd(6, 2.0, 5.5),
                                rnd(7)])
    v_new, weight, life, seed = caps
    pts = g.out(g.node("GeometryNodeRemoveAttribute",
                       {"Geometry": pts, "Name": "*",
                        "Pattern Mode": "Wildcard"}), 0)
    pts = g.out(g.node("GeometryNodeSetPosition",
                       {"Geometry": pts, "Offset": (0.0, 0.0, 0.01)}), 0)
    pts = g.store(pts, "gfx_d_v", v_new, kind="FLOAT_VECTOR")
    pts = g.store(pts, "gfx_d_w", weight)
    pts = g.store(pts, "gfx_d_life", life)
    pts = g.store(pts, "gfx_d_seed", seed)
    pts = g.store(pts, "gfx_d_age", 0.0)
    # a billow, not a wisp: starts larger than a parcel puff and spreads
    # slowly, so it stays visible for seconds
    pts = g.store(pts, "gfx_d_r0", _POWDER_R0)
    pts = g.store(pts, "gfx_d_grow", _POWDER_GROW)
    return pts


def build(g, b, parcels, frame_time, amount, material, ground=None,
          powder=None):
    """Return the dust volume for the parcels of the spray stage.

    With ``ground`` and ``powder`` the moving object itself raises a cloud
    (see ``_powder``), on top of what the parcels leave behind."""
    sim = make_simulation_zone(b, [])
    puffs = V(g, sim.input.outputs["Geometry"])
    dt = V(g, sim.input.outputs["Delta Time"]).max(1e-4)
    seconds = g.out(g.b.add("GeometryNodeInputSceneTime"), "Seconds")

    # ---- drift ----------------------------------------------------------------
    pos = g.position()
    v = g.attr("gfx_d_v", "FLOAT_VECTOR") * (1.0 / (1.0 + dt * _STOP))
    noise = g.node("ShaderNodeTexNoise",
                   {"Vector": pos * 5.0 + g.vec(0.0, 0.0, seconds * 0.35),
                    "Scale": 1.0, "Detail": 1.0})
    turb = (g.out(noise, "Color") - g.vec(0.5, 0.5, 0.5)) * (2.0 * _TURB)
    move = (v + turb + g.vec(0.0, 0.0, -_SINK)) * dt
    puffs, caps = g.capture(puffs, [move, v])
    move, v = caps
    puffs = g.out(g.node("GeometryNodeSetPosition",
                         {"Geometry": puffs, "Offset": move}), 0)
    puffs = g.store(puffs, "gfx_d_v", v, kind="FLOAT_VECTOR")
    puffs = g.store(puffs, "gfx_d_age", g.attr("gfx_d_age") + dt)
    puffs = g.out(g.node("GeometryNodeDeleteGeometry",
                         {"Geometry": puffs,
                          "Selection": g.attr("gfx_d_age").gt(
                              g.attr("gfx_d_life"))},
                         domain="POINT"), 0)

    # ---- new puffs: one per launch, one per landing ---------------------------
    born = g.attr(ATTR_E_AGE).lt(frame_time)
    land = g.attr(ATTR_E_LAND)
    landed = g.math("MULTIPLY", land.gt(0.5), land.lt(1.5))
    pv = g.attr(ATTR_E_VEL, "FLOAT_VECTOR")
    seed = g.attr(ATTR_E_SEED)
    # a landing kicks dust up and outward, a launch drags it along
    v_new = g.switch(landed, pv * 0.3,
                     g.vec(pv.x * 0.12, pv.y * 0.12, 0.10 + seed * 0.25),
                     kind="VECTOR")
    weight = (g.attr(ATTR_E_VOL0) / _VOL_REF).min(8.0)
    fresh, caps = g.capture(parcels, [v_new, weight, 1.2 + seed * 2.2, seed])
    v_new, weight, life, seed = caps
    fresh = g.out(g.node("GeometryNodeDeleteGeometry",
                         {"Geometry": fresh,
                          "Selection": g.math("MAXIMUM", born, landed).lt(0.5)},
                         domain="POINT"), 0)
    fresh = g.out(g.node("GeometryNodeRemoveAttribute",
                         {"Geometry": fresh, "Name": "gfx_*",
                          "Pattern Mode": "Wildcard"}), 0)
    fresh = g.store(fresh, "gfx_d_v", v_new, kind="FLOAT_VECTOR")
    fresh = g.store(fresh, "gfx_d_w", weight)
    fresh = g.store(fresh, "gfx_d_life", life)
    fresh = g.store(fresh, "gfx_d_seed", seed)
    fresh = g.store(fresh, "gfx_d_age", 0.0)
    fresh = g.store(fresh, "gfx_d_r0", 0.012)
    fresh = g.store(fresh, "gfx_d_grow", _GROW)
    join = b.add("GeometryNodeJoinGeometry")
    if ground is not None:
        g.feed(join, 0, _powder(g, ground, powder, frame_time))
    g.feed(join, 0, fresh)
    g.feed(join, 0, puffs)
    g.feed(sim.output, "Geometry", g.out(join, 0))
    puffs = V(g, sim.output.outputs["Geometry"])

    # ---- draw: scatter each puff over its radius, sum into a grid -------------
    dup = g.node("GeometryNodeDuplicateElements",
                 {"Geometry": puffs, "Amount": _SUB}, domain="POINT")
    pts = g.out(dup, "Geometry")
    child = g.out(dup, "Duplicate Index")
    sd = g.attr("gfx_d_seed") * 70000.0

    def rnd(j):
        return g.random(sd + float(j) * 53.0, 0.0, 1.0, child)

    age = g.attr("gfx_d_age")
    r0 = g.attr("gfx_d_r0")
    radius = r0 + age * g.attr("gfx_d_grow")
    off = g.vec(rnd(1) + rnd(2) - 1.0, rnd(3) + rnd(4) - 1.0,
                rnd(5) + rnd(6) - 1.0) * radius
    t = age / g.attr("gfx_d_life")
    fade = sfn.smoothstep(1.0 - t) * (age / 0.08).min(1.0)
    # the same dust in a larger puff is thinner
    thin = (r0 / radius).pow(1.5).max(0.02)
    value = g.attr("gfx_d_w") * fade * thin * amount * (_GAIN / _SUB)
    pts, caps = g.capture(pts, [off, value])
    off, value = caps
    pts = g.out(g.node("GeometryNodeSetPosition",
                       {"Geometry": pts, "Offset": off}), 0)
    ras = g.b.add("GeometryNodeRasterizePoints")
    ras.rasterize_items.new(name="Density")
    g.feed(ras, "Points", pts)
    g.feed(ras, "Voxel Size", _VOXEL)
    g.feed(ras, "Density", value)
    store = g.node("GeometryNodeStoreNamedGrid",
                   {"Name": GRID_NAME, "Grid": g.out(ras, "Density")},
                   data_type="FLOAT")
    vol = g.out(g.node("GeometryNodeSetMaterial",
                       {"Geometry": g.out(store, 0), "Material": material}), 0)
    return vol
