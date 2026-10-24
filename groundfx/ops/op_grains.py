# SPDX-License-Identifier: GPL-3.0-or-later
"""Grain layer: real 3D grains where the camera can resolve them.

At macro range a shader alone cannot give grain silhouettes, contact shadows
under single grains or the sparkle of one quartz facet. This layer scatters
instanced grain meshes over the simulated surface, but only inside the camera
frustum and only out to the distance where a grain still covers a few pixels;
beyond that the surface shader (same mineral palette) takes over, so the
hand-off is invisible.

* Positions come from Distribute Points on Faces over a *selection* of the
  constant-topology grid, so grains keep their place frame to frame and ride
  the deforming surface instead of flickering.
* Grains sit a third embedded, randomly rotated, scaled 0.6-1.4 x the grain
  size, picked from a small library of procedurally made grain meshes.
* In the viewport the layer is off unless asked for (it is a render detail).

Like Pixar's sand in *Elio* (grains as points), the work goes only where the
camera looks.
"""
from __future__ import annotations

import math

import bpy

from ..core.constants import OP_PREFIX, COLLECTION_NAME
from ..core.ng_builder import new_geometry_group
from ..core.ng_expr import make
from ..core.materials import mat_sand
from ..utils import log

NG_GRAINS = "GFX_Grains"
MOD_GRAINS = "GFX Grains"
LIB_NAME = "GFX Grain Library"
MAT_GRAIN = "GFX_SandGrain"

IN_CAMERA = "Camera"
IN_GRAIN = "Grain Size"
IN_MAX_DIST = "Max Distance"
IN_FOV = "Half FOV"
IN_DENSITY = "Coverage"
IN_LIB = "Grains"
IN_VIEWPORT = "Show In Viewport"


def _grain_mesh(name, seed, sharp):
    """A unit-size (diameter ~1) sub-rounded grain: icosphere + jitter."""
    import bmesh
    import random
    rng = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
    sx, sy, sz = (rng.uniform(0.75, 1.15), rng.uniform(0.75, 1.15),
                  rng.uniform(0.55, 0.9))
    for v in bm.verts:
        n = v.co.normalized()
        bump = 1.0 + rng.uniform(-sharp, sharp)
        v.co = n * 0.5 * bump
        v.co.x *= sx
        v.co.y *= sy
        v.co.z *= sz
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me


def _grain_material():
    mat = bpy.data.materials.get(MAT_GRAIN)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MAT_GRAIN)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "INSTANCER"
    attr.attribute_name = "gfx_grain_id"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    mat_sand.set_ramp(ramp.color_ramp, mat_sand.PALETTE)
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.25
    rough.inputs["To Max"].default_value = 0.7
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["IOR"].default_value = 1.54
    bsdf.inputs["Subsurface Weight"].default_value = 0.15
    bsdf.inputs["Subsurface Scale"].default_value = 0.0003
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    L = nt.links.new
    L(attr.outputs["Factor"], ramp.inputs[0])
    L(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    L(attr.outputs["Factor"], rough.inputs["Value"])
    L(rough.outputs[0], bsdf.inputs["Roughness"])
    L(noise.outputs[0], bump.inputs["Height"])
    L(bump.outputs[0], bsdf.inputs["Normal"])
    L(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def ensure_library(context) -> bpy.types.Collection:
    """Hidden collection of grain meshes the layer instances from."""
    lib = bpy.data.collections.get(LIB_NAME)
    if lib is not None and len(lib.objects):
        return lib
    if lib is None:
        lib = bpy.data.collections.new(LIB_NAME)
        parent = bpy.data.collections.get(COLLECTION_NAME) or context.scene.collection
        parent.children.link(lib)
    mat = _grain_material()
    for k in range(8):
        me = _grain_mesh(f"gfx_grain_{k}", seed=101 + k, sharp=0.04 + 0.03 * (k % 3))
        me.materials.append(mat)
        ob = bpy.data.objects.new(f"gfx_grain_{k}", me)
        ob.location = (k * 2.0, 0.0, -100.0)  # library sits out of the way
        lib.objects.link(ob)
    lib.hide_render = True
    lib.hide_viewport = True
    return lib


def build(name=NG_GRAINS):
    tree = new_geometry_group(name)
    b, g = make(tree)
    b.input("Geometry", "NodeSocketGeometry")
    b.input(IN_CAMERA, "NodeSocketObject")
    b.input(IN_LIB, "NodeSocketCollection")
    b.input(IN_GRAIN, "NodeSocketFloat", default=mat_sand.GRAIN_SIZE, min=1e-5,
            subtype="DISTANCE")
    b.input(IN_MAX_DIST, "NodeSocketFloat", default=0.4, min=0.0,
            subtype="DISTANCE")
    b.input(IN_FOV, "NodeSocketFloat", default=math.radians(20.0), min=0.0,
            subtype="ANGLE")
    b.input(IN_DENSITY, "NodeSocketFloat", default=1.0, min=0.0, max=4.0)
    b.input(IN_VIEWPORT, "NodeSocketBool", default=False)
    b.output("Geometry", "NodeSocketGeometry")
    gin, gout = b.group_io()
    I = lambda k: g.out(gin, k)  # noqa: E731

    cam = g.node("GeometryNodeObjectInfo", {"Object": I(IN_CAMERA)},
                 transform_space="RELATIVE")
    cam_pos = g.out(cam, "Location")
    fwd = g.out(g.node("FunctionNodeRotateVector",
                       {"Vector": (0.0, 0.0, -1.0),
                        "Rotation": g.out(cam, "Rotation")}), 0)
    to = g.position() - cam_pos
    dist = to.length()
    cosang = to.normalize().dot(fwd)
    max_d = I(IN_MAX_DIST)
    # Face test is generous (half-FOV + margin) so edges never pop.
    in_view = g.math("MULTIPLY", dist.lt(max_d * 1.1),
                     cosang.gt(g.math("COSINE", (I(IN_FOV) * 1.25).min(1.5))))

    grain = I(IN_GRAIN)
    density = I(IN_DENSITY) * 1.3 / (grain * grain)
    dist_node = g.node("GeometryNodeDistributePointsOnFaces",
                       {"Mesh": I("Geometry"), "Selection": in_view,
                        "Density": density, "Seed": 7},
                       distribute_method="RANDOM")
    pts = g.out(dist_node, "Points")
    ident = g.out(g.node("GeometryNodeInputID"), 0)
    # Thin out toward the far limit so the hand-off to the shader is soft.
    keep = g.random(3, 0.0, 1.0, ident).lt(((max_d - dist) / (max_d * 0.35)).clamp())
    keep = g.math("MULTIPLY", keep, cosang.gt(g.math("COSINE", I(IN_FOV))))
    pts = g.out(g.node("GeometryNodeDeleteGeometry",
                       {"Geometry": pts, "Selection": keep.lt(0.5)},
                       domain="POINT"), 0)
    normal = g.out(dist_node, "Normal")
    size = grain * g.random(4, 0.6, 1.4, ident)
    sp = g.node("GeometryNodeSetPosition",
                {"Geometry": pts, "Offset": normal * (size * -0.3)})
    lib = g.node("GeometryNodeCollectionInfo",
                 {"Collection": I(IN_LIB), "Separate Children": True,
                  "Reset Children": True}, transform_space="ORIGINAL")
    rot = g.out(g.node("FunctionNodeRandomValue",
                       {"Min": (0.0, 0.0, 0.0),
                        "Max": (6.2832, 6.2832, 6.2832), "ID": ident,
                        "Seed": 5}, data_type="FLOAT_VECTOR"), "Value")
    rot = g.out(g.node("FunctionNodeEulerToRotation", {0: rot}), 0)
    iop = g.node("GeometryNodeInstanceOnPoints",
                 {"Points": g.out(sp, 0), "Instance": g.out(lib, 0),
                  "Pick Instance": True,
                  "Instance Index": g.random(6, 0.0, 1000.0, ident).floor(),
                  "Rotation": rot, "Scale": size})
    inst = g.store(g.out(iop, 0), "gfx_grain_id", g.random(8, 0.0, 1.0, ident),
                   domain="INSTANCE")
    show = g.math("MAXIMUM",
                  g.math("SUBTRACT", 1.0, g.out(b.add("GeometryNodeIsViewport"), 0)),
                  I(IN_VIEWPORT))
    sw = g.node("GeometryNodeSwitch", {"Switch": show, "True": inst},
                input_type="GEOMETRY")
    join = b.add("GeometryNodeJoinGeometry")
    g.feed(join, 0, g.out(sw, 0))
    g.feed(join, 0, I("Geometry"))
    g.feed(gout, "Geometry", g.out(join, 0))
    b.layout()
    return tree


def _camera_params(scene, grain, min_px=4.0):
    """Half FOV and the distance up to which a grain spans ``min_px``."""
    cam = scene.camera
    if cam is None or cam.type != "CAMERA":
        return math.radians(30.0), 0.3
    data = cam.data
    width_px = scene.render.resolution_x * scene.render.resolution_percentage / 100
    sensor = data.sensor_width
    f_px = data.lens / sensor * width_px
    half = math.atan(0.5 * sensor / data.lens)
    aspect = scene.render.resolution_y / max(1, scene.render.resolution_x)
    half = math.atan(math.tan(half) * math.sqrt(1 + aspect * aspect))
    return half, grain * f_px / min_px


def add_grain_layer(context, domain, grain=mat_sand.GRAIN_SIZE):
    """Add (or refresh) the grain layer modifier on a domain."""
    from ..core import modifier_io
    lib = ensure_library(context)
    tree = bpy.data.node_groups.get(NG_GRAINS) or build()
    md = domain.modifiers.get(MOD_GRAINS)
    if md is None:
        md = domain.modifiers.new(MOD_GRAINS, "NODES")
    md.node_group = tree
    modifier_io.invalidate(tree.name)
    half, max_d = _camera_params(context.scene, grain)
    modifier_io.set_input(md, IN_CAMERA, context.scene.camera, tag=False)
    modifier_io.set_input(md, IN_LIB, lib, tag=False)
    modifier_io.set_input(md, IN_GRAIN, grain, tag=False)
    modifier_io.set_input(md, IN_FOV, half, tag=False)
    modifier_io.set_input(md, IN_MAX_DIST, max_d, tag=True)
    log.info("grain layer on %s: grains to %.2f m, half FOV %.1f deg",
             domain.name, max_d, math.degrees(half))
    return md


class GFX_OT_grain_layer(bpy.types.Operator):
    """Add real 3D grains where the active camera can resolve them (macro)"""

    bl_idname = f"{OP_PREFIX}.grain_layer"
    bl_label = "Add Grain Layer"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and getattr(ob, "groundfx", None) and ob.groundfx.is_domain

    def execute(self, context):
        if context.scene.camera is None:
            self.report({"WARNING"}, "Needs an active scene camera")
            return {"CANCELLED"}
        add_grain_layer(context, context.active_object)
        return {"FINISHED"}


classes = (GFX_OT_grain_layer,)
