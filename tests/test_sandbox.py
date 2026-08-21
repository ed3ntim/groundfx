# SPDX-License-Identifier: GPL-3.0-or-later
"""E11-S3: the one-click Sandbox produces a working, animated demo."""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ATTR_HEIGHT, MODIFIER_NAME


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _min_h(obj, deps, cx, cy, r=0.25):
    ev = obj.evaluated_get(deps)
    ha = ev.data.attributes.get(ATTR_HEIGHT)
    if ha is None:
        return None
    r2 = r * r
    vals = [h.value for v, h in zip(ev.data.vertices, ha.data)
            if (v.co.x - cx) ** 2 + (v.co.y - cy) ** 2 <= r2]
    return min(vals) if vals else None


def test_sandbox_creates_animated_collider_that_imprints():
    _reset()
    from groundfx.ops.op_add import create_sandbox

    domain, ball = create_sandbox(bpy.context)
    harness.check("domain has the solver modifier",
                  domain.modifiers.get(MODIFIER_NAME) is not None)
    harness.check("collider is in the domain's collection",
                  ball.name in domain.groundfx.collider_collection.objects)
    harness.check("collider is animated",
                  ball.animation_data is not None
                  and ball.animation_data.action is not None)

    scene = bpy.context.scene
    scene.frame_set(1)
    deps = bpy.context.evaluated_depsgraph_get()
    base = _min_h(domain, deps, domain.location.x - 0.5, domain.location.y)

    # Play a few frames: the drop should leave an imprint.
    for f in range(2, 20):
        scene.frame_set(f)
    deps = bpy.context.evaluated_depsgraph_get()
    after = _min_h(domain, deps, domain.location.x - 0.5, domain.location.y)
    harness.check("sandbox leaves an imprint when played",
                  base is not None and after is not None and after < base - 0.01,
                  f"h {base} -> {after}")
    for o in (ball, domain):
        bpy.data.objects.remove(o, do_unlink=True)
