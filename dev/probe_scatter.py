# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe: is the Join+Accumulate scatter exact and order-stable in 5.2?

Grid points carry group = own index, value 0; extra points carry group =
target index, value = amount. After Accumulate (Total, grouped) the first N
points of the joined cloud must hold the sum of what was sent to them.
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from groundfx.core.ng_builder import new_geometry_group  # noqa: E402
from groundfx.core.ng_expr import make  # noqa: E402

tree = new_geometry_group("probe")
b, g = make(tree)
b.output("Geometry", "NodeSocketGeometry")
gout = b.add("NodeGroupOutput")
grid = g.node("GeometryNodeMeshGrid", {"Size X": 1.0, "Size Y": 1.0,
                                       "Vertices X": 4, "Vertices Y": 4})
pts = g.out(g.node("GeometryNodeMeshToPoints", {"Mesh": g.out(grid, 0)}), 0)
pts = g.store(pts, "grp", g.index())
pts = g.store(pts, "amt", 0.0)
# 3 sender points: send 1.0 to idx 5, 2.0 to idx 5, 4.0 to idx 0
snd = g.out(g.node("GeometryNodePoints", {"Count": 3}), 0)
i = g.index()
snd = g.store(snd, "grp", g.switch(i.gt(0.5), 5.0, g.switch(i.gt(1.5), 5.0, 0.0)))
snd = g.store(snd, "amt", g.switch(i.gt(0.5), 1.0, g.switch(i.gt(1.5), 4.0, 2.0)))
join = b.add("GeometryNodeJoinGeometry")
g.feed(join, 0, snd)   # linked FIRST on purpose
g.feed(join, 0, pts)
acc = g.node("GeometryNodeAccumulateField",
             {"Value": g.attr("amt"), "Group ID": g.attr("grp").round()},
             data_type="FLOAT", domain="POINT")
joined = g.out(join, 0)
joined = g.store(joined, "tot", g.out(acc, "Total"))
joined = g.out(g.node("GeometryNodePointsToVertices", {"Points": joined}), 0)
g.feed(gout, 0, joined)

ob = bpy.data.objects.new("probe", bpy.data.meshes.new("probe"))
bpy.context.scene.collection.objects.link(ob)
md = ob.modifiers.new("p", "NODES")
md.node_group = tree
ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
pc = ev.data if hasattr(ev.data, "attributes") else None
print("TYPE", type(ev.data))
m = ev.to_mesh() if not hasattr(ev.data, "points") else None
data = ev.data
grp = [a.value for a in data.attributes["grp"].data]
tot = [a.value for a in data.attributes["tot"].data]
amt = [a.value for a in data.attributes["amt"].data]
print("GRP", grp)
print("AMT", amt)
print("TOT", tot)
# sample nearest exists?
print("NEAREST", "GeometryNodeSampleNearest" in dir(bpy.types))
