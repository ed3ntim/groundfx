# SPDX-License-Identifier: GPL-3.0-or-later
"""E6-S3: the benchmark measures a real, positive ms/frame and records it."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ELEM_SAND


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def test_benchmark_measures_and_records():
    _reset()
    from groundfx.ops.op_add import create_domain
    from groundfx.ops.op_bench import measure_ms

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 40
    scene.frame_set(1)
    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.context.view_layer.objects.active = obj

    ms = measure_ms(obj, bpy.context, frames=5)
    harness.check("benchmark returns a positive time", ms > 0.0, f"{ms}")
    # frame restored
    harness.check("frame restored after benchmark", scene.frame_current == 1,
                  f"{scene.frame_current}")

    bpy.ops.groundfx.benchmark(frames=5)
    harness.check("result written to the domain",
                  obj.groundfx.measured_ms > 0.0,
                  f"{obj.groundfx.measured_ms}")
    bpy.data.objects.remove(obj, do_unlink=True)
