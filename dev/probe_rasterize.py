# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender 5.3: does Rasterize Points give an additive density volume?

    blender -b --factory-startup --python dev/probe_rasterize.py

Builds points -> Rasterize Points -> Store Named Grid on a test object and
prints the node's item API, its sockets and the grids of the result.
"""
import bpy

tree = bpy.data.node_groups.new("probe", "GeometryNodeTree")
tree.interface.new_socket("Geometry", in_out="OUTPUT",
                          socket_type="NodeSocketGeometry")
N = tree.nodes
ras = N.new("GeometryNodeRasterizePoints")
print("item rna:", [p.identifier for p in
                    ras.rasterize_items.bl_rna.functions["new"].parameters])
item = ras.rasterize_items.new(name="Density")
print("item props:", [(p.identifier, p.type) for p in item.bl_rna.properties])
for p in item.bl_rna.properties:
    if p.type == "ENUM":
        print("  enum", p.identifier, [e.identifier for e in p.enum_items],
              "=", getattr(item, p.identifier))
for s in ras.inputs:
    print("  in ", repr(s.name), s.type, s.identifier)
for s in ras.outputs:
    print("  out", repr(s.name), s.type, s.identifier)

pts = N.new("GeometryNodePoints")
pts.inputs["Count"].default_value = 4000
rnd = N.new("FunctionNodeRandomValue")
rnd.data_type = "FLOAT_VECTOR"
rnd.inputs["Min"].default_value = (-0.2, -0.2, 0.0)
rnd.inputs["Max"].default_value = (0.2, 0.2, 0.2)
tree.links.new(rnd.outputs["Value"], pts.inputs["Position"])
store = N.new("GeometryNodeStoreNamedGrid")
store.data_type = "FLOAT"
store.inputs["Name"].default_value = "density"
out = N.new("NodeGroupOutput")
tree.links.new(pts.outputs[0], ras.inputs["Points"])
ras.inputs["Voxel Size"].default_value = 0.02
ras.inputs["Density"].default_value = 1.0
tree.links.new(ras.outputs["Density"], store.inputs["Grid"])
tree.links.new(store.outputs[0], out.inputs[0])

me = bpy.data.meshes.new("m")
ob = bpy.data.objects.new("o", me)
bpy.context.scene.collection.objects.link(ob)
md = ob.modifiers.new("gn", "NODES")
md.node_group = tree
deps = bpy.context.evaluated_depsgraph_get()
gs = ob.evaluated_get(deps).evaluated_geometry()
vol = gs.volume
print("volume:", vol)
if vol is not None:
    vol.grids.load()
    for g in vol.grids:
        print("  grid", g.name, g.data_type, "channels", g.channels)
