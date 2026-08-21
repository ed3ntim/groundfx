# SPDX-License-Identifier: GPL-3.0-or-later
"""Live Sculpt — draw a trace by dragging a collider, without pressing Play.

The solver keeps its state in a Simulation Zone, which only advances when the
scene frame does. So on a still frame, dragging a collider just re-imprints the
current footprint against the *previous* frame's cached field — you get a moving
dent, never an accumulating trail.

Live Sculpt closes that gap with the one mechanism the solver already trusts: a
frame step. A modal operator runs a light timer while the toggle is on; whenever
a collider of a live domain has actually moved, it advances the simulation by a
single frame (extending the frame range so it never stalls). That is *exactly*
an animation step, just triggered by the drag instead of by playback — so the
trace it leaves is identical to the baked one, and the whole tuned solver
(swept carve, deposit, relaxation) is reused rather than reimplemented in Python.

The trade-off is deliberate and documented: the playhead moves forward as you
sculpt. Scrubbing back to the start frame resets the field, which doubles as a
clear. The stepping logic lives in ``LiveStepper`` so it can be driven straight
from a headless test, without a window or a running modal.

Verified against Blender 5.2.
"""
from __future__ import annotations

import bpy

from ..core.constants import OP_PREFIX
from ..utils import log

# Matrix change above this (per element) counts as the collider having moved.
_MOVE_EPS = 1e-6


def _live_domains(context):
    """Yield domains that should react to live dragging."""
    for obj in context.scene.objects:
        st = getattr(obj, "groundfx", None)
        if st is None or not st.is_domain:
            continue
        if st.collider_collection is None:
            continue
        yield obj


def _matrix_tuple(obj):
    m = obj.matrix_world
    return tuple(m[i][j] for i in range(4) for j in range(4))


def _changed(a, b):
    return any(abs(x - y) > _MOVE_EPS for x, y in zip(a, b))


class LiveStepper:
    """Tracks collider poses and steps the sim one frame when they move.

    Kept free of any window/event state so a test can call ``snapshot`` then
    ``advance_if_moved`` directly and assert the trace grew.
    """

    def __init__(self):
        self._last: dict[str, tuple] = {}

    def snapshot(self, context) -> None:
        """Record the current pose of every live collider as the baseline."""
        self._last.clear()
        for dom in _live_domains(context):
            for o in dom.groundfx.collider_collection.objects:
                self._last[o.name] = _matrix_tuple(o)

    def _any_moved(self, context) -> bool:
        moved = False
        for dom in _live_domains(context):
            for o in dom.groundfx.collider_collection.objects:
                now = _matrix_tuple(o)
                prev = self._last.get(o.name)
                self._last[o.name] = now
                # A collider first seen this tick sets a baseline, no step: a
                # newly marked collider must not carve a phantom trench.
                if prev is not None and _changed(prev, now):
                    moved = True
        return moved

    def advance_if_moved(self, context) -> bool:
        """Step the simulation one frame iff a collider moved. Returns stepped?"""
        if not self._any_moved(context):
            return False
        scene = context.scene
        target = scene.frame_current + 1
        # Keep the cache range open ahead of us, or the sim can't step on.
        if target > scene.frame_end:
            scene.frame_end = target
        scene.frame_set(target)
        return True


class GFX_OT_live_sculpt(bpy.types.Operator):
    """Toggle Live Sculpt: dragging a collider draws the trace without Play.

    Advances the simulation as you drag (the playhead moves with you). Scrub to
    the start frame to reset"""

    bl_idname = f"{OP_PREFIX}.live_sculpt"
    bl_label = "Live Sculpt"
    bl_options = {"REGISTER"}

    _timer = None
    _stepper: LiveStepper | None = None

    def invoke(self, context, event):
        scene = context.scene
        # A second click while active is the "off" switch: clear the flag and
        # the running modal notices and tears itself down.
        if scene.gfx_live_active:
            scene.gfx_live_active = False
            return {"FINISHED"}

        wm = context.window_manager
        if context.window is None:  # no window (headless): just flip the flag
            scene.gfx_live_active = True
            return {"FINISHED"}

        self._stepper = LiveStepper()
        self._stepper.snapshot(context)
        scene.gfx_live_active = True
        self._timer = wm.event_timer_add(1.0 / 30.0, window=context.window)
        wm.modal_handler_add(self)
        log.info("Live Sculpt on")
        return {"RUNNING_MODAL"}

    def execute(self, context):
        # Menu/keymap invocation without an event: toggle the flag.
        context.scene.gfx_live_active = not context.scene.gfx_live_active
        return {"FINISHED"}

    def modal(self, context, event):
        if not context.scene.gfx_live_active:
            self._finish(context)
            return {"FINISHED"}
        if event.type == "TIMER" and self._stepper is not None:
            try:
                self._stepper.advance_if_moved(context)
            except Exception:  # noqa: BLE001 -- never let a tick kill the modal
                log.exception("Live Sculpt step failed")
        # Pass events through so the user can still grab and move the collider.
        return {"PASS_THROUGH"}

    def _finish(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        self._stepper = None
        log.info("Live Sculpt off")


classes = (
    GFX_OT_live_sculpt,
)
