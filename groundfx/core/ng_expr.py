# SPDX-License-Identifier: GPL-3.0-or-later
"""Expression layer over NodeTreeBuilder: write field math as Python math.

The solver is mostly arithmetic on fields. Spelling every Math node out with
``b.add`` + ``b.link`` buries the physics under plumbing, so this module wraps
an output socket in ``V`` and overloads the operators::

    g = Expr(builder)
    s = g.attr("gfx_base") + g.attr("gfx_h")
    excess = (s - g.attr("gfx_lo")).max(0.0)

Python numbers become default values on the node input (no Value node), so
the generated tree stays small. Float vs. vector is picked from the socket
type: vector operands route through Vector Math, a float times a vector
becomes a SCALE.
"""
from __future__ import annotations

from .ng_builder import NodeTreeBuilder

_VEC_TYPES = {"VECTOR", "ROTATION", "RGBA"}


class V:
    """A node output socket that supports arithmetic."""

    __slots__ = ("g", "sock")

    def __init__(self, g: "Expr", sock):
        self.g = g
        self.sock = sock

    @property
    def is_vec(self) -> bool:
        return self.sock.type in _VEC_TYPES

    # -- arithmetic ---------------------------------------------------------
    def _bin(self, op, other, rev=False):
        a, b = (other, self) if rev else (self, other)
        if _is_vec(a) or _is_vec(b):
            vop = {"ADD": "ADD", "SUBTRACT": "SUBTRACT", "MULTIPLY": "MULTIPLY",
                   "DIVIDE": "DIVIDE"}[op]
            if op == "MULTIPLY" and _is_vec(a) != _is_vec(b):
                vec, sc = (a, b) if _is_vec(a) else (b, a)
                return self.g.scale(vec, sc)
            return self.g.vmath(vop, a, b)
        return self.g.math(op, a, b)

    def __add__(self, o): return self._bin("ADD", o)
    def __radd__(self, o): return self._bin("ADD", o, True)
    def __sub__(self, o): return self._bin("SUBTRACT", o)
    def __rsub__(self, o): return self._bin("SUBTRACT", o, True)
    def __mul__(self, o): return self._bin("MULTIPLY", o)
    def __rmul__(self, o): return self._bin("MULTIPLY", o, True)
    def __truediv__(self, o): return self._bin("DIVIDE", o)
    def __rtruediv__(self, o): return self._bin("DIVIDE", o, True)

    def __neg__(self):
        return self * -1.0

    # -- float helpers ------------------------------------------------------
    def max(self, o): return self.g.math("MAXIMUM", self, o)
    def min(self, o): return self.g.math("MINIMUM", self, o)
    def clamp(self, lo=0.0, hi=1.0): return self.max(lo).min(hi)
    def abs(self): return self.g.math("ABSOLUTE", self)
    def sign(self): return self.g.math("SIGN", self)
    def sqrt(self): return self.g.math("SQRT", self)
    def floor(self): return self.g.math("FLOOR", self)
    def round(self): return self.g.math("ROUND", self)
    def pow(self, o): return self.g.math("POWER", self, o)
    def gt(self, o): return self.g.math("GREATER_THAN", self, o)
    def lt(self, o): return self.g.math("LESS_THAN", self, o)
    def fmod(self, o): return self.g.math("FLOORED_MODULO", self, o)

    # -- vector helpers -----------------------------------------------------
    @property
    def x(self): return self.g.sep(self)[0]
    @property
    def y(self): return self.g.sep(self)[1]
    @property
    def z(self): return self.g.sep(self)[2]

    def length(self): return self.g.vmath("LENGTH", self, out="Value")
    def dot(self, o): return self.g.vmath("DOT_PRODUCT", self, o, out="Value")
    def normalize(self): return self.g.vmath("NORMALIZE", self)


def _is_vec(v) -> bool:
    if isinstance(v, V):
        return v.is_vec
    return isinstance(v, (tuple, list)) and len(v) == 3


class Expr:
    """Node factory returning ``V`` wrappers. Owns a NodeTreeBuilder."""

    def __init__(self, builder: NodeTreeBuilder):
        self.b = builder
        self._sep_cache: dict[int, tuple] = {}

    # -- plumbing -----------------------------------------------------------
    def feed(self, node, key, value) -> None:
        """Link a V into ``node.inputs[key]`` or set a constant default."""
        if value is None:
            return
        sock = self.b._socket(node, node.inputs, key)
        if isinstance(value, V):
            self.b.tree.links.new(value.sock, sock)
        elif hasattr(value, "bl_idname") and hasattr(value, "is_output"):
            self.b.tree.links.new(value, sock)  # raw socket
        else:
            sock.default_value = value

    def node(self, idname, inputs: dict | None = None, **props):
        node = self.b.add(idname, **props)
        for key, val in (inputs or {}).items():
            self.feed(node, key, val)
        return node

    def out(self, node, key=0) -> V:
        return V(self, self.b._socket(node, node.outputs, key))

    # -- math ---------------------------------------------------------------
    def math(self, op, a, b=None, c=None) -> V:
        n = self.b.add("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b, c)):
            self.feed(n, i, v)
        return V(self, n.outputs[0])

    def vmath(self, op, a, b=None, out="Vector") -> V:
        n = self.b.add("ShaderNodeVectorMath", operation=op)
        self.feed(n, 0, a)
        self.feed(n, 1, b)
        return V(self, self.b._socket(n, n.outputs, out))

    def scale(self, vec, s) -> V:
        n = self.b.add("ShaderNodeVectorMath", operation="SCALE")
        self.feed(n, 0, vec)
        self.feed(n, "Scale", s)
        return V(self, n.outputs["Vector"])

    def vec(self, x=0.0, y=0.0, z=0.0) -> V:
        n = self.node("ShaderNodeCombineXYZ", {"X": x, "Y": y, "Z": z})
        return self.out(n, 0)

    def sep(self, v: V):
        key = v.sock.as_pointer()
        if key not in self._sep_cache:
            n = self.node("ShaderNodeSeparateXYZ", {0: v})
            self._sep_cache[key] = tuple(V(self, n.outputs[i]) for i in range(3))
        return self._sep_cache[key]

    def mix(self, a, b, t) -> V:
        """Linear blend a + (b - a) * t (floats or vectors)."""
        return a + (b - a) * t

    def switch(self, cond, false, true, kind="FLOAT") -> V:
        n = self.node("GeometryNodeSwitch", {"Switch": cond, "False": false,
                                             "True": true}, input_type=kind)
        return self.out(n, 0)

    # -- inputs ---------------------------------------------------------------
    def index(self) -> V:
        return self.out(self.b.add("GeometryNodeInputIndex"), 0)

    def position(self) -> V:
        return self.out(self.b.add("GeometryNodeInputPosition"), 0)

    def attr(self, name, kind="FLOAT") -> V:
        n = self.node("GeometryNodeInputNamedAttribute", {"Name": name},
                      data_type=kind)
        return self.out(n, "Attribute")

    def random(self, seed=0, lo=0.0, hi=1.0, ident=None) -> V:
        n = self.node("FunctionNodeRandomValue",
                      {"Min": lo, "Max": hi, "Seed": seed, "ID": ident},
                      data_type="FLOAT")
        return self.out(n, "Value")

    # -- geometry -------------------------------------------------------------
    def store(self, geo, name, value, kind="FLOAT", domain="POINT",
              selection=None) -> V:
        n = self.node("GeometryNodeStoreNamedAttribute",
                      {"Geometry": geo, "Name": name, "Value": value,
                       "Selection": selection},
                      data_type=kind, domain=domain)
        return self.out(n, "Geometry")

    def sample_index(self, geo, value, index, kind="FLOAT",
                     domain="POINT") -> V:
        n = self.node("GeometryNodeSampleIndex",
                      {"Geometry": geo, "Value": value, "Index": index},
                      data_type=kind, domain=domain)
        return self.out(n, "Value")

    def capture(self, geo, values, domain="POINT"):
        """Freeze fields on ``geo``. Returns (geometry, [captured V...])."""
        n = self.b.add("GeometryNodeCaptureAttribute", domain=domain)
        outs = []
        for i, val in enumerate(values):
            kind = "VECTOR" if _is_vec(val) else "FLOAT"
            n.capture_items.new(kind, f"v{i}")
            # By name: 5.2 puts a Selection socket before the items.
            self.feed(n, f"v{i}", val)
            outs.append(V(self, n.outputs[f"v{i}"]))
        self.feed(n, "Geometry", geo)
        return V(self, n.outputs["Geometry"]), outs

    def stat(self, geo, value, selection=None, out="Mean") -> V:
        n = self.node("GeometryNodeAttributeStatistic",
                      {"Geometry": geo, "Attribute": value,
                       "Selection": selection},
                      data_type="FLOAT", domain="POINT")
        return self.out(n, out)


def make(tree) -> tuple[NodeTreeBuilder, Expr]:
    b = NodeTreeBuilder(tree)
    return b, Expr(b)
