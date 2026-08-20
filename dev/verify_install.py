# SPDX-License-Identifier: GPL-3.0-or-later
"""Install GroundFX as a real extension and enable it, headless.

This exercises the manifest + the bl_ext import path, which the direct-import
smoke test does not. Prints INSTALL:PASS/FAIL lines and exits non-zero on
failure.

Run::

    blender --background --factory-startup --python dev/verify_install.py -- <repo_root>
"""
from __future__ import annotations

import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
repo_root = argv[0] if argv else os.getcwd()

# Build the distributable ZIP first (installer expects an archive, not a dir).
sys.path.insert(0, os.path.join(repo_root, "dev"))
import build as _build  # noqa: E402

zip_path = _build.build()


def line(tag, ok, detail=""):
    print(f"INSTALL:{'PASS' if ok else 'FAIL'}:{tag}"
          + (f":{detail}" if detail and not ok else ""), flush=True)
    return ok


ok = True

# 1. Install from the built ZIP into the default user repo.
try:
    bpy.ops.extensions.package_install_files(
        filepath=zip_path,
        repo="user_default",
        enable_on_install=True,
    )
    ok &= line("package_install_files", True)
except Exception as e:  # noqa: BLE001
    ok &= line("package_install_files", False, repr(e))

# 2. The addon module should now be enabled under a bl_ext path.
enabled = [m for m in bpy.context.preferences.addons.keys()
           if m.endswith(".groundfx") or m == "groundfx"]
ok &= line("addon enabled", bool(enabled),
           f"enabled addons: {list(bpy.context.preferences.addons.keys())}")

# 3. The panel class registered through the real load path.
ok &= line("panel present", hasattr(bpy.types, "GFX_PT_main"))

# 4. Clean up so the run is repeatable and leaves no half-built copy behind.
for mod in list(bpy.context.preferences.addons.keys()):
    if mod.endswith(".groundfx"):
        # Find the repo index of the user_default repo the ZIP went into.
        repos = bpy.context.preferences.extensions.repos
        idx = next((i for i, r in enumerate(repos)
                    if r.module == "user_default"), 0)
        try:
            bpy.ops.extensions.package_uninstall(
                repo_index=idx, pkg_id="groundfx")
            line("uninstall cleanup", True)
        except Exception as e:  # noqa: BLE001
            line("uninstall cleanup", False, repr(e))
        break

sys.exit(0 if ok else 1)
