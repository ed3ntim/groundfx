# SPDX-License-Identifier: GPL-3.0-or-later
"""E3-S2 acceptance: material relaxes to its angle of repose.

Builds a tall narrow spike of material, runs many relaxation iterations, and
measures the flank angle of the resulting cone. It must land within a few
degrees of the configured repose angle — the criterion that separates a real
granular solver from a blur.
"""
from __future__ import annotations

import math

import bpy

import harness

from groundfx.core.ng_builder import NodeTreeBuilder, new_geometry_group
from groundfx.core.nodegroups import ng_relax
from groundfx.core.constants import ATTR_HEIGHT, ATTR_BASE, ATTR_SURFACE


def _build_spike_group(name, repose_rad, cohesion, flow, iterations,
                       cell_size, grid_n, spike_r, spike_h, stickiness=None):
    tree = new_geometry_group(name)
    b = NodeTreeBuilder(tree)
    b.input("Geometry", "NodeSocketGeometry")
    b.output("Geometry", "NodeSocketGeometry")
    gin, gout = b.group_io()

    # radius from centre
    pos = b.add("GeometryNodeInputPosition")
    sep = b.add("ShaderNodeSeparateXYZ")
    b.link(pos, "Position", sep, "Vector")
    x2 = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(sep, "X", x2, 0)
    b.link(sep, "X", x2, 1)
    y2 = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(sep, "Y", y2, 0)
    b.link(sep, "Y", y2, 1)
    r2 = b.add("ShaderNodeMath", operation="ADD")
    b.link(x2, "Value", r2, 0)
    b.link(y2, "Value", r2, 1)
    r = b.add("ShaderNodeMath", operation="SQRT")
    b.link(r2, "Value", r, 0)

    inside = b.add("ShaderNodeMath", operation="LESS_THAN",
                   inputs={1: spike_r})
    b.link(r, "Value", inside, 0)
    h0 = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: spike_h})
    b.link(inside, "Value", h0, 0)

    base_val = b.add("ShaderNodeValue")
    base_val.outputs[0].default_value = 0.0

    st_base = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                    domain="POINT", inputs={"Name": ATTR_BASE})
    b.link(gin, "Geometry", st_base, "Geometry")
    b.link(base_val, "Value", st_base, "Value")
    st_h = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                 domain="POINT", inputs={"Name": ATTR_HEIGHT})
    b.link(st_base, "Geometry", st_h, "Geometry")
    b.link(h0, "Value", st_h, "Value")
    st_surf = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                    domain="POINT", inputs={"Name": ATTR_SURFACE})
    b.link(st_h, "Geometry", st_surf, "Geometry")
    b.link(h0, "Value", st_surf, "Value")

    # constant parameter nodes
    def val(v):
        n = b.add("ShaderNodeValue")
        n.outputs[0].default_value = float(v)
        return n

    iters_node = b.add("FunctionNodeInputInt")
    iters_node.integer = int(iterations)
    gridn_node = b.add("FunctionNodeInputInt")
    gridn_node.integer = int(grid_n)

    refs = {
        "repose": (val(repose_rad), "Value"),
        "cohesion": (val(cohesion), "Value"),
        "flow": (val(flow), "Value"),
        "iterations": (iters_node, "Integer"),
        "cell_size": (val(cell_size), "Value"),
        "grid_n": (gridn_node, "Integer"),
    }
    if stickiness is not None:
        refs["stickiness"] = (val(stickiness), "Value")
    relax_node, relax_key = ng_relax.add_relaxation(b, st_surf, "Geometry", refs)

    # set position z = base + h
    fb = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
               inputs={"Name": ATTR_BASE})
    fh = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
               inputs={"Name": ATTR_HEIGHT})
    surf = b.add("ShaderNodeMath", operation="ADD")
    b.link(fb, "Attribute", surf, 0)
    b.link(fh, "Attribute", surf, 1)
    npos = b.add("ShaderNodeCombineXYZ")
    b.link(sep, "X", npos, "X")
    b.link(sep, "Y", npos, "Y")
    b.link(surf, "Value", npos, "Z")
    setp = b.add("GeometryNodeSetPosition")
    b.link(relax_node, relax_key, setp, "Geometry")
    b.link(npos, "Vector", setp, "Position")
    b.link(setp, "Geometry", gout, "Geometry")
    b.layout()
    return tree


def _measure_repose(deg, stickiness=None):
    """Relax a spike at the given repose angle; return measured flank angle."""
    from groundfx.ops.op_add import _make_grid_mesh

    grid_res = 48
    size = 1.0
    cell = size / grid_res
    grid_n = grid_res + 1

    tag = f"{int(deg)}_{int((stickiness or 0) * 100)}"
    mesh = _make_grid_mesh(f"repose_{tag}", size, grid_res)
    obj = bpy.data.objects.new(f"repose_{tag}", mesh)
    bpy.context.scene.collection.objects.link(obj)

    tree = _build_spike_group(
        f"gfx_repose_{tag}", math.radians(deg), cohesion=0.0, flow=0.9,
        iterations=600, cell_size=cell, grid_n=grid_n,
        spike_r=0.08, spike_h=0.35, stickiness=stickiness)
    md = obj.modifiers.new("GN", "NODES")
    md.node_group = tree
    bpy.context.view_layer.update()

    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    verts = ev.data.vertices
    # Collect (radius, height) pairs.
    pts = [(math.hypot(v.co.x, v.co.y), v.co.z) for v in verts]
    hmax = max(h for _, h in pts)
    # Flank samples: heights between 15% and 85% of the peak.
    flank = [(rr, hh) for rr, hh in pts
             if 0.15 * hmax < hh < 0.85 * hmax]

    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.node_groups.remove(tree)

    if len(flank) < 8:
        return None, hmax
    # Linear fit h = m*r + c ; slope magnitude = tan(angle).
    n = len(flank)
    sr = sum(rr for rr, _ in flank)
    sh = sum(hh for _, hh in flank)
    srr = sum(rr * rr for rr, _ in flank)
    srh = sum(rr * hh for rr, hh in flank)
    denom = n * srr - sr * sr
    if abs(denom) < 1e-12:
        return None, hmax
    slope = (n * srh - sr * sh) / denom
    return math.degrees(math.atan(abs(slope))), hmax


def test_repose_angle_sand():
    measured, hmax = _measure_repose(34.0)
    harness.check("sand cone formed", measured is not None and hmax < 0.30,
                  f"hmax={hmax:.3f} (spike 0.35 should have collapsed)")
    if measured is not None:
        harness.check("sand repose ~34deg", abs(measured - 34.0) <= 3.0,
                      f"measured {measured:.1f}deg, want 34+-3")


def test_repose_angle_steep():
    measured, hmax = _measure_repose(55.0)
    if measured is not None:
        harness.check("steep repose ~55deg", abs(measured - 55.0) <= 3.0,
                      f"measured {measured:.1f}deg, want 55+-3")
    else:
        harness.check("steep cone formed", False, "no flank samples")


def test_stickiness_holds_a_steeper_slope():
    """P1: with a static-friction margin, a pile settles steeper than repose.

    Same 34-deg spike, once free-flowing and once sticky. Static friction lets
    the material stop before it reaches the repose angle, so the sticky cone
    stands clearly steeper -- the mechanism that keeps material caught in a
    groove or a heap standing instead of draining flat.
    """
    free, _ = _measure_repose(34.0, stickiness=0.0)
    sticky, _ = _measure_repose(34.0, stickiness=0.30)
    harness.check("both cones measured", free is not None and sticky is not None,
                  f"free={free} sticky={sticky}")
    if free is not None and sticky is not None:
        harness.check("stickiness holds a steeper slope", sticky > free + 3.0,
                      f"free {free:.1f}deg vs sticky {sticky:.1f}deg")


def test_zero_stickiness_matches_plain_repose():
    """Stickiness 0 must not disturb the repose calibration (still ~34 deg)."""
    measured, _ = _measure_repose(34.0, stickiness=0.0)
    if measured is not None:
        harness.check("stick=0 still ~34deg", abs(measured - 34.0) <= 3.0,
                      f"measured {measured:.1f}deg")
