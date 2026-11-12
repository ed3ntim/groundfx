# SPDX-License-Identifier: GPL-3.0-or-later
"""The surface stage (gen 3): from simulation grid to a believable surface.

A second Geometry Nodes modifier, placed after the solver. The solver stays a
plain height field on a constant grid (fast, bakeable, testable); this stage
is pure display and never feeds back into the simulation.

1. **Upsample.** Catmull-Clark subdivision removes the cell facets. The level
   is separate for viewport and render, so playback stays as fast as the
   solver while the render gets a millimetre mesh.
2. **Meso relief from simulation fields.** Undisturbed sand carries wind
   ripples; where the solver reports disturbance (``gfx_dist``) the ripples
   are wiped out and replaced by the uneven relief of dug-up sand; packed
   tracks (``gfx_comp``) are flat. The relief is real geometry, so it casts
   shadows and holds up in a low sun.
3. **Crumbs.** Loosened damp sand breaks into small lumps that lie on the
   surface. They are scattered as real meshes (a few millimetres, irregular,
   half sunk) on disturbed ground only. Their silhouettes and contact
   shadows are what a close-up needs and no shader can fake.
4. **Surround.** Optionally the domain is embedded in a much larger static
   field: a fine ring that continues the ripples seamlessly, then a coarse
   far field with broad dunes to the horizon. The domain no longer floats as
   a slab in empty space.

The relief functions live in ``surface_fn`` and are shared with the shader.
"""
from __future__ import annotations

import math

from ..ng_builder import new_geometry_group
from ..ng_expr import make
from ..constants import (
    NG_SURFACE, ATTR_COMP, ATTR_DIST, ATTR_DAMP, ATTR_GEO, ATTR_PEBBLE,
    ATTR_SHORE, ELEM_SAND, ELEM_MUD,
    DEFAULT_MATERIAL_HEIGHT,
)
from .. import surface_fn as sfn

IN_GEOMETRY = "Geometry"
IN_RENDER_LEVEL = "Render Level"
IN_VIEW_LEVEL = "Viewport Level"
IN_RIPPLE_HEIGHT = "Ripple Height"
IN_RIPPLE_LENGTH = "Ripple Length"
IN_WIND = "Wind Direction"
IN_CLOD_HEIGHT = "Clod Height"
IN_CRUMBS = "Crumbs"
IN_PEBBLES = "Pebbles"
IN_SURROUND = "Surround"
IN_DOMAIN_SIZE = "Domain Size"
IN_MATERIAL_HEIGHT = "Material Height"
IN_MATERIAL = "Material"
IN_UNDULATION = "Undulation"
IN_WATER = "Water"
IN_WATER_LEVEL = "Water Level"
IN_WATER_MATERIAL = "Water Material"
OUT_GEOMETRY = "Geometry"

_RING_CELL = 0.006     # target cell of the fine ring in renders (metres)
_UNDER_SINK = 0.0004   # the ring dips this far where it runs under the domain
_FAR_CELLS = 33        # far field = this many cells of 3 x domain size
_DUNE_HEIGHT = {ELEM_SAND: 0.9, ELEM_MUD: 0.12}   # metres, far relief
_SHORE_BAND = 0.012    # metres above the water over which mud stays soaked
_CRUMB_MIN = 0.001    # crumb radius range, metres
_CRUMB_MAX = 0.005
_ATTR_SINK = "gfx_sink"
_ATTR_LOOSE = "gfx_loose"
_ATTR_CRUMB = "gfx_crumb"


def _interface(b):
    b.input(IN_GEOMETRY, "NodeSocketGeometry")
    b.input(IN_RENDER_LEVEL, "NodeSocketInt", default=2, min=0, max=4,
            description="Subdivision of the simulation grid in renders")
    b.input(IN_VIEW_LEVEL, "NodeSocketInt", default=0, min=0, max=3,
            description="Subdivision in the viewport (0 keeps playback fast)")
    b.input(IN_RIPPLE_HEIGHT, "NodeSocketFloat", default=0.004, min=0.0,
            max=0.05, subtype="DISTANCE",
            description="Crest-to-trough height of the wind ripples")
    b.input(IN_RIPPLE_LENGTH, "NodeSocketFloat", default=0.07, min=0.01,
            max=1.0, subtype="DISTANCE")
    b.input(IN_WIND, "NodeSocketFloat", default=math.radians(20.0),
            subtype="ANGLE")
    b.input(IN_CLOD_HEIGHT, "NodeSocketFloat", default=0.004, min=0.0,
            max=0.05, subtype="DISTANCE",
            description="Relief of disturbed material")
    b.input(IN_CRUMBS, "NodeSocketFloat", default=9000.0, min=0.0,
            max=100000.0,
            description="Loose lumps per square metre of disturbed ground")
    b.input(IN_PEBBLES, "NodeSocketFloat", default=220.0, min=0.0,
            max=20000.0,
            description="Small stones and shell bits per square metre")
    b.input(IN_SURROUND, "NodeSocketBool", default=False,
            description="Embed the domain in a large static field")
    b.input(IN_DOMAIN_SIZE, "NodeSocketFloat", default=2.0, min=0.01,
            subtype="DISTANCE")
    b.input(IN_MATERIAL_HEIGHT, "NodeSocketFloat",
            default=DEFAULT_MATERIAL_HEIGHT, min=0.0, subtype="DISTANCE")
    b.input(IN_MATERIAL, "NodeSocketMaterial",
            description="Material for the surround and crumbs (the domain's)")
    b.input(IN_UNDULATION, "NodeSocketFloat", default=0.006, min=0.0,
            max=0.1, subtype="DISTANCE",
            description="Broad unevenness of the resting surface (mud)")
    b.input(IN_WATER, "NodeSocketBool", default=False,
            description="Standing water that fills hollows and tracks (mud)")
    b.input(IN_WATER_LEVEL, "NodeSocketFloat", default=-0.004, min=-1.0,
            max=1.0, subtype="DISTANCE",
            description="Water table relative to the resting surface")
    b.input(IN_WATER_MATERIAL, "NodeSocketMaterial")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")


def group_name(element: str) -> str:
    """One surface group per element: only the nodes that element needs."""
    return f"{NG_SURFACE}_{element.title()}"


def _grid(g, size, verts, z):
    grid = g.node("GeometryNodeMeshGrid",
                  {"Size X": size, "Size Y": size,
                   "Vertices X": verts, "Vertices Y": verts})
    sp = g.node("GeometryNodeSetPosition",
                {"Geometry": g.out(grid, "Mesh"), "Offset": g.vec(0.0, 0.0, z)})
    sm = g.node("GeometryNodeSetShadeSmooth", {0: g.out(sp, 0)})
    return g.out(sm, 0)


def _cut_hole(g, geo, half):
    """Delete the faces whose centre lies inside the square |x|,|y| < half."""
    p = g.position()
    inside = p.x.abs().max(p.y.abs()).lt(half)
    return g.out(g.node("GeometryNodeDeleteGeometry",
                        {"Geometry": geo, "Selection": inside},
                        domain="FACE", mode="ALL"), 0)


def _surround(g, size, height, viewport):
    """Fine ring (3 x domain) plus coarse far field, as one geometry.

    The ring has a vertex row exactly on the domain border and meets the
    domain there at the same height. One more row runs under the domain and
    dips down, so a hairline mismatch between the two tessellations shows
    sand, never a gap.
    """
    k = (size / _RING_CELL).round().clamp(16.0, 256.0)
    k = g.switch(viewport, k, (k * 0.25).round().max(8.0))
    ring_cell = size / k
    ring = _grid(g, size * 3.0, k * 3.0 + 1.0, height)
    ring = _cut_hole(g, ring, size * 0.5 - ring_cell)
    p = g.position()
    edge = p.x.abs().max(p.y.abs())              # size/2 on the domain border
    ring = g.store(ring, ATTR_GEO,
                   sfn.smoothstep((1.45 - edge / size) / 0.35))
    ring = g.store(ring, _ATTR_SINK,
                   edge.lt(size * 0.5 - ring_cell * 0.5) * _UNDER_SINK)

    far_size = size * 3.0 * _FAR_CELLS
    far = _grid(g, far_size, _FAR_CELLS + 1, height)
    far = _cut_hole(g, far, size * 1.5)
    far = g.store(far, ATTR_GEO, 0.0)

    join = g.b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, far)
    g.feed(join, 0, ring)
    return g.out(join, 0)


def _lumps(g, surface, density, material, *, seed, r_min, r_max, power,
           sink, flat, rough, pebble, stretch=1.0, pebble_id=None):
    """Scatter small irregular meshes on ``surface`` (crumbs or pebbles).

    ``density`` is a field in points per square metre. Sizes follow a power
    law (many small, few large), each lump is squashed, sunk into the ground
    and broken up along its normals. ``pebble`` stores a per-lump stone id
    for the shader (crumbs stay sand: 0).
    """
    dist_node = g.node("GeometryNodeDistributePointsOnFaces",
                       {"Mesh": surface, "Density": density, "Seed": seed},
                       distribute_method="RANDOM")
    pts = g.out(dist_node, "Points")
    normal = g.out(dist_node, "Normal")
    ident = g.out(g.node("GeometryNodeInputID"), 0)
    # many small, few large: cube of a uniform random value
    t = g.random(seed + 21, 0.0, 1.0, ident)
    radius = r_min + (r_max - r_min) * t.pow(power)
    pts = g.out(g.node("GeometryNodeSetPosition",
                       {"Geometry": pts, "Offset": normal * (radius * -sink)}), 0)
    ico = g.node("GeometryNodeMeshIcoSphere", {"Radius": 1.0, "Subdivisions": 2})
    rot = g.out(g.node("FunctionNodeRandomValue",
                       {"Min": (0.0, 0.0, 0.0), "Max": (6.2832, 6.2832, 6.2832),
                        "ID": ident, "Seed": seed + 22},
                       data_type="FLOAT_VECTOR"),
                "Value")
    rot = g.out(g.node("FunctionNodeEulerToRotation", {0: rot}), 0)
    squash = g.vec(radius * stretch * g.random(seed + 23, 0.75, 1.25, ident),
                   radius * g.random(seed + 24, 0.75, 1.25, ident),
                   radius * g.random(seed + 25, flat * 0.6, flat, ident))
    iop = g.node("GeometryNodeInstanceOnPoints",
                 {"Points": pts, "Instance": g.out(ico, "Mesh"),
                  "Rotation": rot, "Scale": squash})
    inst = g.store(g.out(iop, 0), _ATTR_CRUMB, radius, domain="INSTANCE")
    if pebble:
        pid = (g.random(seed + 26, 0.05, 0.94, ident) if pebble_id is None
               else pebble_id)
        inst = g.store(inst, ATTR_PEBBLE, pid, domain="INSTANCE")
    mesh = g.out(g.node("GeometryNodeRealizeInstances", {"Geometry": inst}), 0)
    # break the sphere: push vertices in and out along their normal
    lump = g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": g.position(), "Scale": 260.0, "Detail": 2.0,
                         "Roughness": 0.6}), 0) - 0.5
    nrm = g.out(g.b.add("GeometryNodeInputNormal"), "Normal")
    mesh = g.out(g.node("GeometryNodeSetPosition",
                        {"Geometry": mesh,
                         "Offset": nrm * (lump * g.attr(_ATTR_CRUMB) * rough)}), 0)
    mesh = g.out(g.node("GeometryNodeSetShadeSmooth", {0: mesh}), 0)
    mesh = g.store(mesh, ATTR_GEO, 1.0)
    return g.out(g.node("GeometryNodeSetMaterial",
                        {"Geometry": mesh, "Material": material}), 0)


def build(name: str = NG_SURFACE, element: str = ELEM_SAND):
    mud = element == ELEM_MUD
    tree = new_geometry_group(name)
    b, g = make(tree)
    _interface(b)
    gin, gout = b.group_io()

    def I(key):  # noqa: E743
        return g.out(gin, key)

    viewport = g.out(b.add("GeometryNodeIsViewport"), 0)
    size = I(IN_DOMAIN_SIZE)

    # ---- domain: realise the top sheet, soften the field edges, upsample ----
    geo = g.out(g.node("GeometryNodeRealizeInstances",
                       {"Geometry": I(IN_GEOMETRY)}), 0)
    for name_ in (ATTR_DIST, ATTR_DAMP):
        blur = g.node("GeometryNodeBlurAttribute",
                      {"Value": g.attr(name_), "Iterations": 3},
                      data_type="FLOAT")
        geo = g.store(geo, name_, g.out(blur, 0))
    level = g.switch(viewport, I(IN_RENDER_LEVEL), I(IN_VIEW_LEVEL), kind="INT")
    sub = g.node("GeometryNodeSubdivisionSurface",
                 {"Mesh": geo, "Level": level})
    try:
        sub.inputs["Boundary Smooth"].default_value = "Keep Corners"
    except (KeyError, TypeError):
        pass
    geo = g.store(g.out(sub, 0), ATTR_GEO, 1.0)

    # ---- surround ---------------------------------------------------------------
    around = _surround(g, size, I(IN_MATERIAL_HEIGHT), viewport)
    around = g.out(g.node("GeometryNodeSetMaterial",
                          {"Geometry": around,
                           "Material": I(IN_MATERIAL)}), 0)
    sw = g.node("GeometryNodeSwitch",
                {"Switch": I(IN_SURROUND), "True": around},
                input_type="GEOMETRY")
    join = b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, g.out(sw, 0))
    g.feed(join, 0, geo)
    geo = g.out(join, 0)

    # ---- meso relief --------------------------------------------------------------
    p = g.position()
    p2 = g.vec(p.x, p.y, 0.0)
    dist = g.attr(ATTR_DIST).clamp(0.0, 1.0)
    comp = g.attr(ATTR_COMP).clamp(0.0, 1.0)
    geo_w = g.attr(ATTR_GEO)

    w_clod = sfn.smoothstep(dist) * (1.0 - comp * 0.85)
    r = p2.length() / size
    dune = sfn.dune_height(g, p2) * sfn.smoothstep((r - 2.2) / 8.0)
    dz = dune * _DUNE_HEIGHT[element] - g.attr(_ATTR_SINK)
    if mud:
        # A mud flat is never level: hollows hold water. Where an object
        # went through, the squeezed mud bulges into rounded lobes; packed
        # tracks stay smooth.
        und = sfn.mud_undulation(g, p2) * I(IN_UNDULATION)
        pock = sfn.mud_pocks(g, p2) * (0.0006 * (1.0 - comp)) * geo_w
        # churned ground everywhere, calmer where it was packed flat and a
        # little calmer in the hollows, where water has slumped the clods
        calm = (1.0 - comp * 0.9) * geo_w
        clod = sfn.mud_clods(g, p2) * calm * (I(IN_CLOD_HEIGHT) * 1.7)
        lobe = (sfn.mud_lobes(g, p2) - 0.35) * w_clod * (I(IN_CLOD_HEIGHT) * 3.0)
        wrinkle = sfn.mud_wrinkles(g, p2) * w_clod * (I(IN_CLOD_HEIGHT) * 0.5)
        dz = dz + und + pock + clod + lobe + wrinkle
    else:
        rip = sfn.ripple_height(g, p2, I(IN_RIPPLE_LENGTH), I(IN_WIND))
        w_rip = sfn.smoothstep(1.0 - dist * 1.6) * (1.0 - comp) * geo_w
        clod = sfn.clod_height(g, p2)
        dz = (dz + rip * w_rip * (I(IN_RIPPLE_HEIGHT) * 0.5)
              + clod * w_clod * (I(IN_CLOD_HEIGHT) * 0.5))
    geo = g.store(geo, _ATTR_LOOSE, w_clod)
    if mud:
        # soaked band just above the water table, for the shader
        water_z = I(IN_MATERIAL_HEIGHT) + I(IN_WATER_LEVEL)
        above = (p.z + dz - water_z) / _SHORE_BAND
        geo = g.store(geo, ATTR_SHORE,
                      (1.0 - sfn.smoothstep(above)) * I(IN_WATER))
    surface = g.out(g.node("GeometryNodeSetPosition",
                           {"Geometry": geo, "Offset": g.vec(0.0, 0.0, dz)}), 0)

    # ---- crumbs ---------------------------------------------------------------------
    if mud:
        # splatter: flat, half-sunk clots thrown off by the object
        # clots everywhere (more where churned), none on packed tracks
        clots = (I(IN_CRUMBS) * 0.1 * (0.4 + g.attr(_ATTR_LOOSE))
                 * g.attr(ATTR_GEO).gt(0.5)
                 * (1.0 - g.attr(ATTR_COMP).clamp(0.0, 1.0)))
        crumbs = _lumps(g, surface, clots,
                        I(IN_MATERIAL), seed=3, r_min=0.0015, r_max=0.012,
                        power=3.5, sink=0.45, flat=0.55, rough=0.8, pebble=False)
    else:
        crumbs = _lumps(g, surface, I(IN_CRUMBS) * g.attr(_ATTR_LOOSE),
                        I(IN_MATERIAL), seed=3, r_min=_CRUMB_MIN,
                        r_max=_CRUMB_MAX, power=4.0, sink=0.25, flat=0.75,
                        rough=1.9, pebble=False)
    # Pebbles and shell bits: everywhere the ground is real geometry, fewer
    # where it was churned (they get buried) and none on packed tracks.
    keep = (g.attr(ATTR_GEO).gt(0.5) * (1.0 - g.attr(_ATTR_LOOSE) * 0.7)
            * (1.0 - g.attr(ATTR_COMP).clamp(0.0, 1.0)))
    pebbles = _lumps(g, surface, I(IN_PEBBLES) * keep, I(IN_MATERIAL),
                     seed=40, r_min=0.0008, r_max=0.006, power=5.0,
                     sink=0.45, flat=0.6, rough=1.2, pebble=True)
    out = b.add("GeometryNodeJoinGeometry")
    if mud:
        # a few stalks of straw and root: thin, long, lying flat
        straw = _lumps(g, surface, I(IN_PEBBLES) * 0.12 * g.attr(ATTR_GEO).gt(0.5),
                       I(IN_MATERIAL), seed=70, r_min=0.0005, r_max=0.0011,
                       power=1.0, sink=0.1, flat=1.0, rough=0.25, pebble=True,
                       stretch=32.0, pebble_id=0.98)
        g.feed(out, 0, straw)
        # Standing water: one level sheet at the water table. The mud is a
        # height field, so the sheet only shows where the mud lies below it:
        # in natural hollows and in every track an object leaves.
        extent = g.switch(I(IN_SURROUND), size, size * 3.0 * _FAR_CELLS)
        sheet = _grid(g, extent, 2, I(IN_MATERIAL_HEIGHT) + I(IN_WATER_LEVEL))
        sheet = g.out(g.node("GeometryNodeSetMaterial",
                             {"Geometry": sheet,
                              "Material": I(IN_WATER_MATERIAL)}), 0)
        wsw = g.node("GeometryNodeSwitch",
                     {"Switch": I(IN_WATER), "True": sheet},
                     input_type="GEOMETRY")
        g.feed(out, 0, g.out(wsw, 0))
    g.feed(out, 0, pebbles)
    g.feed(out, 0, crumbs)
    g.feed(out, 0, surface)
    g.feed(gout, OUT_GEOMETRY, g.out(out, 0))
    b.layout()
    return tree
