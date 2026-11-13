# SPDX-License-Identifier: GPL-3.0-or-later
"""The spray stage (gen 4): airborne parcels become grains.

The solver flies a few thousand parcels, each a few cubic millimetres to a
cubic centimetre of sand. Shown as they are they would be lumps. This stage,
the last modifier on the domain, turns every parcel into the grains it
stands for, and it does so analytically: no extra simulation, no state.

* **Count.** A parcel's volume divided by the volume of one grain (with
  packing) is the number of grains it really holds; ``Detail`` scales that.
  At Detail 1 the render shows about as many grains as real sand would.
  With fewer grains each gets larger, so the volume on screen stays.
* **Along the path.** Every grain sits a random fraction of a frame back on
  the parcel's trajectory. Parcels launched frame after frame thus close up
  into one continuous sheet instead of a string of puffs, and a grain that
  has not left the ground yet (its time is before the launch) is not drawn.
* **Spread.** Every grain has its own small velocity offset, a fixed share
  of the launch speed. The cloud of a parcel grows with its time in the
  air: a tight clump at the start, a veil at the end, as in footage.
* **Landing.** A grain is removed once it is below the visible ground. The
  solver keeps a landed parcel for a few frames (its volume is already back
  in the bed), so the grains above it finish their fall instead of popping.

Grains are points (rendered as spheres by Cycles) with a ``velocity``
attribute, so motion blur works without extra geometry.
"""
from __future__ import annotations

from ..ng_builder import new_geometry_group
from ..ng_expr import make
from ..constants import (
    NG_SPRAY, ATTR_E_VEL, ATTR_E_VOL0, ATTR_E_AGE, ATTR_E_SEED, ATTR_E_V0,
    ATTR_E_DRAG,
)
from .ng_ejecta import GRAVITY
from . import ng_dust

IN_GEOMETRY = "Geometry"
IN_GRAIN = "Grain Size"
IN_DETAIL = "Detail"
IN_VIEW_DETAIL = "Viewport Detail"
IN_MAX = "Max Grains"
IN_SPREAD = "Spread"
IN_CLUMPS = "Clumps"
IN_FRAME_TIME = "Frame Time"
IN_MATERIAL = "Material"
IN_DUST = "Dust"
IN_DUST_MATERIAL = "Dust Material"
OUT_GEOMETRY = "Geometry"

ATTR_GRAIN_ID = "gfx_grain_id"
_PACKING = 0.6        # share of a heap's volume that is grain
_BLOB = 2.5           # initial clump radius in parcel radii


def _interface(b):
    b.input(IN_GEOMETRY, "NodeSocketGeometry")
    b.input(IN_GRAIN, "NodeSocketFloat", default=0.0005, min=1e-5, max=0.02,
            subtype="DISTANCE", description="Diameter of a typical grain")
    b.input(IN_DETAIL, "NodeSocketFloat", default=1.0, min=0.001, max=4.0,
            description="Grains drawn per real grain in renders")
    b.input(IN_VIEW_DETAIL, "NodeSocketFloat", default=0.02, min=0.001,
            max=4.0, description="The same in the viewport")
    b.input(IN_MAX, "NodeSocketInt", default=240, min=1, max=4000,
            description="Upper limit of grains per parcel")
    b.input(IN_SPREAD, "NodeSocketFloat", default=0.07, min=0.0, max=1.0,
            description="Velocity scatter of the grains, as a share of the "
                        "launch speed")
    b.input(IN_CLUMPS, "NodeSocketFloat", default=2.5, min=0.0, max=20.0,
            description="How much larger the rare big lumps are")
    b.input(IN_FRAME_TIME, "NodeSocketFloat", default=1.0 / 24.0, min=1e-4,
            description="Seconds per frame (scene frame rate)")
    b.input(IN_MATERIAL, "NodeSocketMaterial")
    if ng_dust.supported():
        b.input(IN_DUST, "NodeSocketFloat", default=0.0, min=0.0, max=4.0,
                description="Fine fraction that stays in the air as haze")
        b.input(IN_DUST_MATERIAL, "NodeSocketMaterial")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")


def build(name: str = NG_SPRAY):
    tree = new_geometry_group(name)
    b, g = make(tree)
    _interface(b)
    gin, gout = b.group_io()

    def I(key):  # noqa: E743
        return g.out(gin, key)

    sep = g.node("GeometryNodeSeparateComponents",
                 {"Geometry": I(IN_GEOMETRY)})
    ground = g.out(sep, "Mesh")
    parcels = g.out(sep, "Point Cloud")
    # scatter bookkeeping of the solver is of no use from here on
    parcels = g.out(g.node("GeometryNodeRemoveAttribute",
                           {"Geometry": parcels, "Name": "gfx_s_*",
                            "Pattern Mode": "Wildcard"}), 0)

    viewport = g.out(b.add("GeometryNodeIsViewport"), 0)
    detail = g.switch(viewport, I(IN_DETAIL), I(IN_VIEW_DETAIL))
    grain = I(IN_GRAIN)
    grain_vol = grain * grain * grain * (0.5236 / _PACKING)
    count = (g.attr(ATTR_E_VOL0) / grain_vol * detail).round().max(1.0)
    count = count.min(I(IN_MAX))
    dup = g.node("GeometryNodeDuplicateElements",
                 {"Geometry": parcels, "Amount": count}, domain="POINT")
    pts = g.out(dup, "Geometry")
    child = g.out(dup, "Duplicate Index")
    seed = g.attr(ATTR_E_SEED) * 90000.0

    def rnd(j, lo=0.0, hi=1.0):
        return g.random(seed + float(j) * 101.0, lo, hi, child)

    def tri(j):
        """Random vector, denser toward the centre than a cube."""
        return g.vec(rnd(j) + rnd(j + 1) - 1.0, rnd(j + 2) + rnd(j + 3) - 1.0,
                     rnd(j + 4) + rnd(j + 5) - 1.0)

    dt = I(IN_FRAME_TIME)
    v = g.attr(ATTR_E_VEL, "FLOAT_VECTOR")
    lag = rnd(1) * dt
    t = g.attr(ATTR_E_AGE) - lag          # this grain's own time in the air
    # Most grains stay close to the parcel (dense core), a few stray far
    # (thin rim): the scatter has a long tail.
    stray = 1.0 + rnd(17).pow(4.0) * 3.5
    dv = tri(2) * (g.attr(ATTR_E_V0) * I(IN_SPREAD) * stray)
    # Fines feel the air more than the clump they left with: they fall
    # behind along the path and hang as a veil behind the sheet.
    fine = rnd(18).pow(3.0) * 0.45
    dv = dv + v * (fine * -1.0)
    blob = tri(8) * ((g.attr(ATTR_E_VOL0) * 0.2387).pow(1.0 / 3.0) * _BLOB)
    back = v * (lag * -1.0) + g.vec(0.0, 0.0, lag * lag * (-0.5 * GRAVITY))
    # The air takes a piece's extra speed away at the parcel's drag rate, so
    # the drift apart levels off. Without it powder that hangs for seconds
    # (snow) spreads without limit, far past where it could ever get.
    rate = g.attr(ATTR_E_DRAG) * g.attr(ATTR_E_V0)
    slow = 1.0 / (1.0 + rate * t.max(0.0))
    p = g.position() + back + blob + dv * (t.max(0.0) * slow)
    vel = v + g.vec(0.0, 0.0, lag * GRAVITY) + dv * (slow * slow)

    ray = g.node("GeometryNodeRaycast",
                 {"Target Geometry": ground,
                  "Source Position": p + g.vec(0.0, 0.0, 3.0),
                  "Ray Direction": (0.0, 0.0, -1.0), "Ray Length": 6.0},
                 data_type="FLOAT")
    under = g.math("MULTIPLY", g.out(ray, "Is Hit"),
                   g.out(ray, "Hit Position").z.gt(p.z + 0.0003))
    kill = g.math("MAXIMUM", t.lt(0.0), under)
    # fewer grains: each one larger, so the volume on screen stays
    fat = (1.0 / detail).pow(1.0 / 3.0).max(1.0).min(3.0)
    radius = (grain * 0.5 * rnd(14, 0.6, 1.5) * (1.0 + rnd(15).pow(8.0) * I(IN_CLUMPS))
              * fat)
    pts, caps = g.capture(pts, [p, vel, kill, radius, rnd(16)])
    p, vel, kill, radius, gid = caps

    pts = g.out(g.node("GeometryNodeDeleteGeometry",
                       {"Geometry": pts, "Selection": kill},
                       domain="POINT"), 0)
    pts = g.out(g.node("GeometryNodeRemoveAttribute",
                       {"Geometry": pts, "Name": "gfx_e_*",
                        "Pattern Mode": "Wildcard"}), 0)
    pts = g.out(g.node("GeometryNodeSetPosition",
                       {"Geometry": pts, "Position": p}), 0)
    pts = g.out(g.node("GeometryNodeSetPointRadius",
                       {"Points": pts, "Radius": radius}), 0)
    pts = g.store(pts, "velocity", vel, kind="FLOAT_VECTOR")
    pts = g.store(pts, ATTR_GRAIN_ID, gid)
    pts = g.out(g.node("GeometryNodeSetMaterial",
                       {"Geometry": pts, "Material": I(IN_MATERIAL)}), 0)

    out = b.add("GeometryNodeJoinGeometry")
    if ng_dust.supported():
        haze = ng_dust.build(g, b, parcels, I(IN_FRAME_TIME), I(IN_DUST),
                             I(IN_DUST_MATERIAL))
        sw = g.node("GeometryNodeSwitch",
                    {"Switch": I(IN_DUST).gt(0.0), "True": haze},
                    input_type="GEOMETRY")
        g.feed(out, 0, g.out(sw, 0))
    g.feed(out, 0, pts)
    for key in ("Instances", "Volume", "Curve"):
        g.feed(out, 0, g.out(sep, key))
    g.feed(out, 0, ground)
    g.feed(gout, OUT_GEOMETRY, g.out(out, 0))
    b.layout()
    return tree
