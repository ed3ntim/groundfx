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
                 "flow_rate", "bow_wave", "material_height")

    def __init__(self, key, label, element, repose_deg, cohesion, flow_rate,
                 bow_wave, material_height):
        self.key = key
        self.label = label
        self.element = element
        self.repose_deg = repose_deg
        self.cohesion = cohesion
        self.flow_rate = flow_rate
        self.bow_wave = bow_wave
        self.material_height = material_height

    @property
    def repose_rad(self) -> float:
        return math.radians(self.repose_deg)


def _p(*args):
    return Preset(*args)


# key, label, element, repose_deg, cohesion, flow, bow_wave, material_height
_PRESETS = (
    # Sand
    _p("FINE_DRY_SAND", "Fine Dry Sand", ELEM_SAND, 34.0, 0.01, 0.90, 0.75, 0.06),
    _p("COARSE_SAND", "Coarse Sand", ELEM_SAND, 39.0, 0.03, 0.70, 0.65, 0.08),
    _p("WET_SAND", "Wet Sand", ELEM_SAND, 45.0, 0.20, 0.40, 0.50, 0.08),
    _p("BEACH_SAND", "Beach Sand", ELEM_SAND, 32.0, 0.05, 0.80, 0.70, 0.10),
    # Snow
    _p("DRY_POWDER", "Dry Powder", ELEM_SNOW, 38.0, 0.04, 0.70, 0.55, 0.12),
    _p("PACKED_SNOW", "Packed Snow", ELEM_SNOW, 45.0, 0.30, 0.30, 0.40, 0.08),
    _p("HEAVY_WET_SNOW", "Heavy Wet Snow", ELEM_SNOW, 40.0, 0.45, 0.25, 0.35, 0.10),
    _p("FRESH_FLUFF", "Fresh Fluff", ELEM_SNOW, 35.0, 0.02, 0.85, 0.60, 0.15),
    # Mud
    _p("THICK_MUD", "Thick Mud", ELEM_MUD, 22.0, 0.55, 0.20, 0.45, 0.08),
    _p("THIN_MUD", "Thin Mud", ELEM_MUD, 12.0, 0.30, 0.50, 0.50, 0.06),
    _p("WET_CLAY", "Wet Clay", ELEM_MUD, 25.0, 0.65, 0.15, 0.40, 0.08),
    _p("SLUSH", "Slush", ELEM_MUD, 10.0, 0.25, 0.60, 0.50, 0.07),
)

PRESETS = {p.key: p for p in _PRESETS}


def all_presets():
    """Presets in authored order (grouped by element)."""
    return _PRESETS


def get(key: str) -> Preset:
    return PRESETS[key]
