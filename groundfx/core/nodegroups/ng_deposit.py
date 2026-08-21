# SPDX-License-Identifier: GPL-3.0-or-later
"""Displacement / piling: carved material heaps up at the rim instead of vanishing.

The carve step converts removed height into a ``gfx_pile`` buffer (scaled by
``displacement_ratio``; the remainder is compaction). This module then moves
that pile out of the collider footprint to the free cells around it, forming a
berm — which the subsequent relaxation smooths to the repose angle.

The transport is a mass-conserving **lazy** diffusion of the pile buffer with a
reflecting boundary at the collider: a cell keeps ``1 - spread`` of its pile and
sends ``spread/4`` to each valid neighbour. The self term matters more than it
looks: a pure 4-neighbour average (no self term) is *odd-even decoupled* — on
the bipartite grid the pile hops from one checkerboard sublattice to the other
every iteration, so after N steps only cells of one parity have received
anything and the berm comes out as a one-cell comb of teeth (B2 "spiky").
Keeping part of the pile in place couples both sublattices, and as a bonus keeps
the deposit local (spread ~ sqrt(iters * spread / 2) cells instead of one cell
per iteration), which is what stops a held collider churning material out across
the whole domain.

Free cells (not under the collider) convert a ``deposit_rate`` share of their
pile into height and relay the rest; collider cells keep all of it to relay
further out. A deadband dumps a pile too small to matter instead of letting it
crawl forever, so the field actually settles.

The same stencil carries the bow wave (E4-S3): the neighbour the material comes
from is given extra weight, so the heap drifts toward the collider's motion.
The direction is read from the centroid shift of ``gfx_occ`` vs ``gfx_occ_prev``
and the strength is the ``bow_wave`` input (0 = pure isotropic rim). Biasing the
gather **upwind** matters: the centred difference this used to use cannot see
the one-cell mode at all, so a sawtooth grew freely along the bow wave.
Verified against Blender 5.2.

Note what this *cannot* fix: pile is only created where the collider cuts in a
given frame, so a collider crossing three cells per frame drops one lump every
three cells along the rim, whatever the transport does with it afterwards
(measured: the ripple period equals the per-frame travel, exactly). That residue
is temporal undersampling and needs substeps (E3-S5); smearing the transport
along the path only spreads the lumps around without removing them.
"""
from __future__ import annotations

from ..ng_builder import NodeTreeBuilder
from ..ng_zones import make_repeat_zone
from ..constants import ATTR_HEIGHT, ATTR_PILE, ATTR_OCC, ATTR_OCC_PREV

# Coverage above this counts as "the collider stands here" for the centroid
# that gives the motion direction.
_COVERED_EPS = 0.5

# A pile below this (in metres) is dumped where it stands instead of being
# relayed on: without it the tail of the diffusion creeps outward forever and
# the surface never comes to rest (B2 "permanent churn").
_PILE_DEADBAND = 2e-5

# Strength of the upwind bias, per cell of per-frame motion, at bow_wave = 1.
# It is an extra *gather weight* on the upwind neighbour rather than a separate
# correction term, so it can never make a weight negative however fast the
# collider moves.
_ADVECT_BIAS = 1.0


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

    ``refs`` maps: 'iterations' (deposit steps), 'grid_n', 'cell_size',
    'bow_wave', 'spread' (share of a pile that moves per step) and 'rate'
    (share a free cell lays down as height per step).
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

    # Neighbour piles (masked at borders) and this cell's own pile.
    s_px = _sample_neighbour(b, it_geo, ATTR_PILE, idx_px, "Value", valid_px)
    s_mx = _sample_neighbour(b, it_geo, ATTR_PILE, idx_mx, "Value", valid_mx)
    s_py = _sample_neighbour(b, it_geo, ATTR_PILE, idx_py, "Value", valid_py)
    s_my = _sample_neighbour(b, it_geo, ATTR_PILE, idx_my, "Value", valid_my)
    p_self = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_PILE})

    # free = 1 - coverage: how much of this cell is *not* under the collider.
    # Continuous, so a rim cell the collider half covers lays down half its
    # material instead of flipping between all and nothing between frames.
    occ = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                inputs={"Name": ATTR_OCC})
    free = b.add("ShaderNodeMath", operation="SUBTRACT", label="free = 1-occ")
    b.set_default(free, 0, 1.0)
    b.link(occ, "Attribute", free, 1)

    # --- bow wave: advect the pile toward the collider's motion (E4-T10) ----
    # The motion direction is the shift of the footprint's *centroid* between
    # frames: centroid(occ) - centroid(occ_prev). This is a single translation
    # vector for the whole footprint, so it is genuinely zero for a stationary
    # (merely deepening) collider -- unlike a per-cell carve gradient, which
    # points radially inward around any footprint and would choke the rim.
    # Biasing each free cell's inflow along that vector heaps material up ahead.
    bw_node, bw_key = refs["bow_wave"]
    cell_node, cell_key = refs["cell_size"]
    occ_prev = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                     inputs={"Name": ATTR_OCC_PREV})
    mask_now = b.add("ShaderNodeMath", operation="GREATER_THAN",
                     inputs={1: _COVERED_EPS}, label="covered now")
    b.link(occ, "Attribute", mask_now, 0)
    mask_prev = b.add("ShaderNodeMath", operation="GREATER_THAN",
                      inputs={1: _COVERED_EPS}, label="covered before")
    b.link(occ_prev, "Attribute", mask_prev, 0)
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

    # --- transport stencil --------------------------------------------------
    # One normalised gather does both jobs. Every cell uses the same weights
    # (the motion vector is global), so whatever a cell gathers from a
    # neighbour is exactly what that neighbour gives away: mass is conserved,
    # and because no weight can go negative the transport is monotone -- there
    # is no way for a grid-scale sawtooth to grow out of it.
    #
    #   w_self = 1 - spread          material that stays put
    #   w_axis = spread/4            isotropic share per neighbour
    #   the upwind neighbour gets a further bias * bow_wave * |v|
    #
    # Gathering *more* from the cell behind is what shifts the heap forward,
    # i.e. the bow wave. Doing it this way instead of adding a signed advection
    # term also removes the clamp that used to be needed to stop a strong bias
    # driving the pile negative -- and that clamp could invent mass.
    spread_node, spread_key = refs["spread"]
    bw_node, bw_key = refs["bow_wave"]
    w_base = b.add("ShaderNodeMath", operation="MULTIPLY", inputs={1: 0.25},
                   label="spread/4")
    b.link(spread_node, spread_key, w_base, 0)
    w_self = b.add("ShaderNodeMath", operation="SUBTRACT", label="1-spread")
    b.set_default(w_self, 0, 1.0)
    b.link(spread_node, spread_key, w_self, 1)

    def _upwind_extra(v_node, v_key, sign, label):
        """bias * bow_wave * max(sign*v, 0) for the neighbour material comes from."""
        signed = b.add("ShaderNodeMath", operation="MULTIPLY",
                       inputs={1: float(sign)})
        b.link(v_node, v_key, signed, 0)
        amount = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0},
                       label=f"upwind {label}")
        b.link(signed, "Value", amount, 0)
        scaled = b.add("ShaderNodeMath", operation="MULTIPLY",
                       inputs={1: _ADVECT_BIAS})
        b.link(amount, "Value", scaled, 0)
        biased = b.add("ShaderNodeMath", operation="MULTIPLY",
                       label=f"* bow wave {label}")
        b.link(scaled, "Value", biased, 0)
        b.link(bw_node, bw_key, biased, 1)
        return biased

    def _weight(v_node, v_key, sign, label):
        extra = _upwind_extra(v_node, v_key, sign, label)
        w = b.add("ShaderNodeMath", operation="ADD", label=f"w {label}")
        b.link(w_base, "Value", w, 0)
        b.link(extra, "Value", w, 1)
        return w

    # Moving +x means the material arrives from -x, so -x is the upwind side.
    w_mx = _weight(vx, "Result", 1.0, "-x")
    w_px = _weight(vx, "Result", -1.0, "+x")
    w_my = _weight(vy, "Result", 1.0, "-y")
    w_py = _weight(vy, "Result", -1.0, "+y")

    def _term(p_node, p_key, w_node, label):
        t = b.add("ShaderNodeMath", operation="MULTIPLY", label=label)
        b.link(p_node, p_key, t, 0)
        b.link(w_node, "Value", t, 1)
        return t

    terms = [
        _term(p_self, "Attribute", w_self, "kept"),
        _term(s_mx, "Value", w_mx, "from -x"),
        _term(s_px, "Value", w_px, "from +x"),
        _term(s_my, "Value", w_my, "from -y"),
        _term(s_py, "Value", w_py, "from +y"),
    ]
    weights = [w_self, w_mx, w_px, w_my, w_py]

    def _sum5(nodes, keys, label):
        a = b.add("ShaderNodeMath", operation="ADD")
        b.link(nodes[0], keys[0], a, 0)
        b.link(nodes[1], keys[1], a, 1)
        c = b.add("ShaderNodeMath", operation="ADD")
        b.link(nodes[2], keys[2], c, 0)
        b.link(nodes[3], keys[3], c, 1)
        ac = b.add("ShaderNodeMath", operation="ADD")
        b.link(a, "Value", ac, 0)
        b.link(c, "Value", ac, 1)
        total = b.add("ShaderNodeMath", operation="ADD", label=label)
        b.link(ac, "Value", total, 0)
        b.link(nodes[4], keys[4], total, 1)
        return total

    gathered = _sum5(terms, ["Value"] * 5, "gathered")
    denom = _sum5(weights, ["Value"] * 5, "weight sum")
    denom_safe = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 1e-6})
    b.link(denom, "Value", denom_safe, 0)
    s_total = b.add("ShaderNodeMath", operation="DIVIDE", label="transported pile")
    b.link(gathered, "Value", s_total, 0)
    b.link(denom_safe, "Value", s_total, 1)

    # --- lay down / relay ---------------------------------------------------
    # A free cell converts ``rate`` of its pile into height and relays the rest,
    # so a berm builds as a ramp over several cells instead of a one-cell wall
    # at the footprint edge. ``keep`` is additionally capped by the deadband, so
    # a pile too small to see is dumped rather than relayed forever.
    rate_node, rate_key = refs["rate"]
    keep_frac = b.add("ShaderNodeMath", operation="SUBTRACT", label="1-rate")
    b.set_default(keep_frac, 0, 1.0)
    b.link(rate_node, rate_key, keep_frac, 1)
    keep_a = b.add("ShaderNodeMath", operation="MULTIPLY", label="(1-rate)*s")
    b.link(s_total, "Value", keep_a, 0)
    b.link(keep_frac, "Value", keep_a, 1)
    keep_b = b.add("ShaderNodeMath", operation="SUBTRACT",
                   inputs={1: _PILE_DEADBAND}, label="s - deadband")
    b.link(s_total, "Value", keep_b, 0)
    keep_b0 = b.add("ShaderNodeMath", operation="MAXIMUM", inputs={1: 0.0})
    b.link(keep_b, "Value", keep_b0, 0)
    keep = b.add("ShaderNodeMath", operation="MINIMUM", label="kept pile")
    b.link(keep_a, "Value", keep, 0)
    b.link(keep_b0, "Value", keep, 1)
    give = b.add("ShaderNodeMath", operation="SUBTRACT", label="laid down")
    b.link(s_total, "Value", give, 0)
    b.link(keep, "Value", give, 1)

    read_h = b.add("GeometryNodeInputNamedAttribute", data_type="FLOAT",
                   inputs={"Name": ATTR_HEIGHT})
    free_give = b.add("ShaderNodeMath", operation="MULTIPLY", label="free*give")
    b.link(free, "Value", free_give, 0)
    b.link(give, "Value", free_give, 1)
    new_h = b.add("ShaderNodeMath", operation="ADD", label="h + free*give")
    b.link(read_h, "Attribute", new_h, 0)
    b.link(free_give, "Value", new_h, 1)

    # New pile: free cells hold back ``keep``; collider cells relay everything.
    one_minus_free = b.add("ShaderNodeMath", operation="SUBTRACT",
                           label="1-free")
    b.set_default(one_minus_free, 0, 1.0)
    b.link(free, "Value", one_minus_free, 1)
    occupied_pile = b.add("ShaderNodeMath", operation="MULTIPLY",
                          label="occupied relays all")
    b.link(one_minus_free, "Value", occupied_pile, 0)
    b.link(s_total, "Value", occupied_pile, 1)
    free_pile = b.add("ShaderNodeMath", operation="MULTIPLY",
                      label="free keeps rest")
    b.link(free, "Value", free_pile, 0)
    b.link(keep, "Value", free_pile, 1)
    new_pile = b.add("ShaderNodeMath", operation="ADD", label="new pile")
    b.link(occupied_pile, "Value", new_pile, 0)
    b.link(free_pile, "Value", new_pile, 1)

    # gfx_h is stored first so the pile expression above still reads the
    # pre-iteration pile through the untouched attribute.
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
