# SPDX-License-Identifier: GPL-3.0-or-later
"""Node-group lifecycle: build once, reuse, rebuild on version change.

Every GroundFX node group is stamped with ``NODEGROUP_VERSION`` in a custom
property. ``ensure_node_group`` returns an up-to-date group, rebuilding it only
when the stored stamp is missing or stale. This is what lets an addon update
migrate a user's old scene: the modifier keeps pointing at the same-named
group, which gets rebuilt against the running Blender version.

Parameter migration (carrying old input values across a rebuild by socket
*name*, not index) is added in E1-S2 once real solver groups exist.
"""
from __future__ import annotations

import bpy

from .constants import NODEGROUP_VERSION, PROP_NG_VERSION
from ..utils import log


def _stamp(tree) -> None:
    tree[PROP_NG_VERSION] = NODEGROUP_VERSION


def _version_of(tree) -> int | None:
    return tree.get(PROP_NG_VERSION)


def is_current(tree) -> bool:
    return _version_of(tree) == NODEGROUP_VERSION


def ensure_node_group(name: str, build_fn) -> bpy.types.NodeTree:
    """Return a current node group named ``name``, building it if needed.

    ``build_fn(name) -> NodeTree`` creates the group from scratch. It is only
    called when no group with that name exists yet, or the existing one carries
    an out-of-date version stamp.
    """
    existing = bpy.data.node_groups.get(name)
    if existing is not None and is_current(existing):
        return existing

    if existing is not None:
        log.info("rebuilding node group %s (stamp %s -> %s)",
                 name, _version_of(existing), NODEGROUP_VERSION)

    tree = build_fn(name)
    _stamp(tree)
    return tree
