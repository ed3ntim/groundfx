# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-element default physics, straight from PLAN.md section 3.2.

These are the *element* baselines (a sensible middle preset for each). The
richer named presets in E5 layer on top of these. Kept as data so operators,
UI and tests share one source.

``angle_of_repose`` is in radians internally but authored in degrees here for
readability; ``repose_deg`` is the authored value, ``repose_rad`` the derived
one the solver consumes.
"""
from __future__ import annotations

import math

from ..core.constants import ELEM_SAND, ELEM_SNOW, ELEM_MUD


class ElementDefaults:
    __slots__ = ("key", "label", "repose_deg", "cohesion", "flow_rate",
                 "density", "wetness", "compaction", "recovery", "bow_wave",
                 "stickiness")

    def __init__(self, key, label, repose_deg, cohesion, flow_rate, density,
                 wetness, compaction, recovery, bow_wave, stickiness=0.0):
        self.key = key
        self.label = label
        self.repose_deg = repose_deg      # angle of repose, degrees
        self.cohesion = cohesion          # Bingham yield threshold 0..1
        self.flow_rate = flow_rate        # relaxation damping 0..1
        self.density = density            # kg/m^3 (informational + spray mass)
        self.wetness = wetness            # 0..1 baseline moisture
        self.compaction = compaction      # how readily it packs 0..1
        self.recovery = recovery          # how fast compaction relaxes 0..1
        self.bow_wave = bow_wave          # directional heaping ahead 0..1
        self.stickiness = stickiness      # static-friction margin 0..1 (P1)

    @property
    def repose_rad(self) -> float:
        return math.radians(self.repose_deg)


DEFAULTS = {
    ELEM_SAND: ElementDefaults(
        ELEM_SAND, "Sand", repose_deg=34.0, cohesion=0.02, flow_rate=0.8,
        density=1600.0, wetness=0.0, compaction=0.3, recovery=0.1,
        bow_wave=0.7, stickiness=0.05),
    ELEM_SNOW: ElementDefaults(
        ELEM_SNOW, "Snow", repose_deg=40.0, cohesion=0.10, flow_rate=0.5,
        density=80.0, wetness=0.1, compaction=0.6, recovery=0.02,
        bow_wave=0.6, stickiness=0.25),
    ELEM_MUD: ElementDefaults(
        ELEM_MUD, "Mud", repose_deg=18.0, cohesion=0.45, flow_rate=0.3,
        density=1750.0, wetness=0.6, compaction=0.2, recovery=0.05,
        bow_wave=0.45, stickiness=0.4),
}


def defaults(key: str) -> ElementDefaults:
    return DEFAULTS[key]
