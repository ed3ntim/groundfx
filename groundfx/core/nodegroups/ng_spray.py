# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
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

* **Strings** (mud). Wet clay does not leave as balls: it tears. A share of
  the pieces becomes a short curve along its flight, thick at both ends and
  thin in the middle where it is about to snap, sagging under its own
  weight. It stretches with the time in the air and, past a length, snaps:
  the middle disappears and the two ends fly on as drops.
"""
from __future__ import annotations

from ..ng_builder import new_geometry_group
from ..ng_expr import make
from ..constants import (
    NG_SPRAY, ATTR_E_VEL, ATTR_E_VOL0, ATTR_E_AGE, ATTR_E_SEED, ATTR_E_V0,
    ATTR_E_DRAG, ATTR_DIST, ATTR_COMP, ATTR_SHORE,
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
IN_POWDER = "Powder"
IN_WET = "Water Share"
IN_WET_MATERIAL = "Water Material"
IN_STRINGS = "Strings"
OUT_GEOMETRY = "Geometry"

ATTR_GRAIN_ID = "gfx_grain_id"
_PACKING = 0.6        # share of a heap's volume that is grain
_BLOB = 2.5           # initial clump radius in parcel radii
_STRING_PTS = 13      # points per string
_STRING_MAX = 12.0    # a string snaps beyond this many piece radii
_FLAT = 0.5           # cross-section of a mud piece: this much flatter than wide
_DROP_STRETCH = 0.5   # extra length of a drop per m/s, in radii
_RAG = 0.35           # how ragged the cross-section is (share of the radius)


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
    b.input(IN_WET, "NodeSocketFloat", default=0.0, min=0.0, max=1.0,
            description="Share of the pieces that are drops of dirty water "
                        "instead of solid material (mud)")
    b.input(IN_WET_MATERIAL, "NodeSocketMaterial")
    b.input(IN_STRINGS, "NodeSocketFloat", default=0.0, min=0.0, max=1.0,
            description="Share of the pieces that tear into strings "
                        "(wet clay, mud)")
    if ng_dust.supported():
        b.input(IN_DUST, "NodeSocketFloat", default=0.0, min=0.0, max=4.0,
                description="Fine fraction that stays in the air as haze")
        b.input(IN_DUST_MATERIAL, "NodeSocketMaterial")
        b.input(IN_POWDER, "NodeSocketFloat", default=0.0, min=0.0, max=4.0,
                description="Cloud whirled up by the moving object itself "
                            "(powder snow), scaled by Dust")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")


def _tube(g, curves, profile):
    tube = g.out(g.node("GeometryNodeCurveToMesh",
                        {"Curve": curves, "Profile Curve": profile,
                         "Scale": g.attr("gfx_s_rad"), "Fill Caps": False}), 0)
    return g.out(g.node("GeometryNodeSetShadeSmooth", {0: tube}), 0)


def _strings(g, pts, p, vel, kill, radius, gid, t, wet, share, material,
             wet_material, rnd, viewport):
    """Every mud piece as a shaped body (tube mesh), not a ball.

    Each piece becomes ``_STRING_PTS`` points on a line through it, then one
    curve, then a tube. Three kinds by ``gid``:

    * ``gid < wet``: drops of muddy water. Smooth and round in section,
      pointing exactly along the current flight (it bends with the arc):
      a round head in front, a tail behind, longer the faster they fly.
    * ``wet <= gid < wet + share``: strings. Along the flight with a random
      tilt, longer the longer they fly, a blob at each end and a neck in
      the middle, sagging. Past ``_STRING_MAX`` radii they snap: the middle
      goes, the two ends fly on as stubs.
    * the rest: clots. Shaped like the drops, with a ragged, flattened
      section and a little scatter in their heading.

    Every body keeps the volume of the ball it replaces.
    """
    sel = g.math("MULTIPLY", share.gt(0.0), 1.0 - kill)
    water = gid.lt(wet)
    is_long = g.math("MULTIPLY", 1.0 - water, gid.lt(wet + share))
    pts = g.store(pts, "gfx_s_p", p, kind="FLOAT_VECTOR")
    pts = g.store(pts, "gfx_s_v", vel, kind="FLOAT_VECTOR")
    pts = g.store(pts, "gfx_s_r", radius)
    pts = g.store(pts, "gfx_s_t", t)
    pts = g.store(pts, "gfx_s_id", g.index())
    pts = g.store(pts, "gfx_s_long", is_long)
    pts = g.store(pts, "gfx_s_water", water)
    pts = g.store(pts, "gfx_s_gid", gid)
    pts = g.out(g.node("GeometryNodeDeleteGeometry",
                       {"Geometry": pts, "Selection": sel.lt(0.5)},
                       domain="POINT"), 0)
    v = g.attr("gfx_s_v", "FLOAT_VECTOR")
    r = g.attr("gfx_s_r")
    lng = g.attr("gfx_s_long")
    wat = g.attr("gfx_s_water")
    speed = v.length()
    # heading: drops exactly along the flight, clots nearly, strings loosely
    tilt = g.vec(rnd(30, -0.6, 0.6), rnd(31, -0.6, 0.6), rnd(32, -0.4, 0.8))
    scatter = (lng * 0.4 + (1.0 - lng) * 0.3) * (1.0 - wat)
    d = (v.normalize() + tilt * scatter).normalize()
    string_len = (r * (3.0 + rnd(33, 0.0, 4.0))
                  + speed * g.attr("gfx_s_t").max(0.0) * rnd(34, 0.05, 0.3))
    # drops and clots stretch with their speed: round when slow, a teardrop
    # up to about twice as long as wide when fast (the length is the whole
    # body: round at 2.6 radii)
    stretch = (speed * _DROP_STRETCH).min(1.4)
    drop_len = r * (2.6 + stretch * 0.9 + rnd(36, 0.0, 0.8)
                    + (1.0 - wat) * rnd(37, 0.0, 0.6))
    length = g.switch(lng.gt(0.5), drop_len, string_len.min(r * _STRING_MAX * 1.6))
    pts = g.store(pts, "gfx_s_d", d, kind="FLOAT_VECTOR")
    pts = g.store(pts, "gfx_s_len", length)
    pts = g.store(pts, "gfx_s_snap", string_len.gt(r * _STRING_MAX) * lng)
    pts = g.store(pts, "gfx_s_twist", rnd(35, -1.0, 1.0))

    dup = g.node("GeometryNodeDuplicateElements",
                 {"Geometry": pts, "Amount": _STRING_PTS}, domain="POINT")
    cp = g.out(dup, "Geometry")
    k = g.out(dup, "Duplicate Index")
    s = k / float(_STRING_PTS - 1)              # 0..1, tail to head
    u = s * 2.0 - 1.0                           # -1..1, 0 in the middle
    ln = g.attr("gfx_s_len")
    dd = g.attr("gfx_s_d", "FLOAT_VECTOR")
    side = g.vec(dd.y * -1.0, dd.x, 0.0).normalize()
    lng = g.attr("gfx_s_long")
    wat = g.attr("gfx_s_water")
    bend = (1.0 - u * u) * lng
    pos = (g.attr("gfx_s_p", "FLOAT_VECTOR") + dd * (u * ln * 0.5)
           + g.vec(0.0, 0.0, bend * ln * -0.3)
           + side * (bend * ln * 0.25 * g.attr("gfx_s_twist")))
    # Radius closes to zero at both ends (round tips, no caps) and is scaled
    # so the piece keeps the volume of its ball: a body of length L and
    # radius R holds about as much as a ball of radius (R^2 L / 2)^(1/3).
    r0 = g.attr("gfx_s_r")
    keep = (r0 * 2.0 / ln.max(1e-6)).sqrt()
    # strings: blobs at both ends, a neck in the middle
    neck = (0.4 + 0.6 * u.abs().pow(2.0)) * (1.0 - u.abs().pow(8.0)).max(0.0).sqrt()
    # drops: a round head in front (u = 1), a tail tapering to a point behind
    head = (1.0 - u.max(0.0).pow(2.0)).max(0.0).sqrt()
    tail = (1.0 - u.min(0.0).abs().pow(1.3)).max(0.0)
    drop = head * tail
    # lumpy clots: one or two smooth bulges (a random value per point would
    # ring the body like a screw); water drops stay smooth
    pid = g.attr("gfx_s_id")
    phase = g.random(77, 0.0, 6.2832, pid)
    freq = g.random(78, 2.0, 6.0, pid)
    lump = 1.0 + (g.math("SINE", s * freq + phase) * g.random(79, 0.1, 0.3, pid)
                  * (1.0 - wat))
    shape = g.switch(lng.gt(0.5), drop, neck)
    rad = r0 * keep * 1.35 * lump * shape
    snapped = g.math("MULTIPLY", g.attr("gfx_s_snap"), u.abs().lt(0.6))
    cp, caps = g.capture(cp, [pos, rad, k, snapped])
    pos, rad, k, snapped = caps
    cp = g.out(g.node("GeometryNodeSetPosition",
                      {"Geometry": cp, "Position": pos}), 0)
    cp = g.out(g.node("GeometryNodeDeleteGeometry",
                      {"Geometry": cp, "Selection": snapped},
                      domain="POINT"), 0)
    cp = g.store(cp, "gfx_s_rad", rad)
    curves = g.out(g.node("GeometryNodePointsToCurves",
                          {"Points": cp,
                           # a snapped string is two curves, one per end
                           "Curve Group ID": (g.attr("gfx_s_id") * 2.0
                                              + (k / float(_STRING_PTS)).gt(0.5)
                                              * g.attr("gfx_s_snap")).round(),
                           "Weight": k}), 0)
    curves = g.store(curves, "velocity", g.attr("gfx_s_v", "FLOAT_VECTOR"),
                     kind="FLOAT_VECTOR")
    # Cycles does not render the curves of a mesh object: make tubes. The
    # profile is scaled per point by the radius, which is zero at the tips.
    curves = g.out(g.node("GeometryNodeCurveSplineType",
                          {"Curve": curves}, spline_type="CATMULL_ROM"), 0)
    curves = g.out(g.node("GeometryNodeSetSplineResolution",
                          {"Curve": curves,
                           "Resolution": g.switch(viewport, 3, 1, kind="INT")}), 0)
    # each piece turned its own way about its axis
    curves = g.out(g.node("GeometryNodeSetCurveTilt",
                          {"Curve": curves,
                           "Tilt": g.random(80, 0.0, 6.2832, g.attr("gfx_s_id"))}), 0)
    res = g.switch(viewport, 10, 5, kind="INT")
    circle = g.out(g.node("GeometryNodeCurvePrimitiveCircle",
                          {"Resolution": res, "Radius": 1.0}), "Curve")
    # Mud: a ragged, flattened section (pushing the finished skin along its
    # normals instead folds it into rings). Water: round.
    pp = g.position()
    jag = g.random(84, 1.0 - _RAG, 1.0 + _RAG, g.index())
    ragged = g.out(g.node("GeometryNodeSetPosition",
                          {"Geometry": circle,
                           "Position": g.vec(pp.x * jag, pp.y * jag * _FLAT, 0.0)}), 0)
    split = g.node("GeometryNodeSeparateGeometry",
                   {"Geometry": curves, "Selection": g.attr("gfx_s_water").gt(0.5)},
                   domain="CURVE")
    drops = _tube(g, g.out(split, "Selection"), circle)
    mud = _tube(g, g.out(split, "Inverted"), ragged)
    # The mud wears the ground's own shader: mark it churned, loose and
    # soaked, like the mud it was torn from.
    mud = g.store(mud, ATTR_GRAIN_ID, g.attr("gfx_s_gid"))
    mud = g.store(mud, ATTR_DIST, 1.0)
    mud = g.store(mud, ATTR_COMP, 0.0)
    mud = g.store(mud, ATTR_SHORE, 0.7)
    mud = g.out(g.node("GeometryNodeSetMaterial",
                       {"Geometry": mud, "Material": material}), 0)
    drops = g.store(drops, ATTR_GRAIN_ID, g.attr("gfx_s_gid"))
    drops = g.out(g.node("GeometryNodeSetMaterial",
                         {"Geometry": drops, "Material": wet_material}), 0)
    join = g.b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, drops)
    g.feed(join, 0, mud)
    out = g.out(join, 0)
    for pat in ("gfx_s_*", "gfx_e_*"):
        out = g.out(g.node("GeometryNodeRemoveAttribute",
                           {"Geometry": out, "Name": pat,
                            "Pattern Mode": "Wildcard"}), 0)
    return out


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
    # Wet ground does not only throw clots: much of what flies is water
    # carrying silt, in drops smaller than the clots.
    gid = rnd(16)
    is_drop = gid.lt(I(IN_WET))
    radius = radius * (1.0 - is_drop * 0.5)
    pts, caps = g.capture(pts, [p, vel, kill, radius, gid, t])
    p, vel, kill, radius, gid, t = caps
    strings = _strings(g, pts, p, vel, kill, radius, gid, t, I(IN_WET),
                       I(IN_STRINGS), I(IN_MATERIAL), I(IN_WET_MATERIAL),
                       rnd, viewport)
    # With strings on (mud) every piece, drops included, is a shaped body.
    kill = g.math("MAXIMUM", kill, I(IN_STRINGS).gt(0.0))

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
    pts = g.out(g.node("GeometryNodeSetMaterial",
                       {"Geometry": pts,
                        "Selection": g.attr(ATTR_GRAIN_ID).lt(I(IN_WET)),
                        "Material": I(IN_WET_MATERIAL)}), 0)

    out = b.add("GeometryNodeJoinGeometry")
    if ng_dust.supported():
        haze = ng_dust.build(g, b, parcels, I(IN_FRAME_TIME), I(IN_DUST),
                             I(IN_DUST_MATERIAL), ground=ground,
                             powder=I(IN_POWDER))
        sw = g.node("GeometryNodeSwitch",
                    {"Switch": I(IN_DUST).gt(0.0), "True": haze},
                    input_type="GEOMETRY")
        g.feed(out, 0, g.out(sw, 0))
    g.feed(out, 0, pts)
    g.feed(out, 0, strings)
    for key in ("Instances", "Volume", "Curve"):
        g.feed(out, 0, g.out(sep, key))
    g.feed(out, 0, ground)
    g.feed(gout, OUT_GEOMETRY, g.out(out, 0))
    b.layout()
    return tree
