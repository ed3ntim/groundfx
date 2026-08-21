# SPDX-License-Identifier: GPL-3.0-or-later
"""B2 acceptance: the deposited berm is smooth, and the solver invents no mass.

Two failure modes are pinned here, both found by measuring a dragged collider's
height field rather than by looking at it:

* **The checkerboard comb.** A transport step that averages only over the four
  neighbours is odd-even decoupled: the pile hops between the two checkerboard
  sublattices every iteration, so after N steps only cells of one parity have
  received anything and the berm comes out as a comb of one-cell teeth. The
  test projects the field's one-cell residual onto that mode. Measured on the
  transport this replaced: 0.174 mm. Measured now: under 0.005 mm.
* **Invented mass.** Carving only ever moves material (and compaction removes
  some), so the total can never grow. A transport step that clamps a negative
  intermediate to zero silently creates material, which compounds frame over
  frame; this catches it while it is still small.

Only the checkerboard mode is asserted, not the two axis-aligned combs: with an
odd number of grid columns an alternating sum over a smooth field does not
cancel, so those projections read ~0.2 mm even on a visibly perfect ramp. The
remaining known artefact — one lump per frame when a collider crosses several
cells per frame, whose ripple period equals the per-frame travel — is temporal
undersampling and waits on substeps (E3-S5); no spatial metric here can tell it
apart from a legitimate berm.
"""
from __future__ import annotations

import bpy

import harness

from groundfx.core.constants import ATTR_HEIGHT, ELEM_SAND


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _height_grid(obj, deps):
    """Return (n, h[row][col]) of the evaluated domain's material height."""
    ev = obj.evaluated_get(deps)
    me = ev.data
    hattr = me.attributes.get(ATTR_HEIGHT)
    if hattr is None:
        return 0, []
    xs = sorted({round(v.co.x, 5) for v in me.vertices})
    ys = sorted({round(v.co.y, 5) for v in me.vertices})
    n = len(xs)
    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: i for i, y in enumerate(ys)}
    h = [[0.0] * n for _ in range(n)]
    for k, v in enumerate(me.vertices):
        h[yi[round(v.co.y, 5)]][xi[round(v.co.x, 5)]] = hattr.data[k].value
    return n, h


def _checkerboard_amplitude(n, h):
    """Amplitude of the one-cell checkerboard mode, in metres.

    ``r = h - mean(4 neighbours)`` vanishes on any smooth surface (a ramp, a
    dome) and is maximal on a one-cell comb; projecting it onto ``(-1)^(i+j)``
    keeps the checkerboard and averages everything else away.
    """
    total = 0.0
    count = 0
    for i in range(1, n - 1):
        for j in range(1, n - 1):
            nb = (h[i - 1][j] + h[i + 1][j] + h[i][j - 1] + h[i][j + 1]) * 0.25
            r = h[i][j] - nb
            total += r if (i + j) % 2 == 0 else -r
            count += 1
    return abs(total) / count if count else 0.0


def _total_material(n, h):
    return sum(sum(row) for row in h)


def _new_domain_and_cube(scene):
    from groundfx.ops.op_add import create_domain

    scene.frame_start = 1
    scene.frame_end = 60
    scene.frame_set(1)
    obj = create_domain(bpy.context, ELEM_SAND)
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(-0.6, 0.0, 2.0))
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)
    scene.frame_set(1)
    return obj, cube


def test_berm_has_no_checkerboard_comb():
    """A dragged collider leaves a smooth berm, not a comb of one-cell teeth."""
    _reset()
    scene = bpy.context.scene
    obj, cube = _new_domain_and_cube(scene)

    frames = 20
    for k in range(frames):
        cube.location = (-0.6 + 0.045 * k, 0.0, 0.22)
        scene.frame_set(2 + k)
    # Lift clear and let the field come to rest: the berm the collider leaves
    # behind is what the user actually looks at.
    cube.location = (0.0, 0.0, 3.0)
    for f in range(2 + frames, 2 + frames + 12):
        scene.frame_set(f)

    deps = bpy.context.evaluated_depsgraph_get()
    n, h = _height_grid(obj, deps)
    harness.check("height grid read", n > 0)
    if n:
        amp = _checkerboard_amplitude(n, h)
        limit = 2e-5  # 0.02 mm: 9x under the broken value, 5x over the current
        harness.check("no checkerboard comb", amp < limit,
                      f"checkerboard {amp * 1000:.4f} mm, limit "
                      f"{limit * 1000:.3f} mm")
    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def test_carving_never_creates_material():
    """Total material may fall (compaction) but must never rise."""
    _reset()
    scene = bpy.context.scene
    obj, cube = _new_domain_and_cube(scene)
    deps = bpy.context.evaluated_depsgraph_get()
    n, h0 = _height_grid(obj, deps)
    start = _total_material(n, h0)

    worst = 0.0
    for k in range(20):
        cube.location = (-0.6 + 0.045 * k, 0.0, 0.22)
        scene.frame_set(2 + k)
        deps = bpy.context.evaluated_depsgraph_get()
        n, h = _height_grid(obj, deps)
        worst = max(worst, _total_material(n, h) - start)

    # Tolerance covers float accumulation over ~16k cells, not real growth: the
    # clamp this guards against grew the total by orders of magnitude more.
    tol = 1e-3 * start
    harness.check("no material invented", worst <= tol,
                  f"total grew by {worst:.5f} m (start {start:.3f} m, "
                  f"tolerance {tol:.5f} m)")
    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)
