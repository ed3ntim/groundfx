# SPDX-License-Identifier: GPL-3.0-or-later
"""Benchmark the solver: real ms/frame instead of the static estimate (E6-S3).

The quality panel shows a *guess* (``QualityProfile.target_ms``). This measures
the truth: it steps the scene a few frames, forcing the domain's modifier to
evaluate each time, and reports the median wall-clock cost. The median (not the
mean) shrugs off the odd frame that stalls on something unrelated.

The measurement is stored on the domain (``groundfx.measured_ms``) so the panel
can show it, and compared against the profile's budget so a setup that blows
past it earns a warning (E6-T9/T11).
"""
from __future__ import annotations

import time

import bpy

from ..core.constants import OP_PREFIX, MODIFIER_NAME
from ..data import quality as qmod
from ..utils import log


def _active_domain(context):
    obj = context.active_object
    if obj is not None and getattr(obj.groundfx, "is_domain", False):
        return obj
    return None


def measure_ms(domain, context, frames: int = 8) -> float:
    """Median ms to evaluate the domain over ``frames`` successive frames.

    Times ``frame_set`` plus a forced read of the evaluated mesh (which is what
    pulls the geometry-node modifier through), then restores the frame.
    """
    scene = context.scene
    start = scene.frame_current
    samples = []
    try:
        for i in range(1, frames + 1):
            t0 = time.perf_counter()
            scene.frame_set(start + i)
            ev = domain.evaluated_get(context.evaluated_depsgraph_get())
            # Touch the data so the evaluation can't be skipped/deferred.
            _ = len(ev.data.vertices)
            samples.append((time.perf_counter() - t0) * 1000.0)
    finally:
        scene.frame_set(start)
    samples.sort()
    return samples[len(samples) // 2] if samples else 0.0


class GFX_OT_benchmark(bpy.types.Operator):
    """Measure the actual solver cost of the active domain (ms/frame)"""

    bl_idname = f"{OP_PREFIX}.benchmark"
    bl_label = "Measure Performance"
    bl_options = {"REGISTER"}

    frames: bpy.props.IntProperty(name="Frames", default=8, min=2, max=120)

    @classmethod
    def poll(cls, context):
        dom = _active_domain(context)
        return dom is not None and dom.modifiers.get(MODIFIER_NAME) is not None

    def execute(self, context):
        domain = _active_domain(context)
        ms = measure_ms(domain, context, self.frames)
        domain.groundfx.measured_ms = ms

        prof = qmod.profile(domain.groundfx.quality)
        budget_hi = prof.target_ms[1]
        log.info("benchmark %s: %.2f ms/frame (budget <= %.0f)",
                 domain.name, ms, budget_hi)
        if ms > 2.0 * budget_hi:
            self.report({"WARNING"},
                        f"{ms:.1f} ms/frame — well over the "
                        f"~{budget_hi:.0f} ms budget for {prof.label}")
        else:
            self.report({"INFO"}, f"{ms:.1f} ms/frame ({prof.label})")
        return {"FINISHED"}


classes = (
    GFX_OT_benchmark,
)
