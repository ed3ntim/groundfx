# SPDX-License-Identifier: GPL-3.0-or-later
"""Quality levels as data.

Each level trades performance for fidelity along the axes documented in
PLAN.md section 4. Keeping them as a plain table (not code) means the UI, the
operators and the tests all read the same numbers, and tuning is a one-line
edit.

``resolution`` is the simulation grid subdivisions per side; the vertex count
is (resolution+1)^2. ``display_subdiv`` and ``detail_displace`` belong to the
post-simulation display stage, never the solver.
"""
from __future__ import annotations

from ..core.constants import (
    QUALITY_LOW, QUALITY_MEDIUM, QUALITY_HIGH, QUALITY_ULTRA,
)


class QualityProfile:
    __slots__ = ("key", "label", "resolution", "relax_iterations",
                 "substeps", "spray_cap", "display_subdiv", "detail_displace",
                 "target_ms")

    def __init__(self, key, label, resolution, relax_iterations, substeps,
                 spray_cap, display_subdiv, detail_displace, target_ms):
        self.key = key
        self.label = label
        self.resolution = resolution
        self.relax_iterations = relax_iterations
        self.substeps = substeps
        self.spray_cap = spray_cap
        self.display_subdiv = display_subdiv
        self.detail_displace = detail_displace
        self.target_ms = target_ms  # (low, high) budget estimate per frame

    @property
    def vertex_count(self) -> int:
        return (self.resolution + 1) ** 2


PROFILES = {
    QUALITY_LOW: QualityProfile(
        QUALITY_LOW, "Low", resolution=64, relax_iterations=4, substeps=1,
        spray_cap=0, display_subdiv=0, detail_displace=False, target_ms=(0.5, 2.0)),
    QUALITY_MEDIUM: QualityProfile(
        QUALITY_MEDIUM, "Medium", resolution=128, relax_iterations=8, substeps=2,
        spray_cap=5000, display_subdiv=1, detail_displace=False, target_ms=(3.0, 6.0)),
    QUALITY_HIGH: QualityProfile(
        QUALITY_HIGH, "High", resolution=256, relax_iterations=14, substeps=3,
        spray_cap=20000, display_subdiv=1, detail_displace=True, target_ms=(10.0, 20.0)),
    QUALITY_ULTRA: QualityProfile(
        QUALITY_ULTRA, "Ultra", resolution=512, relax_iterations=24, substeps=4,
        spray_cap=80000, display_subdiv=2, detail_displace=True, target_ms=(40.0, 120.0)),
}


def profile(key: str) -> QualityProfile:
    return PROFILES[key]


def cell_size(domain_size: float, quality_key: str) -> float:
    """Effective cell size in metres for a square domain at a quality level."""
    return domain_size / profile(quality_key).resolution


def traffic_light(domain_size: float, quality_key: str) -> str:
    """Green/amber/red hint on whether the cell size resolves close-up detail.

    Tuned for the close-up scale (2 m default): under ~2 cm is comfortable for
    footprints and coarse tread, over ~5 cm is too coarse for the intended use.
    """
    cs = cell_size(domain_size, quality_key)
    if cs <= 0.02:
        return "GREEN"
    if cs <= 0.05:
        return "AMBER"
    return "RED"
