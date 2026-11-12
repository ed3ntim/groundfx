# SPDX-License-Identifier: GPL-3.0-or-later
"""Material clinging to a collider's flanks (gen 3).

The height-field solver cannot put anything on a vertical face, yet a box
dragged through sand comes out dusted along its lower edge and one dragged
through mud comes out spattered. This group adds exactly that, as real
geometry, on a separate *coat object* (one per collider).

Why a separate object: the domain reads the collider's geometry, the coat
reads the domain's surface. On the collider itself that would be a
dependency cycle; on a third object it is a chain.

How it works:

1. Points are scattered once over the collider in its *local* space and
   kept as simulation state, so they ride along rigidly whatever the object
   does. (Deforming colliders are not followed.)
2. Every frame each point looks at the ground just outside its face
   (a ray dropped a little way out along the face normal):

   * if the ground there is at or above the point, the point is **buried**
     and picks material up;
   * while the object moves, points a little above the ground are
     **splashed**, with a per-point reach so the coat thins out upward
     instead of ending in a line.

   A point that is hit stays hit, if its own random number is below the
   element's cling. Sand keeps a dusting, mud nearly everything.
3. Hit points become small lumps lying flat on the face: grains for sand,
   blots for mud, wearing the domain's own material.

The coat object must stay at the world origin with no rotation or scale;
it draws its geometry in world space.
"""
from __future__ import annotations

from ..ng_builder import new_geometry_group
from ..ng_expr import make, V
from ..ng_zones import make_simulation_zone
from ..constants import (
    NG_COAT, ELEM_SAND, ELEM_MUD, ATTR_DIST, ATTR_DAMP, ATTR_GEO, ATTR_SHORE,
)

IN_COLLIDER = "Collider"
IN_DOMAIN = "Domain"
IN_MATERIAL = "Material"
IN_DENSITY = "Density"
IN_SPLASH = "Splash Height"
IN_CLING = "Cling"
IN_REACH = "Reach"
OUT_GEOMETRY = "Geometry"

_CONTACT = 0.003      # metres: ground this close above/below counts as buried
_MOVING = 0.0003      # metres per frame that count as motion
_RAY_UP = 2.0

# Per-element authored look: lump radius range (metres), size power law,
# flatness on the face, icosphere level, surface break-up, default density
# (points per square metre of collider), splash height, cling.
PROFILES = {
    ELEM_SAND: dict(r_min=0.0003, r_max=0.0009, power=3.0, flat=0.6, ico=1,
                    rough=1.2, density=2000000.0, splash=0.04, cling=0.6,
                    damp=0.15, shore=0.0, run=1.0),
    # mud blots run down the face: longer than wide, ragged, mostly small
    ELEM_MUD: dict(r_min=0.0006, r_max=0.0045, power=4.0, flat=0.3, ico=2,
                   rough=1.7, density=220000.0, splash=0.09, cling=0.85,
                   damp=1.0, shore=0.7, run=2.2),
}


def group_name(element: str) -> str:
    return f"{NG_COAT}_{element.title()}"


def defaults(element: str) -> dict:
    return PROFILES[element]


def _interface(b, prof):
    b.input(IN_COLLIDER, "NodeSocketObject")
    b.input(IN_DOMAIN, "NodeSocketObject")
    b.input(IN_MATERIAL, "NodeSocketMaterial")
    b.input(IN_DENSITY, "NodeSocketFloat", default=prof["density"], min=0.0,
            description="Candidate points per square metre of the collider")
    b.input(IN_SPLASH, "NodeSocketFloat", default=prof["splash"], min=0.0,
            max=1.0, subtype="DISTANCE",
            description="How far above the ground a moving object is spattered")
    b.input(IN_CLING, "NodeSocketFloat", default=prof["cling"], min=0.0,
            max=1.0, description="Share of touched points that keep material")
    b.input(IN_REACH, "NodeSocketFloat", default=0.012, min=0.0,
            subtype="DISTANCE",
            description="How far outside a face the ground is sampled")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")


def build(name: str = NG_COAT, element: str = ELEM_SAND):
    prof = PROFILES[element]
    tree = new_geometry_group(name)
    b, g = make(tree)
    _interface(b, prof)
    gin, gout = b.group_io()

    def I(key):  # noqa: E743
        return g.out(gin, key)

    coll = g.node("GeometryNodeObjectInfo", {"Object": I(IN_COLLIDER)},
                  transform_space="ORIGINAL")
    xform = g.out(coll, "Transform")
    dom = g.node("GeometryNodeObjectInfo", {"Object": I(IN_DOMAIN)},
                 transform_space="RELATIVE")
    ground = g.out(g.node("GeometryNodeRealizeInstances",
                          {"Geometry": g.out(dom, "Geometry")}), 0)

    def to_world(p):
        return g.out(g.node("FunctionNodeTransformPoint",
                            {"Vector": p, "Transform": xform}), 0)

    def dir_world(d):
        return g.out(g.node("FunctionNodeTransformDirection",
                            {"Direction": d, "Transform": xform}), 0).normalize()

    # ---- candidate points, once, in collider space ---------------------------
    # a thinner set in the viewport keeps playback light
    viewport = g.out(b.add("GeometryNodeIsViewport"), 0)
    density = I(IN_DENSITY) * g.switch(viewport, 1.0, 0.15)
    dist_node = g.node("GeometryNodeDistributePointsOnFaces",
                       {"Mesh": g.out(coll, "Geometry"),
                        "Density": density, "Seed": 11},
                       distribute_method="RANDOM")
    pts = g.out(dist_node, "Points")
    pts = g.store(pts, "gfx_n", g.out(dist_node, "Normal"), kind="FLOAT_VECTOR")
    ident = g.index()
    pts = g.store(pts, "gfx_r", g.random(31, 0.0, 1.0, ident))
    pts = g.store(pts, "gfx_r2", g.random(32, 0.0, 1.0, ident))
    pts = g.store(pts, "gfx_stuck", 0.0)
    pts = g.store(pts, "gfx_pw", to_world(g.position()), kind="FLOAT_VECTOR")

    # ---- per frame: buried or splashed ------------------------------------------
    sim = make_simulation_zone(b, [])
    g.feed(sim.input, "Geometry", pts)
    geo = V(g, sim.input.outputs["Geometry"])
    pw = to_world(g.position())
    nw = dir_world(g.attr("gfx_n", "FLOAT_VECTOR"))
    out_xy = g.vec(nw.x, nw.y, 0.0).normalize()
    sample = pw + out_xy * I(IN_REACH)
    ray = g.node("GeometryNodeRaycast",
                 {"Target Geometry": ground,
                  "Source Position": g.vec(sample.x, sample.y, pw.z + _RAY_UP),
                  "Ray Direction": (0.0, 0.0, -1.0), "Ray Length": 20.0},
                 data_type="FLOAT")
    hit = g.out(ray, "Is Hit")
    above = pw.z - g.out(ray, "Hit Position").z
    moved = (pw - g.attr("gfx_pw", "FLOAT_VECTOR")).length().gt(_MOVING)
    r = g.attr("gfx_r")
    buried = above.lt(_CONTACT)
    splashed = g.math("MULTIPLY", moved, above.lt(I(IN_SPLASH) * r * r * r))
    keeps = g.attr("gfx_r2").lt(I(IN_CLING))
    got = g.math("MULTIPLY", g.math("MULTIPLY", buried.max(splashed), hit), keeps)
    geo, caps = g.capture(geo, [got, pw])
    geo = g.store(geo, "gfx_stuck", g.attr("gfx_stuck").max(caps[0]))
    geo = g.store(geo, "gfx_pw", caps[1], kind="FLOAT_VECTOR")
    g.feed(sim.output, "Geometry", geo)
    geo = V(g, sim.output.outputs["Geometry"])

    # ---- lumps on the points that were hit -----------------------------------------
    hit_pts = g.out(g.node("GeometryNodeDeleteGeometry",
                           {"Geometry": geo,
                            "Selection": g.attr("gfx_stuck").lt(0.5)},
                           domain="POINT"), 0)
    nw2 = dir_world(g.attr("gfx_n", "FLOAT_VECTOR"))
    t = g.attr("gfx_r")
    # sizes from an independent draw, so the high splashes are not all tiny
    s = g.random(33, 0.0, 1.0, g.index())
    radius = prof["r_min"] + (prof["r_max"] - prof["r_min"]) * s.pow(prof["power"])
    placed = g.out(g.node("GeometryNodeSetPosition",
                          {"Geometry": hit_pts,
                           "Position": to_world(g.position())
                           + nw2 * (radius * prof["flat"] * 0.5)}), 0)
    placed = g.store(placed, "gfx_nw", nw2, kind="FLOAT_VECTOR")
    placed = g.store(placed, "gfx_rad", radius)
    rot = g.out(g.node("FunctionNodeAlignRotationToVector",
                       {"Vector": g.attr("gfx_nw", "FLOAT_VECTOR")},
                       axis="Z"), 0)
    # then turn the lump about the face normal until its long axis hangs down
    rot = g.out(g.node("FunctionNodeAlignRotationToVector",
                       {"Rotation": rot, "Vector": (0.0, 0.0, -1.0)},
                       axis="Y", pivot_axis="Z"), 0)
    rad = g.attr("gfx_rad")
    scale = g.vec(rad * (0.7 + t * 0.5),
                  rad * (0.8 + g.random(34, 0.0, 1.0, g.index()) * prof["run"]),
                  rad * prof["flat"])
    ico = g.node("GeometryNodeMeshIcoSphere",
                 {"Radius": 1.0, "Subdivisions": prof["ico"]})
    iop = g.node("GeometryNodeInstanceOnPoints",
                 {"Points": placed, "Instance": g.out(ico, "Mesh"),
                  "Rotation": rot, "Scale": scale})
    inst = g.store(g.out(iop, 0), "gfx_rad", rad, domain="INSTANCE")
    mesh = g.out(g.node("GeometryNodeRealizeInstances", {"Geometry": inst}), 0)
    lump = g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": g.position(),
                         "Scale": 0.35 / prof["r_max"], "Detail": 2.0}), 0) - 0.5
    nrm = g.out(b.add("GeometryNodeInputNormal"), "Normal")
    mesh = g.out(g.node("GeometryNodeSetPosition",
                        {"Geometry": mesh,
                         "Offset": nrm * (lump * g.attr("gfx_rad")
                                          * prof["rough"])}), 0)
    mesh = g.out(g.node("GeometryNodeSetShadeSmooth", {0: mesh}), 0)
    mesh = g.store(mesh, ATTR_DIST, 1.0)
    mesh = g.store(mesh, ATTR_GEO, 1.0)
    mesh = g.store(mesh, ATTR_DAMP, prof["damp"])
    mesh = g.store(mesh, ATTR_SHORE, prof["shore"])
    mesh = g.out(g.node("GeometryNodeSetMaterial",
                        {"Geometry": mesh, "Material": I(IN_MATERIAL)}), 0)
    g.feed(gout, OUT_GEOMETRY, mesh)
    b.layout()
    return tree
