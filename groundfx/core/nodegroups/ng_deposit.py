# SPDX-License-Identifier: GPL-3.0-or-later
"""Displacement / piling: carved material heaps up at the rim instead of vanishing.

The carve step converts removed height into a ``gfx_pile`` buffer (scaled by
``displacement_ratio``; the remainder is compaction). This module then moves
that pile out of the collider footprint to the free cells around it, forming a
berm — which the subsequent relaxation smooths to the repose angle.

The transport is a mass-conserving diffusion of the pile buffer with a
reflecting boundary at the collider: each cell sends a quarter of its pile to
every valid neighbour, so a cell's pile after one step is the average inflow
from its neighbours. Free cells (not under the collider) convert their incoming
pile into height; collider cells keep it as pile to relay further out. Over a
few iterations the pile walks to the rim and deposits.

Directional bias (bow wave ahead of a moving collider, side berms) needs
collider velocity and is added in E4; this isotropic version already produces a
believable rim. Verified against Blender 5.2.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_zones import make_repeat_zone
from ..constants import ATTR_HEIGHT, ATTR_PILE, ATTR_CARVE

_FREE_EPS = 1e-5  # a cell with carve below this is "free" (not under collider)


def _sample_neighbour(b, geo_node, attr_name, nidx_node, nidx_key, valid_node):
    """Sample a POINT float attribute at a neighbour index, masked by validity."""
    sample = b.add("GeometryNodeSampleIndex", data_type="FLOAT", domain="POINT",
                   clamp=True)
    attr = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                 inputs={"Name": attr_name})
    b.link(geo_node, "Geometry", sample, "Geometry")
    b.link(attr, "Attribute", sample, "Value")
    b.link(nidx_node, nidx_key, sample, "Index")
    masked = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(sample, "Value", masked, 0)
    b.link(valid_node, "Value", masked, 1)
    return masked


def add_deposit(b: NodeTreeBuilder, geo_node, geo_key, refs):
    """Append the pile-transport Repeat zone; return (out_node, out_key).

    ``refs`` maps: 'iterations' (deposit steps), 'grid_n'.
    """
    zone = make_repeat_zone(b, repeat_items=[("GEOMETRY", "Geometry")])
    b.link(geo_node, geo_key, zone.input, "Geometry")
    b.link(*refs["iterations"], zone.input, "Iterations")

    it_geo = zone.input
    grid_n_node, grid_n_key = refs["grid_n"]

    # Grid coordinates from index (row-major: index = row*N + col).
    index = b.add("GeometryNodeInputIndex")
    col = b.add("ShaderNodeMath", operation="MODULO", label="col")
    b.link(index, "Index", col, 0)
    b.link(grid_n_node, grid_n_key, col, 1)
    row_div = b.add("ShaderNodeMath", operation="DIVIDE")
    b.link(index, "Index", row_div, 0)
    b.link(grid_n_node, grid_n_key, row_div, 1)
    row = b.add("ShaderNodeMath", operation="FLOOR", label="row")
    b.link(row_div, "Value", row, 0)
    n_minus_1 = b.add("ShaderNodeMath", operation="SUBTRACT", inputs={1: 1.0})
    b.link(grid_n_node, grid_n_key, n_minus_1, 0)

    def lt(a, ak, c, ck):
        v = b.add("ShaderNodeMath", operation="LESS_THAN")
        b.link(a, ak, v, 0)
        b.link(c, ck, v, 1)
        return v

    def gt0(a, ak):
        v = b.add("ShaderNodeMath", operation="GREATER_THAN", inputs={1: 0.0})
        b.link(a, ak, v, 0)
        return v

    valid_px = lt(col, "Value", n_minus_1, "Value")
    valid_mx = gt0(col, "Value")
    valid_py = lt(row, "Value", n_minus_1, "Value")
    valid_my = gt0(row, "Value")

    # Neighbour indices: +/-1 and +/-N.
    def add_idx(offset_value=None, offset_node=None, sign=1.0):
        if offset_value is not None:
            n = b.add("ShaderNodeMath", operation="ADD",
                      inputs={1: float(offset_value)})
            b.link(index, "Index", n, 0)
            return n
        n = b.add("ShaderNodeMath", operation="MULTIPLY_ADD")
        b.link(offset_node[0], offset_node[1], n, 0)
        b.set_default(n, 1, sign)
        b.link(index, "Index", n, 2)
        return n

    idx_px = add_idx(offset_value=1)
    idx_mx = add_idx(offset_value=-1)
    idx_py = add_idx(offset_node=(grid_n_node, grid_n_key), sign=1.0)
    idx_my = add_idx(offset_node=(grid_n_node, grid_n_key), sign=-1.0)

    # Sum of neighbour piles (masked at borders).
    s_px = _sample_neighbour(b, it_geo, ATTR_PILE, idx_px, "Value", valid_px)
    s_mx = _sample_neighbour(b, it_geo, ATTR_PILE, idx_mx, "Value", valid_mx)
    s_py = _sample_neighbour(b, it_geo, ATTR_PILE, idx_py, "Value", valid_py)
    s_my = _sample_neighbour(b, it_geo, ATTR_PILE, idx_my, "Value", valid_my)
    sum1 = b.add("ShaderNodeMath", operation="ADD")
    b.link(s_px, "Value", sum1, 0)
    b.link(s_mx, "Value", sum1, 1)
    sum2 = b.add("ShaderNodeMath", operation="ADD")
    b.link(s_py, "Value", sum2, 0)
    b.link(s_my, "Value", sum2, 1)
    nsum = b.add("ShaderNodeMath", operation="ADD", label="neighbour pile sum")
    b.link(sum1, "Value", nsum, 0)
    b.link(sum2, "Value", nsum, 1)
    # s = 0.25 * neighbour sum (mass-conserving average inflow)
    s = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.25},
              label="inflow s")
    b.link(nsum, "Value", s, 0)

    # free = carve <= eps  ->  1 for cells not under the collider
    carve = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                  inputs={"Name": ATTR_CARVE})
    free = b.add("ShaderNodeMath", operation="LESS_THAN", inputs={1: _FREE_EPS},
                 label="free = carve<eps")
    b.link(carve, "Attribute", free, 0)

    # Free cells convert inflow to height; collider cells keep it as pile.
    read_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_HEIGHT})
    free_s = b.add("ShaderNodeMath", operation="MULTIPLY", label="free*s")
    b.link(free, "Value", free_s, 0)
    b.link(s, "Value", free_s, 1)
    new_h = b.add("ShaderNodeMath", operation="ADD", label="h + free*s")
    b.link(read_h, "Attribute", new_h, 0)
    b.link(free_s, "Value", new_h, 1)

    one_minus_free = b.add("ShaderNodeMath", operation="SUBTRACT",
                           label="1-free")
    b.set_default(one_minus_free, 0, 1.0)
    b.link(free, "Value", one_minus_free, 1)
    new_pile = b.add("ShaderNodeMath", operation="MULTIPLY", label="new pile")
    b.link(one_minus_free, "Value", new_pile, 0)
    b.link(s, "Value", new_pile, 1)

    store_h = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                    domain="POINT", inputs={"Name": ATTR_HEIGHT})
    b.link(it_geo, "Geometry", store_h, "Geometry")
    b.link(new_h, "Value", store_h, "Value")
    store_pile = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                       domain="POINT", inputs={"Name": ATTR_PILE})
    b.link(store_h, "Geometry", store_pile, "Geometry")
    b.link(new_pile, "Value", store_pile, "Value")

    b.link(store_pile, "Geometry", zone.output, "Geometry")
    return zone.output, "Geometry"
