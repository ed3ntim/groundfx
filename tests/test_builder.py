# SPDX-License-Identifier: GPL-3.0-or-later
"""E1 tests: the NodeTreeBuilder, zone helpers, and version library.

The headline test builds a real simulation group that increments a named
attribute every frame, evaluates it across several frames, and reads the value
back — proving the builder wires sockets, the simulation zone persists state,
and the whole thing actually computes in Blender (not just constructs).
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.ng_builder import NodeTreeBuilder, new_geometry_group
from groundfx.core import ng_zones, ng_library


# --- basic construction -----------------------------------------------------
def test_builder_counts():
    tree = new_geometry_group("gfx_test_counts")
    b = NodeTreeBuilder(tree)
    b.output("Geometry", "NodeSocketGeometry")
    gin, gout = b.group_io()
    # A little chain of math nodes to reach ~20 nodes.
    prev = b.add("FunctionNodeInputInt", inputs={})
    node_count = 3  # gin, gout, prev
    for i in range(8):
        m = b.add("ShaderNodeMath", operation="ADD", inputs={1: 1.0})
        b.link(prev, 0, m, 0)
        prev = m
        node_count += 1
    b.layout()
    harness.eq("node count", len(tree.nodes), node_count)
    # 8 math nodes chained => 8 links.
    harness.eq("link count", len(tree.links), 8)
    bpy.data.node_groups.remove(tree)


def test_interface_socket_map():
    from groundfx.utils import compat
    tree = new_geometry_group("gfx_test_iface")
    b = NodeTreeBuilder(tree)
    b.input("Geometry", "NodeSocketGeometry")
    b.input("Angle", "NodeSocketFloat", default=0.6, min=0.0, max=1.5)
    b.input("Strength", "NodeSocketFloat", default=1.0)
    b.output("Geometry", "NodeSocketGeometry")
    mapping = compat.socket_identifier_map(tree)
    harness.check("has Angle input", "Angle" in mapping,
                  f"map keys: {list(mapping)}")
    harness.check("identifiers are Socket_N",
                  all(v.startswith("Socket_") for v in mapping.values()),
                  f"map: {mapping}")
    # Confirm the default we set survived.
    angle = next(i for i in compat.iter_input_sockets(tree) if i.name == "Angle")
    harness.check("angle default", abs(angle.default_value - 0.6) < 1e-6,
                  f"got {angle.default_value}")
    bpy.data.node_groups.remove(tree)


# --- functional simulation --------------------------------------------------
def _build_accumulator(name):
    """Group that adds 1.0 to a POINT attribute 'gfx_h' every sim step."""
    tree = new_geometry_group(name)
    b = NodeTreeBuilder(tree)
    b.input("Geometry", "NodeSocketGeometry")
    b.output("Geometry", "NodeSocketGeometry")
    gin, gout = b.group_io()

    zone = ng_zones.make_simulation_zone(b, state_items=[])  # geometry only

    # Read current gfx_h (defaults to 0 on first frame), add 1, store back.
    read = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                 inputs={"Name": "gfx_h"})
    add = b.add("ShaderNodeMath", operation="ADD", inputs={1: 1.0})
    store = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                  domain="POINT", inputs={"Name": "gfx_h"})

    b.link(gin, "Geometry", zone.input, "Geometry")
    b.link(zone.input, "Geometry", store, "Geometry")
    b.link(read, "Attribute", add, 0)
    b.link(add, "Value", store, "Value")
    b.link(store, "Geometry", zone.output, "Geometry")
    b.link(zone.output, "Geometry", gout, "Geometry")
    b.layout()
    return tree


def test_simulation_zone_accumulates():
    scene = bpy.context.scene
    # Fresh grid object.
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3, size=2.0)
    obj = bpy.context.active_object
    tree = _build_accumulator("gfx_test_accum")
    md = obj.modifiers.new("gfx", "NODES")
    md.node_group = tree

    scene.frame_start = 1
    scene.frame_end = 10
    deps = bpy.context.evaluated_depsgraph_get()

    # Step frames sequentially so the simulation zone caches each step.
    for f in range(1, 6):
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()

    eval_obj = obj.evaluated_get(deps)
    mesh = eval_obj.data
    attr = mesh.attributes.get("gfx_h")
    ok = attr is not None
    harness.check("gfx_h attribute exists", ok,
                  f"attributes: {[a.name for a in mesh.attributes]}")
    if ok:
        val = attr.data[0].value
        # After stepping frames 1..5, the accumulator ran 5 times => 5.0.
        harness.check("accumulated value", abs(val - 5.0) < 1e-4,
                      f"expected ~5.0 at frame 5, got {val}")

    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.node_groups.remove(tree)


# --- version library --------------------------------------------------------
def test_ensure_node_group_reuses_and_rebuilds():
    calls = {"n": 0}

    def build(name):
        calls["n"] += 1
        return new_geometry_group(name)

    t1 = ng_library.ensure_node_group("gfx_test_ensure", build)
    harness.eq("built once", calls["n"], 1)
    harness.check("stamped current", ng_library.is_current(t1))

    # Second call: current stamp => no rebuild.
    ng_library.ensure_node_group("gfx_test_ensure", build)
    harness.eq("reused (no rebuild)", calls["n"], 1)

    # Stale stamp => rebuild.
    from groundfx.core.constants import PROP_NG_VERSION
    t1[PROP_NG_VERSION] = -1
    ng_library.ensure_node_group("gfx_test_ensure", build)
    harness.eq("rebuilt on stale", calls["n"], 2)

    leftover = bpy.data.node_groups.get("gfx_test_ensure")
    if leftover:
        bpy.data.node_groups.remove(leftover)
