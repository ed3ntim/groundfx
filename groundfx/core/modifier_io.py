# SPDX-License-Identifier: GPL-3.0-or-later
"""Read/write geometry-node modifier inputs by socket *name*.

Blender 5.2 replaced the old ``modifier["Socket_N"] = value`` IDProperty path.
Inputs now live under ``modifier.properties.inputs.<identifier>`` as small
sub-structs, each exposing ``.value`` (and ``.type`` VALUE/ATTRIBUTE plus
``.attribute_name`` for fields). Writing a value requires tagging the owning
object for a depsgraph re-evaluation.

We resolve socket *name* -> identifier from the group interface (cached per
tree), so operators and update callbacks never hard-code "Socket_3".
Verified against 5.2 — see docs/API_NOTES.md.
"""
from __future__ import annotations

from ..utils import compat, log

# Cache: node-group name -> {socket name: identifier}.
_cache: dict[str, dict[str, str]] = {}


def _mapping(node_group):
    key = node_group.name
    mapping = _cache.get(key)
    if mapping is None or not _mapping_valid(node_group, mapping):
        mapping = compat.socket_identifier_map(node_group)
        _cache[key] = mapping
    return mapping


def _mapping_valid(node_group, mapping) -> bool:
    names = {i.name for i in compat.iter_input_sockets(node_group)}
    return names == set(mapping.keys())


def _input_struct(modifier, socket_name: str):
    """Return the per-input sub-struct for ``socket_name``, or None."""
    ng = modifier.node_group
    if ng is None:
        return None
    ident = _mapping(ng).get(socket_name)
    if ident is None:
        log.warning("socket %r not found on group %s", socket_name, ng.name)
        return None
    return getattr(modifier.properties.inputs, ident, None)


def set_input(modifier, socket_name: str, value, *, tag: bool = True) -> bool:
    """Set a modifier input by interface socket name. Returns success.

    ``tag`` re-tags the owning object so the change takes effect on the next
    depsgraph evaluation; pass False when setting many inputs in a batch and
    tagging once afterwards.
    """
    sock = _input_struct(modifier, socket_name)
    if sock is None:
        return False
    try:
        sock.value = value
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to set %s=%r: %s", socket_name, value, exc)
        return False
    if tag and modifier.id_data is not None:
        modifier.id_data.update_tag()
    return True


def set_attribute_input(modifier, socket_name: str, attribute_name: str,
                        *, tag: bool = True) -> bool:
    """Drive a value socket from a named attribute instead of a constant."""
    sock = _input_struct(modifier, socket_name)
    if sock is None or not hasattr(sock, "attribute_name"):
        return False
    sock.type = "ATTRIBUTE"
    sock.attribute_name = attribute_name
    if tag and modifier.id_data is not None:
        modifier.id_data.update_tag()
    return True


def get_input(modifier, socket_name: str, default=None):
    sock = _input_struct(modifier, socket_name)
    if sock is None:
        return default
    return getattr(sock, "value", default)


def invalidate(node_group_name: str | None = None) -> None:
    """Drop cached mappings (call after rebuilding a group)."""
    if node_group_name is None:
        _cache.clear()
    else:
        _cache.pop(node_group_name, None)
