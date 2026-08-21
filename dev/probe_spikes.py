# SPDX-License-Identifier: GPL-3.0-or-later
"""Probe for B2: measure the high-frequency (spiky) content of the height field.

Drags a cube through a sand domain and reports, for the resulting height field,
the worst one-cell residual ``r = h - mean(4 neighbours)``, how many cells carry
a visible spike, and how many of those sit on the collider footprint — plus an
ASCII cross-section so the trench shape is readable in a log.

Env overrides (all optional): GFX_BW (bow wave), GFX_DEP (deposit iterations),
GFX_RELAX (relax iterations).

Run:
  blender --background --factory-startup --python dev/probe_spikes.py
"""
from __future__ import annotations

import os
import sys

import bpy

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from groundfx.core.constants import ATTR_HEIGHT, ATTR_CARVE, ELEM_SAND, MODIFIER_NAME  # noqa: E402
from groundfx.core import modifier_io  # noqa: E402
from groundfx.core.nodegroups import ng_ground_sim as gsim  # noqa: E402

THRESH = 0.002  # 2 mm one-cell deviation is clearly visible at close-up scale


def _reset():
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()


def _grid(obj, deps):
    ev = obj.evaluated_get(deps)
    me = ev.data
    ha = me.attributes.get(ATTR_HEIGHT)
    ca = me.attributes.get(ATTR_CARVE)
    xs = sorted({round(v.co.x, 5) for v in me.vertices})
    ys = sorted({round(v.co.y, 5) for v in me.vertices})
    n = len(xs)
    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: i for i, y in enumerate(ys)}
    h = [[0.0] * n for _ in range(n)]
    c = [[0.0] * n for _ in range(n)]
    for k, v in enumerate(me.vertices):
        i = yi[round(v.co.y, 5)]
        j = xi[round(v.co.x, 5)]
        h[i][j] = ha.data[k].value
        c[i][j] = ca.data[k].value if ca else 0.0
    return n, h, c, xs, ys


def _report(tag, n, h, c, ys):
    worst = 0.0
    worst_at = None
    spikes = []
    for i in range(1, n - 1):
        for j in range(1, n - 1):
            nb = (h[i - 1][j] + h[i + 1][j] + h[i][j - 1] + h[i][j + 1]) * 0.25
            r = h[i][j] - nb
            if abs(r) > abs(worst):
                worst, worst_at = r, (i, j)
            if abs(r) > THRESH:
                spikes.append((i, j, r))
    touch = sum(1 for i, j, _ in spikes
                if any(c[i + di][j + dj] > 1e-5
                       for di, dj in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))))
    print(f"PROBE:{tag}:worst={worst:+.5f}@{worst_at} spikes={len(spikes)} "
          f"at_footprint={touch}")
    mid = n // 2
    print(f"PROBE:{tag}:section=" + " ".join(f"{v * 1000:.0f}" for v in h[mid][::2]))
    # (pi,pi) checkerboard amplitude vs total roughness over the whole field
    cb = 0.0
    tot = 0.0
    cnt = 0
    for i in range(1, n - 1):
        for j in range(1, n - 1):
            nb = (h[i - 1][j] + h[i + 1][j] + h[i][j - 1] + h[i][j + 1]) * 0.25
            r = h[i][j] - nb
            cb += r * (1 if (i + j) % 2 == 0 else -1)
            tot += abs(r)
            cnt += 1
    print(f"PROBE:{tag}:checkerboard={cb / cnt * 1000:+.4f}mm "
          f"mean_roughness={tot / cnt * 1000:.4f}mm")
    # Rim ripple: high-pass of the berm profile along the drag axis. The berm
    # runs parallel to x at the trench's lateral edge; a clean berm is smooth
    # along it, one lump per frame shows up as a bump on the high-pass.
    rim_i, rim_amp, rim_prof = None, 0.0, None
    for i in range(1, n - 1):
        prof = [h[i][j] for j in range(30, n - 30)]
        smooth = []
        for k in range(len(prof)):
            lo, hi = max(0, k - 2), min(len(prof), k + 3)
            smooth.append(sum(prof[lo:hi]) / (hi - lo))
        amp = sum(abs(a - b) for a, b in zip(prof, smooth)) / len(prof)
        if amp > rim_amp:
            rim_i, rim_amp, rim_prof = i, amp, prof
    print(f"PROBE:{tag}:rim_ripple={rim_amp * 1000:.3f}mm @row {rim_i}")
    if rim_prof:
        print(f"PROBE:{tag}:rim=" + " ".join(f"{v * 1000:.0f}" for v in rim_prof[:46]))
    # 2D patch around the worst cell, in mm
    if worst_at:
        wi, wj = worst_at
        i0, j0 = max(1, wi - 6), max(1, wj - 14)
        print(f"PROBE:{tag}:patch@({i0},{j0})")
        for i in range(i0, min(n - 1, i0 + 13)):
            print("PROBE:%s:  %s" % (tag, " ".join(
                f"{h[i][j] * 1000:4.0f}" for j in range(j0, min(n - 1, j0 + 28)))))


def _run(bw=None, dep=None, relax=None, spread=None, rate=None, tag="base",
         step=0.045, steps=24):
    _reset()
    from groundfx.ops.op_add import create_domain

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 60
    scene.frame_set(1)

    obj = create_domain(bpy.context, ELEM_SAND)
    md = obj.modifiers.get(MODIFIER_NAME)
    if bw is not None:
        modifier_io.set_input(md, gsim.IN_BOW_WAVE, float(bw))
    if dep is not None:
        modifier_io.set_input(md, gsim.IN_DEPOSIT_ITERS, int(dep))
    if relax is not None:
        modifier_io.set_input(md, gsim.IN_RELAX_ITERS, int(relax))
    if spread is not None:
        modifier_io.set_input(md, gsim.IN_DEPOSIT_SPREAD, float(spread))
    if rate is not None:
        modifier_io.set_input(md, gsim.IN_DEPOSIT_RATE, float(rate))

    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(-0.6, 0.0, 2.0))
    cube = bpy.context.active_object
    obj.groundfx.collider_collection.objects.link(cube)

    scene.frame_set(1)
    for k in range(steps):
        cube.location = (-0.6 + step * k, 0.0, 0.22)
        scene.frame_set(2 + k)
    deps = bpy.context.evaluated_depsgraph_get()
    n, h, c, xs, ys = _grid(obj, deps)
    _report(f"{tag}/drag", n, h, c, ys)

    cube.location = (0.0, 0.0, 3.0)
    for f in range(2 + steps, 2 + steps + 15):
        scene.frame_set(f)
    deps = bpy.context.evaluated_depsgraph_get()
    n, h, c, xs, ys = _grid(obj, deps)
    _report(f"{tag}/settled", n, h, c, ys)

    for o in (cube, obj):
        bpy.data.objects.remove(o, do_unlink=True)


def main():
    """GFX_CASES is a semicolon-separated list of `k=v,k=v` specs.

    Keys: bw, dep, relax, spread, rate, step, steps (plus tag).
    """
    spec_list = os.environ.get("GFX_CASES", "tag=base")
    for spec in spec_list.split(";"):
        kw = {}
        for part in spec.split(","):
            if not part.strip():
                continue
            k, _, v = part.partition("=")
            k = k.strip()
            kw[k] = v if k == "tag" else float(v)
        for k in ("dep", "relax", "steps"):
            if k in kw:
                kw[k] = int(kw[k])
        kw.setdefault("tag", spec.replace(",", "_").replace("=", ""))
        _run(**kw)


main()
