# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a reproducible hero test scene and render it with Cycles.

A box ploughs through the material and stops; the camera sits low and close,
lit by a sun + physical sky. Used to judge realism by eye, not by tests.

Run::

    blender --background --factory-startup --python dev/hero_scene.py -- \
        --element SAND --out C:/tmp/hero --frames 40,80 [--samples 128] \
        [--save scene.blend] [--res 1280x720] [--cam close|wide|macro]
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import bpy

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--element", default="SAND")
    p.add_argument("--out", default=os.path.join(_REPO, "dev", "_renders"))
    p.add_argument("--frames", default="80")
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--res", default="1280x720")
    p.add_argument("--cam", default="close")
    p.add_argument("--quality", default="HIGH")
    p.add_argument("--size", type=float, default=1.2)
    p.add_argument("--save", default="")
    p.add_argument("--grains", action="store_true")
    p.add_argument("--no-surround", action="store_true")
    p.add_argument("--sun", default="22,120", help="elevation,rotation deg")
    p.add_argument("--exposure", type=float, default=0.0)
    p.add_argument("--noderender", action="store_true",
                   help="build + simulate only, skip rendering")
    return p.parse_args(argv)


def enable_gpu():
    prefs = bpy.context.preferences
    try:
        cprefs = prefs.addons["cycles"].preferences
    except KeyError:
        return "CPU"
    for kind in ("OPTIX", "CUDA"):
        try:
            cprefs.compute_device_type = kind
            cprefs.refresh_devices()
            devs = [d for d in cprefs.devices if d.type == kind]
            if devs:
                for d in cprefs.devices:
                    d.use = d.type == kind
                return kind
        except TypeError:
            continue
    return "CPU"


def setup_world(scene, sun_elev_deg=22.0, sun_rot_deg=120.0, strength=0.06,
                exposure=0.0):
    """Physical sky with its own sun disc: sun and sky fill stay in their
    real ratio, so shadows get the right amount of blue without tuning."""
    world = bpy.data.worlds.new("GFX_Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    for attr, val in (("sun_elevation", math.radians(sun_elev_deg)),
                      ("sun_rotation", math.radians(sun_rot_deg)),
                      ("sun_disc", True),
                      ("sun_size", math.radians(0.545)),
                      ("aerosol_density", 1.5),
                      ("ozone_density", 1.0)):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    scene.view_settings.exposure = exposure


def make_box(size=0.2, mud=False):
    import bmesh
    me = bpy.data.meshes.new("HeroBox")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    # Slightly bevelled edges catch light like a real object.
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.004, segments=3,
                    affect="EDGES", profile=0.5)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new("HeroBox", me)
    mat = bpy.data.materials.new("HeroBox_Paint")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    nt = mat.node_tree
    # Worn paint with sand dust settled toward the bottom: a clean primary
    # colour is the first thing that reads as CG.
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 14.0
    n1.inputs["Detail"].default_value = 6.0
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = -0.10
    ramp.inputs["From Max"].default_value = 0.02
    ramp.inputs["To Min"].default_value = 0.75
    ramp.inputs["To Max"].default_value = 0.0
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (0.42, 0.06, 0.035, 1.0)
    mix.inputs[7].default_value = (0.50, 0.40, 0.27, 1.0)
    rr = nt.nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.28
    rr.inputs["To Max"].default_value = 0.62
    L = nt.links.new
    L(tc.outputs["Object"], n1.inputs["Vector"])
    L(tc.outputs["Object"], sep.inputs[0])
    L(sep.outputs["Z"], ramp.inputs["Value"])
    L(ramp.outputs[0], mul.inputs[0])
    L(n1.outputs[0], mul.inputs[1])
    L(mul.outputs[0], mix.inputs[0])
    L(mix.outputs[2], bsdf.inputs["Base Color"])
    L(n1.outputs[0], rr.inputs["Value"])
    L(rr.outputs[0], bsdf.inputs["Roughness"])
    if mud:
        # splatter: scene dressing only, the solver does not coat flanks yet
        n1.inputs["Scale"].default_value = 60.0
        n1.inputs["Roughness"].default_value = 0.75
        ramp.inputs["From Max"].default_value = 0.10
        ramp.inputs["To Min"].default_value = 3.6
        ramp.inputs["To Max"].default_value = 0.0
        mix.inputs[7].default_value = (0.065, 0.042, 0.025, 1.0)
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = 5.0
        pw.use_clamp = True
        L(mul.outputs[0], pw.inputs[0])
        L(pw.outputs[0], mix.inputs[0])
    me.materials.append(mat)
    return obj


def setup_camera(scene, kind, target):
    cam_data = bpy.data.cameras.new("GFX_Cam")
    cam_data.clip_start = 0.002  # macro: subject is a few cm away
    cam = bpy.data.objects.new("GFX_Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    tx, ty, tz = target
    if kind == "wide":
        cam.location = (tx - 0.15, ty - 1.25, tz + 0.75)
        cam_data.lens = 35
    elif kind == "macro":
        # looks at the side levee next to the trench, grain scale
        target = (tx + 0.33, ty - 0.04, tz + 0.03)
        tx, ty, tz = target
        cam.location = (tx + 0.10, ty - 0.15, tz + 0.06)
        cam_data.lens = 100
    elif kind == "micro":
        # ~1:2 reproduction on the sunlit slope of the bow-wave heap
        target = (tx + 0.33, ty - 0.04, tz + 0.03)
        tx, ty, tz = target
        cam.location = (tx + 0.02, ty - 0.045, tz + 0.06)
        cam_data.lens = 100
    elif kind == "hero":
        # low, long lens, looking along the track toward the object
        target = (tx - 0.02, ty, tz + 0.03)
        tx, ty, tz = target
        cam.location = (tx - 0.95, ty - 0.62, tz + 0.2)
        cam_data.lens = 70
    else:  # close
        cam.location = (tx + 0.25, ty - 0.55, tz + 0.22)
        cam_data.lens = 50
    if kind in ("macro", "micro"):
        cam["gfx_offset"] = [cam.location[k] - (tx, ty, tz)[k] for k in range(3)]
    tgt = bpy.data.objects.new("GFX_CamTarget", None)
    scene.collection.objects.link(tgt)
    tgt.location = target
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    cam_data.dof.use_dof = kind != "wide"
    cam_data.dof.focus_object = tgt
    cam_data.dof.aperture_fstop = {"macro": 8.0, "micro": 11.0, "hero": 5.6}.get(kind, 11.0)
    return cam


def build(element="SAND", quality="HIGH", size=1.2, cam="close", grains=False,
          surround=True, sun=(22.0, 120.0), exposure=0.0):
    import groundfx
    try:
        groundfx.unregister()
    except Exception:  # noqa: BLE001
        pass
    groundfx.register()
    from groundfx.ops.op_add import create_domain, rebuild_grid
    from groundfx.ops.op_collider import ensure_collider_collection

    scene = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    domain = create_domain(bpy.context, element, size=size, surface=True)
    domain.groundfx.domain_size = size
    domain.groundfx.quality = quality
    rebuild_grid(domain)
    domain.groundfx.surround = surround

    h = domain.groundfx.material_height
    box = make_box(0.2, mud=element == "MUD")
    scene.collection.objects.link(box)
    coll = ensure_collider_collection(bpy.context, domain)
    coll.objects.link(box)
    box.groundfx.is_collider = True

    scene.frame_start, scene.frame_end = 1, 90
    depth = {"MUD": 0.03}.get(element, 0.022)
    zc = h + 0.1 - depth  # box bottom this far below the surface
    keys = {1: (-0.30, 0.0, zc + 0.06), 8: (-0.30, 0.0, zc),
            55: (0.12, 0.0, zc), 90: (0.12, 0.0, zc)}
    for f, loc in keys.items():
        box.location = loc
        box.keyframe_insert("location", frame=f)
    for fc in _fcurves(box):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.easing = "AUTO"

    setup_world(scene, sun[0], sun[1], exposure=exposure)
    setup_camera(scene, cam, (0.0, 0.0, h))
    if grains:
        from groundfx.ops import op_grains
        op_grains.add_grain_layer(bpy.context, domain)
    return domain, box


def _fcurves(obj):
    ad = obj.animation_data
    if ad is None or ad.action is None:
        return []
    act = ad.action
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out = []  # 5.x layered actions
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def apply_res(scene, res):
    scene.render.resolution_x, scene.render.resolution_y = (
        int(v) for v in res.lower().split("x"))
    scene.render.resolution_percentage = 100


def snap_to_surface(scene):
    """Macro cameras: put the target on the simulated surface, keep offset."""
    cam = scene.camera
    if cam is None or "gfx_offset" not in cam:
        return
    tgt = bpy.data.objects.get("GFX_CamTarget")
    deps = bpy.context.evaluated_depsgraph_get()
    from mathutils import Vector
    origin = Vector((tgt.location.x, tgt.location.y, 5.0))
    hit, loc, _n, _i, ob, _m = scene.ray_cast(deps, origin, Vector((0, 0, -1)))
    if hit:
        tgt.location.z = loc.z
        off = cam["gfx_offset"]
        cam.location = (loc.x + off[0], loc.y + off[1], loc.z + off[2])


def render(scene, out_dir, frames, samples, res, tag):
    os.makedirs(out_dir, exist_ok=True)
    scene.render.engine = "CYCLES"
    dev = enable_gpu()
    scene.cycles.device = "GPU" if dev != "CPU" else "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = (
        int(v) for v in res.lower().split("x"))
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    last = max(frames)
    for f in range(scene.frame_start, last + 1):
        scene.frame_set(f)  # step the simulation in order
        if f in frames:
            snap_to_surface(scene)
            scene.render.filepath = os.path.join(out_dir, f"{tag}_f{f:03d}.png")
            bpy.ops.render.render(write_still=True)
            print(f"RENDERED {scene.render.filepath} on {dev}", flush=True)


def main():
    a = _args()
    apply_res(bpy.context.scene, a.res)  # grain layer reads the resolution
    sun = tuple(float(v) for v in a.sun.split(","))
    domain, _box = build(a.element, a.quality, a.size, a.cam, a.grains,
                         surround=not a.no_surround, sun=sun,
                         exposure=a.exposure)
    scene = bpy.context.scene
    frames = [int(f) for f in a.frames.split(",")]
    if a.grains:
        deps = bpy.context.evaluated_depsgraph_get()
        n_inst = sum(1 for i in deps.object_instances if i.is_instance)
        print(f"INSTANCES {n_inst}", flush=True)
    if a.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.save))
    if not a.noderender:
        tag = f"{a.element.lower()}_{a.cam}" + ("_grains" if a.grains else "")
        render(scene, a.out, frames, a.samples, a.res, tag)


if __name__ == "__main__":
    main()
