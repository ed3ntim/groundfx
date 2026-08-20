# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe: raycast a grid against a *collection* of colliders (E4-T17).

Verifies: NodeSocketCollection interface socket, GeometryNodeCollectionInfo
(transform_space, Separate Children, output Instances), GeometryNodeRealizeInstances,
and that a ray cast upward hits the union of two cubes placed at different XY.
"""
import bpy

def out(msg): print("PROBE:" + msg, flush=True)

# node existence
for idn in ("GeometryNodeCollectionInfo", "GeometryNodeRealizeInstances",
            "GeometryNodeRaycast", "GeometryNodeObjectInfo"):
    try:
        ng = bpy.data.node_groups.new("t", "GeometryNodeTree")
        n = ng.nodes.new(idn)
        out(f"node {idn}: OK inputs={[s.name for s in n.inputs]} outputs={[s.name for s in n.outputs]}")
        if idn == "GeometryNodeCollectionInfo":
            out(f"  transform_space={getattr(n,'transform_space',None)!r} has_attr={hasattr(n,'transform_space')}")
        bpy.data.node_groups.remove(ng)
    except Exception as e:
        out(f"node {idn}: FAIL {e}")

# collection socket type
ng = bpy.data.node_groups.new("sock", "GeometryNodeTree")
try:
    s = ng.interface.new_socket("Colliders", in_out="INPUT", socket_type="NodeSocketCollection")
    out(f"socket NodeSocketCollection: OK identifier={s.identifier}")
except Exception as e:
    out(f"socket NodeSocketCollection: FAIL {e}")
bpy.data.node_groups.remove(ng)

# --- end-to-end: grid raycasts up against a collection of two cubes ---------
# Build collection with two cubes at different XY, undersides at z=0.3
coll = bpy.data.collections.new("ProbeColliders")
bpy.context.scene.collection.children.link(coll)
for cx in (-0.5, 0.5):
    m = bpy.data.meshes.new("c")
    import numpy as np
    # unit cube 0.4 wide centred at (cx,0,0.5): underside z=0.3
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(cx, 0.0, 0.5))
    cube = bpy.context.active_object
    # move to our collection only
    for c in list(cube.users_collection):
        c.objects.unlink(cube)
    coll.objects.link(cube)

# grid object
bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20, size=2.0)
grid = bpy.context.active_object

ng = bpy.data.node_groups.new("ProbeRC", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
csock = ng.interface.new_socket("Colliders", in_out="INPUT", socket_type="NodeSocketCollection")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
n = ng.nodes
gin = n.new("NodeGroupInput"); gout = n.new("NodeGroupOutput")
ci = n.new("GeometryNodeCollectionInfo"); ci.transform_space = "RELATIVE"
real = n.new("GeometryNodeRealizeInstances")
pos = n.new("GeometryNodeInputPosition"); sep = n.new("ShaderNodeSeparateXYZ")
comb = n.new("ShaderNodeCombineXYZ")
ray = n.new("GeometryNodeRaycast"); ray.data_type = "FLOAT"
store = n.new("GeometryNodeStoreNamedAttribute"); store.data_type="FLOAT"; store.domain="POINT"
store.inputs["Name"].default_value = "hit"
L = ng.links.new
L(gin.outputs["Colliders"], ci.inputs["Collection"])
L(ci.outputs["Instances"], real.inputs["Geometry"])
L(real.outputs["Geometry"], ray.inputs["Target Geometry"])
# source position: (x, y, -5), ray dir +Z
L(pos.outputs["Position"], sep.inputs["Vector"])
L(sep.outputs["X"], comb.inputs["X"]); L(sep.outputs["Y"], comb.inputs["Y"])
comb.inputs["Z"].default_value = -5.0
ray.inputs["Ray Length"].default_value = 20.0
ray.inputs["Ray Direction"].default_value = (0.0,0.0,1.0)
L(comb.outputs["Vector"], ray.inputs["Source Position"])
L(gin.outputs["Geometry"], store.inputs["Geometry"])
# store Is Hit as float via a switch->value? Simpler: store hit position Z
seph = n.new("ShaderNodeSeparateXYZ"); L(ray.outputs["Hit Position"], seph.inputs["Vector"])
L(seph.outputs["Z"], store.inputs["Value"])
L(store.outputs["Geometry"], gout.inputs["Geometry"])

md = grid.modifiers.new("t", "NODES"); md.node_group = ng
# set collection input
ident = None
for it in ng.interface.items_tree:
    if it.item_type=='SOCKET' and it.in_out=='INPUT' and it.name=="Colliders":
        ident = it.identifier
md.properties.inputs[ident].value = coll
grid.update_tag()
deps = bpy.context.evaluated_depsgraph_get()
ev = grid.evaluated_get(deps)
attr = ev.data.attributes.get("hit")
vals = [d.value for d in attr.data] if attr else []
hits = [v for v in vals if v > 0.01]  # hit underside z~0.3
out(f"raycast against collection: {len(hits)} points hit (of {len(vals)}), "
    f"min={min(vals):.3f} max={max(vals):.3f}")
out("DONE")
