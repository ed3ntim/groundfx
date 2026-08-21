# SPDX-License-Identifier: GPL-3.0-or-later
"""Angle-of-repose relaxation (the physics that makes material *behave*).

A Laplacian/blur smoother cannot enforce a repose angle: on a uniform ramp its
value is zero, so a slope steeper than repose would never collapse. Instead we
run a **toppling** step — the standard height-field granular relaxation — which
compares each cell to its four grid neighbours individually and moves material
downhill whenever the height difference exceeds the stable slope
``tan(theta) * cell_size`` (plus a cohesion term that lets wet snow / thick mud
hold a steeper wall).

Neighbours are addressed by index arithmetic on the regular grid
(row-major, ``index = row * N + col``) via Sample Index. Border cells mask out
the wrapped-around neighbour so material never teleports across an edge. The
update is symmetric (out-flow from A to B equals in-flow to B from A), so it
conserves mass except where a cell would go negative and is clamped.

The whole thing lives inside a Repeat zone so it iterates N times per frame.
Verified against Blender 5.2.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_zones import make_repeat_zone
from ..constants import ATTR_HEIGHT, ATTR_BASE, ATTR_SURFACE, ATTR_CARVE

# A neighbour with carve above this is occupied by the collider: material may
# not flow into it (the collider fills that space). Blocking it lets a berm
# build at the rim instead of draining back into the hole and being scraped
# away (B1 "no piling").
_OCCUPIED_EPS = 1e-5

# Stability factor: fraction of the computed excess moved per iteration. Below
# 0.25 the 4-neighbour sum can't overshoot into oscillation.
_STABILITY = 0.25

# Discrete-grid calibration: the 4-neighbour toppling holds a slightly steeper
# slope than the continuous ideal, so the measured repose angle sits a few
# degrees high. Scaling the stable-slope threshold by this factor centres the
# measured angle on the configured one. Calibrated against the cone-collapse
# test (see tests/test_relax.py).
_SLOPE_CALIB = 0.88


def _store_surface(b, geo_node, geo_key):
    """Append store of gfx_surface = base + h to the geometry chain."""
    rb = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
               inputs={"Name": ATTR_BASE})
    rh = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
               inputs={"Name": ATTR_HEIGHT})
    s = b.add("ShaderNodeMath", operation="ADD", label="surface = base + h")
    b.link(rb, "Attribute", s, 0)
    b.link(rh, "Attribute", s, 1)
    store = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                  domain="POINT", inputs={"Name": ATTR_SURFACE})
    b.link(geo_node, geo_key, store, "Geometry")
    b.link(s, "Value", store, "Value")
    return store


def _neighbour_flow(b, sample_geo_node, self_surface, index_node,
                    offset, valid_node, threshold):
    """Net material change for one neighbour direction.

    Returns (node, key) yielding ``(inflow - outflow) * valid`` for the
    neighbour at ``index + offset``.
    """
    # neighbour index = index + offset
    nidx = b.add("ShaderNodeMath", operation="ADD", inputs={1: float(offset)},
                 label=f"nidx {offset:+d}")
    b.link(index_node, "Index", nidx, 0)

    sample = b.add("GeometryNodeSampleIndex", data_type="FLOAT", domain="POINT",
                   clamp=True)
    # Sample the cached surface attribute from the (pre-iteration) geometry.
    surf_attr = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                      inputs={"Name": ATTR_SURFACE})
    b.link(sample_geo_node, "Geometry", sample, "Geometry")
    b.link(surf_attr, "Attribute", sample, "Value")
    b.link(nidx, "Value", sample, "Index")

    # diff = H_self - H_neighbour
    diff = b.add("ShaderNodeMath", operation="SUBTRACT", label="H-Hn")
    b.link(self_surface, "Value", diff, 0)
    b.link(sample, "Value", diff, 1)

    # outflow = max(0, diff - T) ; inflow = max(0, -diff - T)
    out_over = b.add("ShaderNodeMath", operation="SUBTRACT", label="diff-T")
    b.link(diff, "Value", out_over, 0)
    b.link(threshold, "Value", out_over, 1)
    outflow = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0})
    b.link(out_over, "Value", outflow, 0)

    neg = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: -1.0})
    b.link(diff, "Value", neg, 0)
    in_over = b.add("ShaderNodeMath", operation="SUBTRACT", label="-diff-T")
    b.link(neg, "Value", in_over, 0)
    b.link(threshold, "Value", in_over, 1)
    inflow = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0})
    b.link(in_over, "Value", inflow, 0)

    net = b.add("ShaderNodeMath", operation="SUBTRACT", label="in-out")
    b.link(inflow, "Value", net, 0)
    b.link(outflow, "Value", net, 1)
    masked = b.add("ShaderNodeMath", operation="MULTIPLY", label="* valid")
    b.link(net, "Value", masked, 0)
    b.link(valid_node, "Value", masked, 1)
    free = _neighbour_free(b, sample_geo_node, nidx, "Value")
    masked_free = b.add("ShaderNodeMath", operation="MULTIPLY", label="* free")
    b.link(masked, "Value", masked_free, 0)
    b.link(free, "Value", masked_free, 1)
    return masked_free


def _neighbour_free(b, geo_node, nidx_node, nidx_key):
    """1.0 if the neighbour at ``nidx`` is *not* under the collider."""
    sample = b.add("GeometryNodeSampleIndex", data_type="FLOAT", domain="POINT",
                   clamp=True)
    carve_attr = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                       inputs={"Name": ATTR_CARVE})
    b.link(geo_node, "Geometry", sample, "Geometry")
    b.link(carve_attr, "Attribute", sample, "Value")
    b.link(nidx_node, nidx_key, sample, "Index")
    free = b.add("ShaderNodeMath", operation="LESS_THAN",
                 inputs={1: _OCCUPIED_EPS}, label="neighbour free")
    b.link(sample, "Value", free, 0)
    return free


def add_relaxation(b: NodeTreeBuilder, geo_node, geo_key, refs):
    """Append the relaxation Repeat zone; return (out_node, out_key).

    ``refs`` maps parameter name -> (node, socket_key) for the value sources:
    'repose' (radians), 'cohesion', 'flow', 'cell_size', 'grid_n', 'iterations'.
    """
    # Cache the surface attribute before entering the loop.
    pre = _store_surface(b, geo_node, geo_key)

    zone = make_repeat_zone(b, repeat_items=[("GEOMETRY", "Geometry")])
    b.link(pre, "Geometry", zone.input, "Geometry")
    # Drive iteration count.
    rn, rk = refs["iterations"]
    b.link(rn, rk, zone.input, "Iterations")

    it_geo = zone.input  # geometry available inside the loop

    # Stable height step over one cell: T = (tan(repose)*calib + cohesion) * cell.
    # Cohesion is an *extra slope* the material holds (a Bingham yield), so it
    # must be added to the tangent BEFORE scaling by cell size — otherwise, as
    # an absolute height, a 2 cm cohesion would let a 1.5 cm cell hold a ~60°
    # wall at close-up scale, and slopes never relaxed to the repose angle (B1).
    tan = b.add("ShaderNodeMath", operation="TANGENT", label="tan(repose)")
    b.link(*refs["repose"], tan, 0)
    tan_c = b.add("ShaderNodeMath", operation="MULTIPLY",
                  inputs={1: _SLOPE_CALIB}, label="tan*calib")
    b.link(tan, "Value", tan_c, 0)
    tan_coh = b.add("ShaderNodeMath", operation="ADD", label="+ cohesion slope")
    b.link(tan_c, "Value", tan_coh, 0)
    b.link(*refs["cohesion"], tan_coh, 1)
    threshold = b.add("ShaderNodeMath", operation="MULTIPLY", label="T = slope*cell")
    b.link(tan_coh, "Value", threshold, 0)
    b.link(*refs["cell_size"], threshold, 1)

    # Grid coordinates from the point index.
    index = b.add("GeometryNodeInputIndex")
    grid_n_node, grid_n_key = refs["grid_n"]
    col = b.add("ShaderNodeMath", operation="MODULO", label="col")
    b.link(index, "Index", col, 0)
    b.link(grid_n_node, grid_n_key, col, 1)
    row = b.add("ShaderNodeMath", operation="DIVIDE", label="row f")
    b.link(index, "Index", row, 0)
    b.link(grid_n_node, grid_n_key, row, 1)
    row_f = b.add("ShaderNodeMath", operation="FLOOR", label="row")
    b.link(row, "Value", row_f, 0)

    n_minus_1 = b.add("ShaderNodeMath", operation="SUBTRACT", inputs={1: 1.0},
                      label="N-1")
    b.link(grid_n_node, grid_n_key, n_minus_1, 0)

    def valid_lt(a_node, a_key, b_node, b_key, label):
        v = b.add("ShaderNodeMath", operation="LESS_THAN", label=label)
        b.link(a_node, a_key, v, 0)
        b.link(b_node, b_key, v, 1)
        return v

    def valid_gt0(a_node, a_key, label):
        v = b.add("ShaderNodeMath", operation="GREATER_THAN", inputs={1: 0.0},
                  label=label)
        b.link(a_node, a_key, v, 0)
        return v

    valid_px = valid_lt(col, "Value", n_minus_1, "Value", "col<N-1")
    valid_mx = valid_gt0(col, "Value", "col>0")
    valid_py = valid_lt(row_f, "Value", n_minus_1, "Value", "row<N-1")
    valid_my = valid_gt0(row_f, "Value", "row>0")

    # Self surface inside the loop.
    self_surf = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                      inputs={"Name": ATTR_SURFACE})
    self_surf_val = b.add("ShaderNodeMath", operation="ADD", inputs={1: 0.0},
                          label="H_self")
    b.link(self_surf, "Attribute", self_surf_val, 0)

    # grid_n as float for offset +N / -N.
    # Four directions.
    dirs = []
    # +x offset +1, -x offset -1
    dirs.append(_neighbour_flow(b, it_geo, self_surf_val, index, 1,
                                valid_px, threshold))
    dirs.append(_neighbour_flow(b, it_geo, self_surf_val, index, -1,
                                valid_mx, threshold))
    # +y / -y need offset = +/- N. N is dynamic, so build those via add nodes
    # that take grid_n as the offset.
    for sign, valid, label in ((1.0, valid_py, "+y"), (-1.0, valid_my, "-y")):
        nidx = b.add("ShaderNodeMath", operation="MULTIPLY_ADD",
                     label=f"nidx {label}")
        # index + sign * grid_n  ->  MULTIPLY_ADD(grid_n, sign, index)
        b.link(grid_n_node, grid_n_key, nidx, 0)
        b.set_default(nidx, 1, sign)
        b.link(index, "Index", nidx, 2)
        sample = b.add("GeometryNodeSampleIndex", data_type="FLOAT",
                       domain="POINT", clamp=True)
        surf_attr = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                          inputs={"Name": ATTR_SURFACE})
        b.link(it_geo, "Geometry", sample, "Geometry")
        b.link(surf_attr, "Attribute", sample, "Value")
        b.link(nidx, "Value", sample, "Index")
        diff = b.add("ShaderNodeMath", operation="SUBTRACT", label=f"H-Hn {label}")
        b.link(self_surf_val, "Value", diff, 0)
        b.link(sample, "Value", diff, 1)
        out_over = b.add("ShaderNodeMath", operation="SUBTRACT")
        b.link(diff, "Value", out_over, 0)
        b.link(threshold, "Value", out_over, 1)
        outflow = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0})
        b.link(out_over, "Value", outflow, 0)
        neg = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: -1.0})
        b.link(diff, "Value", neg, 0)
        in_over = b.add("ShaderNodeMath", operation="SUBTRACT")
        b.link(neg, "Value", in_over, 0)
        b.link(threshold, "Value", in_over, 1)
        inflow = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0})
        b.link(in_over, "Value", inflow, 0)
        net = b.add("ShaderNodeMath", operation="SUBTRACT")
        b.link(inflow, "Value", net, 0)
        b.link(outflow, "Value", net, 1)
        masked = b.add("ShaderNodeMath", operation="MULTIPLY", label=f"*valid {label}")
        b.link(net, "Value", masked, 0)
        b.link(valid, "Value", masked, 1)
        free = _neighbour_free(b, it_geo, nidx, "Value")
        masked_free = b.add("ShaderNodeMath", operation="MULTIPLY",
                            label=f"*free {label}")
        b.link(masked, "Value", masked_free, 0)
        b.link(free, "Value", masked_free, 1)
        dirs.append(masked_free)

    # sum the four nets
    s01 = b.add("ShaderNodeMath", operation="ADD")
    b.link(dirs[0], "Value", s01, 0)
    b.link(dirs[1], "Value", s01, 1)
    s23 = b.add("ShaderNodeMath", operation="ADD")
    b.link(dirs[2], "Value", s23, 0)
    b.link(dirs[3], "Value", s23, 1)
    net_sum = b.add("ShaderNodeMath", operation="ADD", label="net sum")
    b.link(s01, "Value", net_sum, 0)
    b.link(s23, "Value", net_sum, 1)

    # delta = net_sum * stability * flow_rate
    delta = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: _STABILITY},
                  label="* stability")
    b.link(net_sum, "Value", delta, 0)
    delta_f = b.add("ShaderNodeMath", operation="MULTIPLY", label="* flow")
    b.link(delta, "Value", delta_f, 0)
    b.link(*refs["flow"], delta_f, 1)

    # An occupied cell (under the collider) doesn't relax — its height is the
    # carved surface. Masking its delta keeps mass conserved with the blocked
    # inflow from free neighbours (no phantom fill in the hole).
    self_carve = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                       inputs={"Name": ATTR_CARVE})
    self_free = b.add("ShaderNodeMath", operation="LESS_THAN",
                      inputs={1: _OCCUPIED_EPS}, label="self free")
    b.link(self_carve, "Attribute", self_free, 0)
    delta_m = b.add("ShaderNodeMath", operation="MULTIPLY", label="* self free")
    b.link(delta_f, "Value", delta_m, 0)
    b.link(self_free, "Value", delta_m, 1)

    # new_h = max(0, h + delta)
    read_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_HEIGHT})
    h_plus = b.add("ShaderNodeMath", operation="ADD", label="h + delta")
    b.link(read_h, "Attribute", h_plus, 0)
    b.link(delta_m, "Value", h_plus, 1)
    new_h = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0},
                  label="max(0,_)")
    b.link(h_plus, "Value", new_h, 0)

    store_h = b.add("GeometryNodeStoreNamedAttribute", data_type="FLOAT",
                    domain="POINT", inputs={"Name": ATTR_HEIGHT})
    b.link(it_geo, "Geometry", store_h, "Geometry")
    b.link(new_h, "Value", store_h, "Value")

    # Refresh gfx_surface for the next iteration's sampling.
    refreshed = _store_surface(b, store_h, "Geometry")
    b.link(refreshed, "Geometry", zone.output, "Geometry")

    return zone.output, "Geometry"
