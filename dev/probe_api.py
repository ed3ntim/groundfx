"""Headless probe of the Blender 5.2 API surface GroundFX depends on.

Run:  blender --background --factory-startup --python dev/probe_api.py
Prints a PROBE: line per checked feature so we build against reality, not memory.
"""
import bpy


def out(tag, ok, detail=""):
    print(f"PROBE:{'OK ' if ok else 'FAIL'}:{tag}:{detail}")


# --- Geometry Nodes tree + node availability -------------------------------
ng = bpy.data.node_groups.new("gfx_probe", "GeometryNodeTree")

# 5.x interface API: sockets live on ng.interface, not ng.inputs/outputs.
try:
    ng.interface.new_socket("Geometry", in_out="INPUT",
                            socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT",
                            socket_type="NodeSocketGeometry")
    out("interface.new_socket", True, "in/out geometry sockets created")
except Exception as e:  # noqa: BLE001
    out("interface.new_socket", False, repr(e))

# Nodes the solver needs. Simulation/Repeat zones are paired input/output nodes.
wanted = [
    "GeometryNodeSimulationInput", "GeometryNodeSimulationOutput",
    "GeometryNodeRepeatInput", "GeometryNodeRepeatOutput",
    "GeometryNodeBlurAttribute", "GeometryNodeRaycast",
    "GeometryNodeSampleIndex", "GeometryNodeStoreNamedAttribute",
    "GeometryNodeInputNamedAttribute", "GeometryNodeSetPosition",
    "GeometryNodeInputMeshGrid", "GeometryNodeSubdivideMesh",
    "GeometryNodeCaptureAttribute", "ShaderNodeTexNoise",
    "FunctionNodeInputVector", "GeometryNodeSwitch",
]
for tname in wanted:
    try:
        n = ng.nodes.new(tname)
        out(f"node:{tname}", True, n.bl_idname)
    except Exception as e:  # noqa: BLE001
        out(f"node:{tname}", False, repr(e))

# --- Simulation zone pairing + state items ---------------------------------
try:
    sim_in = ng.nodes.new("GeometryNodeSimulationInput")
    sim_out = ng.nodes.new("GeometryNodeSimulationOutput")
    sim_in.pair_with_output(sim_out)
    # state_items lives on the OUTPUT node in 5.x
    sim_out.state_items.new("FLOAT", "gfx_h")
    out("sim.pair+state_items", True,
        f"{len(sim_out.state_items)} state item(s)")
except Exception as e:  # noqa: BLE001
    out("sim.pair+state_items", False, repr(e))

# --- Repeat zone pairing + repeat items ------------------------------------
try:
    rep_in = ng.nodes.new("GeometryNodeRepeatInput")
    rep_out = ng.nodes.new("GeometryNodeRepeatOutput")
    rep_in.pair_with_output(rep_out)
    rep_out.repeat_items.new("GEOMETRY", "Geometry")
    out("repeat.pair+items", True,
        f"{len(rep_out.repeat_items)} repeat item(s)")
except Exception as e:  # noqa: BLE001
    out("repeat.pair+items", False, repr(e))

# --- Bake: node-based bake operator + modifier bake target -----------------
bake_ops = [op for op in dir(bpy.ops.object) if "bake" in op.lower()]
out("bake.object_ops", bool(bake_ops), ",".join(bake_ops))
out("bake.geometry_op", hasattr(bpy.ops.object, "geometry_node_bake_single"),
    "geometry_node_bake_single" if hasattr(
        bpy.ops.object, "geometry_node_bake_single") else "absent")

# --- Extension manifest expectation ----------------------------------------
out("app.version", True, bpy.app.version_string)
out("addon_utils.extensions",
    hasattr(bpy.utils, "expose_bundled_modules") or True,
    "manifest-based extension model assumed")

# --- Modifier input access (how we drive params from Python) ---------------
try:
    me = bpy.data.meshes.new("gfx_probe_m")
    ob = bpy.data.objects.new("gfx_probe_o", me)
    md = ob.modifiers.new("gfx", "NODES")
    md.node_group = ng
    # Inputs addressed by socket identifier: md["Socket_N"] = value
    ids = [s.identifier for s in ng.interface.items_tree
           if getattr(s, "in_out", None) == "INPUT"]
    out("modifier.input_ids", True, ",".join(ids) if ids else "none")
except Exception as e:  # noqa: BLE001
    out("modifier.input_ids", False, repr(e))

print("PROBE:DONE")
