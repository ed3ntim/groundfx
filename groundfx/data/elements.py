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
                 "stickiness", "yield_m", "compact_deg", "displace")

    def __init__(self, key, label, repose_deg, cohesion, flow_rate, density,
                 wetness, compaction, recovery, bow_wave, stickiness=0.0,
                 yield_m=0.0, compact_deg=12.0, displace=0.95):
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
        self.stickiness = stickiness      # clings to colliders 0..1 (coat)
        self.yield_m = yield_m            # Bingham yield as a length (mud)
        self.compact_deg = compact_deg    # packed material holds this steeper
        self.displace = displace          # share pushed aside, rest compacts

    @property
    def compact_rad(self) -> float:
        return math.radians(self.compact_deg)

    @property
    def repose_rad(self) -> float:
        return math.radians(self.repose_deg)


DEFAULTS = {
    ELEM_SAND: ElementDefaults(
        ELEM_SAND, "Sand", repose_deg=34.0, cohesion=0.02, flow_rate=1.0,
        density=1600.0, wetness=0.0, compaction=0.05, recovery=0.1,
        bow_wave=0.7, stickiness=0.15, yield_m=0.0, compact_deg=5.0,
        displace=0.95),
    ELEM_SNOW: ElementDefaults(
        ELEM_SNOW, "Snow", repose_deg=40.0, cohesion=0.25, flow_rate=0.6,
        density=150.0, wetness=0.1, compaction=0.65, recovery=0.0,
        bow_wave=0.5, stickiness=0.6, yield_m=0.0, compact_deg=35.0,
        displace=0.35),
    ELEM_MUD: ElementDefaults(
        ELEM_MUD, "Mud", repose_deg=10.0, cohesion=0.0, flow_rate=0.7,
        density=1750.0, wetness=0.6, compaction=0.0, recovery=0.0,
        bow_wave=0.5, stickiness=0.8, yield_m=0.003, compact_deg=4.0,
        displace=1.0),
}


def defaults(key: str) -> ElementDefaults:
    return DEFAULTS[key]


def push_physics(md, ed: ElementDefaults, *, cohesion=None, tag=True) -> None:
    """Push one element's full physics set into a solver modifier."""
    from ..core import modifier_io
    from ..core.nodegroups import ng_ground_sim as gsim

    set_ = modifier_io.set_input
    set_(md, gsim.IN_REPOSE, ed.repose_rad, tag=False)
    set_(md, gsim.IN_COHESION, ed.cohesion if cohesion is None else cohesion,
         tag=False)
    set_(md, gsim.IN_YIELD, ed.yield_m, tag=False)
    set_(md, gsim.IN_COMPACT_ANGLE, ed.compact_rad, tag=False)
    set_(md, gsim.IN_DISPLACE_RATIO, ed.displace, tag=False)
    set_(md, gsim.IN_FLOW, ed.flow_rate, tag=False)
    set_(md, gsim.IN_BOW_WAVE, ed.bow_wave, tag=False)
    set_(md, gsim.IN_RECOVERY, ed.recovery, tag=False)
    set_(md, gsim.IN_STICKINESS, ed.stickiness, tag=tag)
