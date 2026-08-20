# SPDX-License-Identifier: GPL-3.0-or-later
"""Declarative builder for Geometry Node trees.

The solver is 150+ nodes across several groups. Hand-wiring them through the
raw ``node_group.nodes.new`` / ``links.new`` API is unreadable and undiffable.
``NodeTreeBuilder`` wraps a tree with a compact, typed API:

    b = NodeTreeBuilder(tree)
    geo_in = b.add("NodeGroupInput")
    grid = b.add("GeometryNodeMeshGrid", size_x=2.0, size_y=2.0)
    geo_out = b.add("NodeGroupOutput")
    b.link(grid, "Mesh", geo_out, "Geometry")
    b.layout()

Socket endpoints are addressed by name or by integer index (needed when a node
has several sockets of the same name, e.g. Math). Auto-layout places nodes in
columns by their longest path from the inputs, so the generated graph is
legible when opened in the editor.

Verified against Blender 5.2 — see docs/API_NOTES.md.
"""
from __future__ import annotations

from typing import Union

import bpy

from ..utils import compat, log

# A socket endpoint: (node, key) where key is a socket name or an int index.
SocketKey = Union[str, int]


class NodeTreeBuilder:
    """Thin, typed convenience layer over a bpy node tree."""

    def __init__(self, tree: bpy.types.NodeTree):
        self.tree = tree
        self._nodes: list[bpy.types.Node] = []

    # -- interface (group inputs/outputs) -----------------------------------
    def input(self, name, socket_type, *, default=None, min=None, max=None,
              subtype=None, description="") -> bpy.types.NodeTreeInterfaceSocket:
        """Add a group INPUT socket and configure it in one call."""
        item = compat.new_tree_socket(self.tree, name, "INPUT", socket_type)
        self._configure_socket(item, default, min, max, subtype, description)
        return item

    def output(self, name, socket_type, *, description="",
               ) -> bpy.types.NodeTreeInterfaceSocket:
        """Add a group OUTPUT socket."""
        item = compat.new_tree_socket(self.tree, name, "OUTPUT", socket_type)
        if description:
            item.description = description
        return item

    @staticmethod
    def _configure_socket(item, default, min, max, subtype, description):
        if default is not None and hasattr(item, "default_value"):
            item.default_value = default
        if min is not None and hasattr(item, "min_value"):
            item.min_value = min
        if max is not None and hasattr(item, "max_value"):
            item.max_value = max
        if subtype is not None and hasattr(item, "subtype"):
            item.subtype = subtype
        if description:
            item.description = description

    # -- nodes --------------------------------------------------------------
    def add(self, bl_idname: str, *, name: str = "", label: str = "",
            inputs: dict | None = None, **props) -> bpy.types.Node:
        """Create a node, set node-level properties, and default input values.

        ``props`` sets attributes on the node itself (e.g. operation="ADD").
        ``inputs`` sets default_value on unlinked input sockets, keyed by name
        or index.
        """
        node = self.tree.nodes.new(bl_idname)
        if name:
            node.name = name
        if label:
            node.label = label
        for key, value in props.items():
            setattr(node, key, value)
        if inputs:
            for key, value in inputs.items():
                self.set_default(node, key, value)
        self._nodes.append(node)
        return node

    @staticmethod
    def _socket(node, collection, key: SocketKey):
        """Resolve a socket by int index or by name (first enabled match)."""
        if isinstance(key, int):
            return collection[key]
        for sock in collection:
            if sock.name == key and sock.enabled:
                return sock
        # Fall back to any matching name (some sockets report enabled oddly).
        for sock in collection:
            if sock.name == key:
                return sock
        raise KeyError(f"socket {key!r} not found on node {node.name!r}")

    def set_default(self, node, key: SocketKey, value) -> None:
        """Set the default_value on an (unlinked) input socket."""
        sock = self._socket(node, node.inputs, key)
        sock.default_value = value

    def link(self, from_node, from_key: SocketKey,
             to_node, to_key: SocketKey) -> bpy.types.NodeLink:
        """Connect an output socket to an input socket."""
        src = self._socket(from_node, from_node.outputs, from_key)
        dst = self._socket(to_node, to_node.inputs, to_key)
        return self.tree.links.new(src, dst)

    # -- layout -------------------------------------------------------------
    def layout(self, *, x_gap: float = 220.0, y_gap: float = 220.0) -> None:
        """Place nodes in columns by longest path from the inputs.

        Purely cosmetic — makes the generated tree readable in the editor.
        """
        depth: dict[bpy.types.Node, int] = {}

        def node_depth(node, seen) -> int:
            if node in depth:
                return depth[node]
            if node in seen:
                return 0  # cycle guard (shouldn't happen in our DAGs)
            seen = seen | {node}
            best = 0
            for inp in node.inputs:
                for link in inp.links:
                    best = max(best, node_depth(link.from_node, seen) + 1)
            depth[node] = best
            return best

        for node in self._nodes:
            node_depth(node, frozenset())

        columns: dict[int, list] = {}
        for node, d in depth.items():
            columns.setdefault(d, []).append(node)

        for d, col_nodes in columns.items():
            for row, node in enumerate(col_nodes):
                node.location = (d * x_gap, -row * y_gap)

    # -- convenience --------------------------------------------------------
    @property
    def nodes(self):
        return tuple(self._nodes)

    def group_io(self):
        """Create and return the (input, output) interface nodes."""
        gin = self.add("NodeGroupInput")
        gout = self.add("NodeGroupOutput")
        return gin, gout


def new_geometry_group(name: str) -> bpy.types.GeometryNodeTree:
    """Create (or replace) a Geometry Node group data-block by name."""
    existing = bpy.data.node_groups.get(name)
    if existing is not None:
        bpy.data.node_groups.remove(existing)
        log.debug("replaced existing node group %s", name)
    return bpy.data.node_groups.new(name, "GeometryNodeTree")
