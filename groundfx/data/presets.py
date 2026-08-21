# SPDX-License-Identifier: GPL-3.0-or-later
"""Named presets (E5-S2): ready-made looks layered on the element baselines.

Each preset is a full physics set for one element, authored as data so the
operator, UI and tests share one source. Externalising these to JSON files plus
user-saved presets (E5-T4/T9) is a later pass; the values and the apply path are
identical either way.
"""
from __future__ import annotations

import math

from ..core.constants import ELEM_SAND, ELEM_SNOW, ELEM_MUD


class Preset:
    __slots__ = ("key", "label", "element", "repose_deg", "cohesion",
                 "flow_rate", "bow_wave", "material_height", "stickiness",
                 "recovery")

    def __init__(self, key, label, element, repose_deg, cohesion, flow_rate,
                 bow_wave, material_height, stickiness, recovery):
        self.key = key
        self.label = label
        self.element = element
        self.repose_deg = repose_deg
        self.cohesion = cohesion
        self.flow_rate = flow_rate
        self.bow_wave = bow_wave
        self.material_height = material_height
        self.stickiness = stickiness      # static-friction hold (P1a)
        self.recovery = recovery          # how fast tracks heal (E3-S4)

    @property
    def repose_rad(self) -> float:
        return math.radians(self.repose_deg)


def _p(*args):
    return Preset(*args)


# key, label, element, repose_deg, cohesion, flow, bow_wave, material_height,
# stickiness, recovery
_PRESETS = (
    # Sand — dry sands flow freely and heal; wet/beach hold their shape
    _p("FINE_DRY_SAND", "Fine Dry Sand", ELEM_SAND, 34.0, 0.01, 0.90, 0.75, 0.06, 0.03, 0.14),
    _p("COARSE_SAND", "Coarse Sand", ELEM_SAND, 39.0, 0.03, 0.70, 0.65, 0.08, 0.07, 0.10),
    _p("WET_SAND", "Wet Sand", ELEM_SAND, 45.0, 0.20, 0.40, 0.50, 0.08, 0.28, 0.04),
    _p("BEACH_SAND", "Beach Sand", ELEM_SAND, 32.0, 0.05, 0.80, 0.70, 0.10, 0.10, 0.08),
    # Snow — powder heals slowly, packed/wet snow keeps its imprint
    _p("DRY_POWDER", "Dry Powder", ELEM_SNOW, 38.0, 0.04, 0.70, 0.55, 0.12, 0.12, 0.03),
    _p("PACKED_SNOW", "Packed Snow", ELEM_SNOW, 45.0, 0.30, 0.30, 0.40, 0.08, 0.42, 0.01),
    _p("HEAVY_WET_SNOW", "Heavy Wet Snow", ELEM_SNOW, 40.0, 0.45, 0.25, 0.35, 0.10, 0.48, 0.02),
    _p("FRESH_FLUFF", "Fresh Fluff", ELEM_SNOW, 35.0, 0.02, 0.85, 0.60, 0.15, 0.06, 0.04),
    # Mud — thick/clay hold cracks; thin/slush flow and heal
    _p("THICK_MUD", "Thick Mud", ELEM_MUD, 22.0, 0.55, 0.20, 0.45, 0.08, 0.45, 0.05),
    _p("THIN_MUD", "Thin Mud", ELEM_MUD, 12.0, 0.30, 0.50, 0.50, 0.06, 0.20, 0.08),
    _p("WET_CLAY", "Wet Clay", ELEM_MUD, 25.0, 0.65, 0.15, 0.40, 0.08, 0.55, 0.04),
    _p("SLUSH", "Slush", ELEM_MUD, 10.0, 0.25, 0.60, 0.50, 0.07, 0.15, 0.10),
)

PRESETS = {p.key: p for p in _PRESETS}


def all_presets():
    """Presets in authored order (grouped by element)."""
    return _PRESETS


def get(key: str) -> Preset:
    return PRESETS[key]
