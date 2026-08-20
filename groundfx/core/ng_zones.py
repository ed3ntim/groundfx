# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers for Simulation and Repeat zones.

Both are paired input/output nodes in Blender 5.x: you create the two nodes,
pair them, then declare the values that persist across the boundary (state
items for simulation, repeat items for loops). Getting the pairing and item
order right by hand is error-prone, so it lives here.

Verified against Blender 5.2 — see docs/API_NOTES.md:
 * state items live on the *output* node (``sim_out.state_items``)
 * a Geometry item is created automatically with the zone
"""
from __future__ import annotations

import bpy


class Zone:
    """A paired input/output zone with helpers to add state/repeat items.

    ``input`` and ``output`` are the two zone nodes. ``item_socket`` maps an
    item name to its (input_socket, output_socket) pair so callers can wire
    values in and read them out by name.
    """

    def __init__(self, input_node, output_node, items_attr: str):
        self.input = input_node
        self.output = output_node
        self._items_attr = items_attr  # "state_items" or "repeat_items"

    @property
    def items(self):
        return getattr(self.output, self._items_attr)

    def add_item(self, socket_type: str, name: str):
        """Add a state/repeat item; both zone nodes gain a matching socket."""
        self.items.new(socket_type, name)

    def in_socket(self, name):
        """Input socket on the zone *input* node (where you feed a value in)."""
        return self.input.inputs[name]

    def out_socket(self, name):
        """Output socket on the zone *output* node (where you read it out)."""
        return self.output.outputs[name]


def make_simulation_zone(builder, state_items) -> Zone:
    """Create a paired Simulation zone.

    ``state_items`` is an iterable of (socket_type, name). A Geometry item is
    added automatically by Blender, so callers pass only the extra attributes
    they need to persist (heights, carve buffers, ...).
    """
    sim_in = builder.add("GeometryNodeSimulationInput")
    sim_out = builder.add("GeometryNodeSimulationOutput")
    sim_in.pair_with_output(sim_out)
    zone = Zone(sim_in, sim_out, "state_items")
    for socket_type, name in state_items:
        zone.add_item(socket_type, name)
    return zone


def make_repeat_zone(builder, repeat_items) -> Zone:
    """Create a paired Repeat zone.

    ``repeat_items`` is an iterable of (socket_type, name). Unlike simulation
    zones, repeat zones start empty, so pass every value the loop carries
    (typically at least a Geometry item).
    """
    rep_in = builder.add("GeometryNodeRepeatInput")
    rep_out = builder.add("GeometryNodeRepeatOutput")
    rep_in.pair_with_output(rep_out)
    zone = Zone(rep_in, rep_out, "repeat_items")
    for socket_type, name in repeat_items:
        zone.add_item(socket_type, name)
    return zone
