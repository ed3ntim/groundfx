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


def setup_world(scene, sun_elev_deg=28.0, sun_rot_deg=35.0, strength=1.0):
    world = bpy.data.worlds.new("GFX_Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "NISHITA", "SINGLE_SCATTERING"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    for attr, val in (("sun_elevation", math.radians(sun_elev_deg)),
                      ("sun_rotation", math.radians(sun_rot_deg)),
                      ("sun_disc", False)):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
    bg.inputs["Strength"].default_value = 0.08 * strength
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])

    # A real sun lamp gives crisp, controllable grain shadows.
    sun_data = bpy.data.lights.new("GFX_Sun", "SUN")
    sun_data.energy = 3.2 * strength
    sun_data.angle = math.radians(0.53)
    sun_data.color = (1.0, 0.95, 0.88)
    sun = bpy.data.objects.new("GFX_Sun", sun_data)
    scene.collection.objects.link(sun)
    el, rot = math.radians(sun_elev_deg), math.radians(sun_rot_deg)
    sun.rotation_euler = (math.pi / 2 - el, 0.0, rot + math.pi / 2)
    return sun


def make_box(size=0.2):
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
    bsdf.inputs["Base Color"].default_value = (0.55, 0.08, 0.04, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
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
    cam_data.dof.aperture_fstop = {"macro": 8.0, "micro": 11.0}.get(kind, 5.6)
    return cam


def build(element="SAND", quality="HIGH", size=1.2, cam="close", grains=False):
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

    domain = create_domain(bpy.context, element, size=size)
    domain.groundfx.domain_size = size
    domain.groundfx.quality = quality
    rebuild_grid(domain)

    h = domain.groundfx.material_height
    box = make_box(0.2)
    scene.collection.objects.link(box)
    coll = ensure_collider_collection(bpy.context, domain)
    coll.objects.link(box)
    box.groundfx.is_collider = True

    scene.frame_start, scene.frame_end = 1, 90
    zc = h + 0.1 - 0.045  # box bottom 4.5 cm below the surface
    keys = {1: (-0.45, 0.0, zc), 55: (0.12, 0.0, zc), 90: (0.12, 0.0, zc)}
    for f, loc in keys.items():
        box.location = loc
        box.keyframe_insert("location", frame=f)
    for fc in _fcurves(box):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.easing = "AUTO"

    setup_world(scene)
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
    domain, _box = build(a.element, a.quality, a.size, a.cam, a.grains)
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
