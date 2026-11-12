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
    NG_SURFACE, ATTR_COMP, ATTR_DIST, ATTR_DAMP, ATTR_GEO,
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
IN_SURROUND = "Surround"
IN_DOMAIN_SIZE = "Domain Size"
IN_MATERIAL_HEIGHT = "Material Height"
IN_MATERIAL = "Material"
OUT_GEOMETRY = "Geometry"

_RING_CELL = 0.01      # target cell of the fine ring in renders (metres)
_UNDER_SINK = 0.003    # the ring dips this far where it runs under the domain
_FAR_CELLS = 33        # far field = this many cells of 3 x domain size
_DUNE_HEIGHT = 0.9     # metres, broad far dunes
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
    b.input(IN_SURROUND, "NodeSocketBool", default=False,
            description="Embed the domain in a large static field")
    b.input(IN_DOMAIN_SIZE, "NodeSocketFloat", default=2.0, min=0.01,
            subtype="DISTANCE")
    b.input(IN_MATERIAL_HEIGHT, "NodeSocketFloat",
            default=DEFAULT_MATERIAL_HEIGHT, min=0.0, subtype="DISTANCE")
    b.input(IN_MATERIAL, "NodeSocketMaterial",
            description="Material for the surround and crumbs (the domain's)")
    b.output(OUT_GEOMETRY, "NodeSocketGeometry")


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


def _crumbs(g, surface, density, material):
    """Small irregular lumps lying on disturbed ground, as real meshes."""
    dist_node = g.node("GeometryNodeDistributePointsOnFaces",
                       {"Mesh": surface,
                        "Density": density * g.attr(_ATTR_LOOSE), "Seed": 3},
                       distribute_method="RANDOM")
    pts = g.out(dist_node, "Points")
    normal = g.out(dist_node, "Normal")
    ident = g.out(g.node("GeometryNodeInputID"), 0)
    # many small, few large: cube of a uniform random value
    t = g.random(21, 0.0, 1.0, ident)
    radius = _CRUMB_MIN + (_CRUMB_MAX - _CRUMB_MIN) * t * t * t * t
    pts = g.out(g.node("GeometryNodeSetPosition",
                       {"Geometry": pts, "Offset": normal * (radius * -0.25)}), 0)
    ico = g.node("GeometryNodeMeshIcoSphere", {"Radius": 1.0, "Subdivisions": 2})
    rot = g.out(g.node("FunctionNodeRandomValue",
                       {"Min": (0.0, 0.0, 0.0), "Max": (6.2832, 6.2832, 6.2832),
                        "ID": ident, "Seed": 22}, data_type="FLOAT_VECTOR"),
                "Value")
    rot = g.out(g.node("FunctionNodeEulerToRotation", {0: rot}), 0)
    squash = g.vec(radius * g.random(23, 0.8, 1.2, ident),
                   radius * g.random(24, 0.8, 1.2, ident),
                   radius * g.random(25, 0.4, 0.75, ident))
    iop = g.node("GeometryNodeInstanceOnPoints",
                 {"Points": pts, "Instance": g.out(ico, "Mesh"),
                  "Rotation": rot, "Scale": squash})
    inst = g.store(g.out(iop, 0), _ATTR_CRUMB, radius, domain="INSTANCE")
    mesh = g.out(g.node("GeometryNodeRealizeInstances", {"Geometry": inst}), 0)
    # break the sphere: push vertices in and out along their normal
    lump = g.out(g.node("ShaderNodeTexNoise",
                        {"Vector": g.position(), "Scale": 260.0, "Detail": 2.0,
                         "Roughness": 0.6}), 0) - 0.5
    nrm = g.out(g.b.add("GeometryNodeInputNormal"), "Normal")
    mesh = g.out(g.node("GeometryNodeSetPosition",
                        {"Geometry": mesh,
                         "Offset": nrm * (lump * g.attr(_ATTR_CRUMB) * 1.9)}), 0)
    mesh = g.out(g.node("GeometryNodeSetShadeSmooth", {0: mesh}), 0)
    mesh = g.store(mesh, ATTR_GEO, 1.0)
    return g.out(g.node("GeometryNodeSetMaterial",
                        {"Geometry": mesh, "Material": material}), 0)


def build(name: str = NG_SURFACE):
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

    rip = sfn.ripple_height(g, p2, I(IN_RIPPLE_LENGTH), I(IN_WIND))
    w_rip = sfn.smoothstep(1.0 - dist * 1.6) * (1.0 - comp) * geo_w
    clod = sfn.clod_height(g, p2)
    w_clod = sfn.smoothstep(dist) * (1.0 - comp * 0.85)
    r = p2.length() / size
    dune = sfn.dune_height(g, p2) * sfn.smoothstep((r - 2.2) / 8.0)

    dz = (rip * w_rip * (I(IN_RIPPLE_HEIGHT) * 0.5)
          + clod * w_clod * (I(IN_CLOD_HEIGHT) * 0.5)
          + dune * _DUNE_HEIGHT - g.attr(_ATTR_SINK))
    geo = g.store(geo, _ATTR_LOOSE, w_clod)
    surface = g.out(g.node("GeometryNodeSetPosition",
                           {"Geometry": geo, "Offset": g.vec(0.0, 0.0, dz)}), 0)

    # ---- crumbs ---------------------------------------------------------------------
    crumbs = _crumbs(g, surface, I(IN_CRUMBS), I(IN_MATERIAL))
    out = b.add("GeometryNodeJoinGeometry")
    g.feed(out, 0, crumbs)
    g.feed(out, 0, surface)
    g.feed(gout, OUT_GEOMETRY, g.out(out, 0))
    b.layout()
    return tree
