# SPDX-License-Identifier: GPL-3.0-or-later
"""Print the sockets and properties of geometry nodes by idname.

    blender -b --factory-startup --python dev/probe_nodes.py -- \
        GeometryNodeRemoveAttribute GeometryNodePointsToVolume
"""
import sys

import bpy

names = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
tree = bpy.data.node_groups.new("probe", "GeometryNodeTree")
for idname in names:
    try:
        n = tree.nodes.new(idname)
    except RuntimeError as exc:
        print(f"NODE {idname}: MISSING ({exc})")
        continue
    print(f"NODE {idname}")
    for s in n.inputs:
        dv = getattr(s, "default_value", None)
        try:
            dv = tuple(dv)
        except TypeError:
            pass
        print(f"  in  {s.name!r:28} {s.type:10} default={dv!r} enabled={s.enabled}")
    for s in n.outputs:
        print(f"  out {s.name!r:28} {s.type:10} enabled={s.enabled}")
    skip = {p.identifier for p in bpy.types.Node.bl_rna.properties}
    for p in n.bl_rna.properties:
        if p.identifier in skip:
            continue
        extra = ""
        if p.type == "ENUM":
            extra = " " + str([e.identifier for e in p.enum_items])
        print(f"  prop {p.identifier} ({p.type}){extra}")
