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

On top of that isotropic diffusion, a directional bias (E4-S3) advects the pile
toward the collider's motion so material heaps up ahead as a bow wave. The
motion direction is read from the gradient of ``dcarve = carve - carve_prev``
(positive at the leading edge, negative at the trailing one) and its strength is
the ``bow_wave`` input (0 = pure isotropic rim). Verified against Blender 5.2.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_zones import make_repeat_zone
from ..constants import ATTR_HEIGHT, ATTR_PILE, ATTR_CARVE, ATTR_CARVE_PREV

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

    # --- bow wave: advect the pile toward the collider's motion (E4-T10) ----
    # The motion direction is the shift of the footprint's *centroid* between
    # frames: centroid(carve>0) - centroid(carve_prev>0). This is a single
    # translation vector for the whole footprint, so it is genuinely zero for a
    # stationary (merely deepening) collider -- unlike a per-cell carve gradient,
    # which points radially inward around any footprint and would choke the rim.
    # Biasing each free cell's inflow along that vector heaps material up ahead.
    bw_node, bw_key = refs["bow_wave"]
    cell_node, cell_key = refs["cell_size"]
    carve_prev = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                       inputs={"Name": ATTR_CARVE_PREV})
    mask_now = b.add("ShaderNodeMath", operation="GREATER_THAN",
                     inputs={1: _FREE_EPS}, label="carve>0")
    b.link(carve, "Attribute", mask_now, 0)
    mask_prev = b.add("ShaderNodeMath", operation="GREATER_THAN",
                      inputs={1: _FREE_EPS}, label="carve_prev>0")
    b.link(carve_prev, "Attribute", mask_prev, 0)
    pos = b.add("GeometryNodeInputPosition")
    sepp = b.add("ShaderNodeSeparateXYZ")
    b.link(pos, "Position", sepp, "Vector")

    def _centroid(mask_node, axis_key):
        stat = b.add("GeometryNodeAttributeStatistic", data_type="FLOAT",
                     domain="POINT")
        b.link(it_geo, "Geometry", stat, "Geometry")
        b.link(mask_node, "Value", stat, "Selection")
        b.link(sepp, axis_key, stat, "Attribute")
        return stat

    cx_now = _centroid(mask_now, "X")
    cx_prev = _centroid(mask_prev, "X")
    cy_now = _centroid(mask_now, "Y")
    cy_prev = _centroid(mask_prev, "Y")
    vx_raw = b.add("ShaderNodeMath", operation="SUBTRACT", label="vx")
    b.link(cx_now, "Mean", vx_raw, 0)
    b.link(cx_prev, "Mean", vx_raw, 1)
    vy_raw = b.add("ShaderNodeMath", operation="SUBTRACT", label="vy")
    b.link(cy_now, "Mean", vy_raw, 0)
    b.link(cy_prev, "Mean", vy_raw, 1)
    # Scale by 1/cell_size (one cell of travel per frame -> unit) and clamp to
    # [-1,1]: gives a stable direction that is ~0 for a static collider, without
    # the 0/0 blow-up of normalising a near-zero vector.
    inv_cell = b.add("ShaderNodeMath", operation="DIVIDE", label="1/cell")
    b.set_default(inv_cell, 0, 1.0)
    b.link(cell_node, cell_key, inv_cell, 1)
    vx = b.add("ShaderNodeClamp", inputs={"Min": -1.0, "Max": 1.0})
    vxm = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(vx_raw, "Value", vxm, 0)
    b.link(inv_cell, "Value", vxm, 1)
    b.link(vxm, "Value", vx, "Value")
    vy = b.add("ShaderNodeClamp", inputs={"Min": -1.0, "Max": 1.0})
    vym = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(vy_raw, "Value", vym, 0)
    b.link(inv_cell, "Value", vym, 1)
    b.link(vym, "Value", vy, "Value")
    # Directional correction: s_dir = 0.25*beta*(vx*(P_mx-P_px)+vy*(P_my-P_py)).
    diff_x = b.add("ShaderNodeMath", operation="SUBTRACT", label="P_mx-P_px")
    b.link(s_mx, "Value", diff_x, 0)
    b.link(s_px, "Value", diff_x, 1)
    diff_y = b.add("ShaderNodeMath", operation="SUBTRACT", label="P_my-P_py")
    b.link(s_my, "Value", diff_y, 0)
    b.link(s_py, "Value", diff_y, 1)
    tx = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(vx, "Result", tx, 0)
    b.link(diff_x, "Value", tx, 1)
    ty = b.add("ShaderNodeMath", operation="MULTIPLY")
    b.link(vy, "Result", ty, 0)
    b.link(diff_y, "Value", ty, 1)
    term = b.add("ShaderNodeMath", operation="ADD", label="v . dP")
    b.link(tx, "Value", term, 0)
    b.link(ty, "Value", term, 1)
    s_dir = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.25},
                  label="0.25 * term")
    b.link(term, "Value", s_dir, 0)
    s_dir_bw = b.add("ShaderNodeMath", operation="MULTIPLY", label="* bow wave")
    b.link(s_dir, "Value", s_dir_bw, 0)
    b.link(bw_node, bw_key, s_dir_bw, 1)
    # s_total = max(s + s_dir, 0): clamp so a strong bias can't drive pile < 0.
    s_sum = b.add("ShaderNodeMath", operation="ADD", label="s + s_dir")
    b.link(s, "Value", s_sum, 0)
    b.link(s_dir_bw, "Value", s_sum, 1)
    s_total = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0},
                    label="max(s_total,0)")
    b.link(s_sum, "Value", s_total, 0)

    # Free cells convert inflow to height; collider cells keep it as pile.
    read_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_HEIGHT})
    free_s = b.add("ShaderNodeMath", operation="MULTIPLY", label="free*s")
    b.link(free, "Value", free_s, 0)
    b.link(s_total, "Value", free_s, 1)
    new_h = b.add("ShaderNodeMath", operation="ADD", label="h + free*s")
    b.link(read_h, "Attribute", new_h, 0)
    b.link(free_s, "Value", new_h, 1)

    one_minus_free = b.add("ShaderNodeMath", operation="SUBTRACT",
                           label="1-free")
    b.set_default(one_minus_free, 0, 1.0)
    b.link(free, "Value", one_minus_free, 1)
    new_pile = b.add("ShaderNodeMath", operation="MULTIPLY", label="new pile")
    b.link(one_minus_free, "Value", new_pile, 0)
    b.link(s_total, "Value", new_pile, 1)

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
