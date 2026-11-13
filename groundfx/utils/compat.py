# SPDX-License-Identifier: GPL-3.0-or-later
"""Version-dependent API access, isolated behind feature detection.

Everything the plan flagged as "might change between Blender versions" is
funnelled through here, so the rest of the codebase never branches on a
version number. Facts encoded here are verified against 5.2.0 LTS — see
docs/API_NOTES.md.
"""
from __future__ import annotations

import bpy

# Minimum version GroundFX supports. Kept as data so the __init__ guard and
# the manifest stay in agreement.
BLENDER_MIN = (5, 3, 0)


def is_supported() -> bool:
    """True when the running Blender is new enough for GroundFX."""
    return bpy.app.version >= BLENDER_MIN


def version_string() -> str:
    return bpy.app.version_string


def new_tree_socket(tree, name, in_out, socket_type):
    """Create an interface socket on a node tree (5.x ``interface`` API).

    ``in_out`` is "INPUT" or "OUTPUT"; ``socket_type`` e.g. "NodeSocketFloat".
    Returns the created interface item so the caller can set default/min/max.
    """
    return tree.interface.new_socket(name, in_out=in_out, socket_type=socket_type)


def iter_input_sockets(tree):
    """Yield interface items that are inputs, in interface order."""
    for item in tree.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT":
            yield item


def socket_identifier_map(tree):
    """Map input socket *name* -> stable *identifier* ("Socket_N").

    Modifier inputs are addressed by identifier (``modifier["Socket_3"]``),
    never by index. We look them up by name once and cache the identifiers.
    """
    return {item.name: item.identifier for item in iter_input_sockets(tree)}


def pair_zone(input_node, output_node):
    """Pair a simulation/repeat input node with its output node."""
    input_node.pair_with_output(output_node)


def bake_geometry_nodes(objects) -> bool:
    """Bake all geometry-node simulation caches for ``objects``.

    Uses ``simulation_nodes_cache_bake`` (verified present in 5.2). Returns
    True on success. The per-node ``geometry_node_bake_single`` path is left
    for E7 where individual bake nodes get their own targeted operators.
    """
    if not objects:
        return False
    objects = list(objects)
    override = {"selected_objects": objects,
                "active_object": objects[0],
                "object": objects[0]}
    try:
        with bpy.context.temp_override(**override):
            bpy.ops.object.simulation_nodes_cache_bake(selected=True)
        return True
    except Exception:  # noqa: BLE001 -- surfaced to the user by the operator
        return False


def free_geometry_nodes(objects) -> bool:
    """Free (delete) geometry-node simulation caches for ``objects``.

    Uses ``simulation_nodes_cache_delete`` (5.2; the operator is *_delete*, not
    *_free* — verified via dev/probe). Returns True on success.
    """
    if not objects:
        return False
    objects = list(objects)
    override = {"selected_objects": objects,
                "active_object": objects[0],
                "object": objects[0]}
    try:
        with bpy.context.temp_override(**override):
            bpy.ops.object.simulation_nodes_cache_delete(selected=True)
        return True
    except Exception:  # noqa: BLE001 -- surfaced to the user by the operator
        return False
