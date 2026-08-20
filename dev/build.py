# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a distributable GroundFX extension ZIP.

Plain Python (no bpy) so it runs with any interpreter, including the one
Blender bundles. Produces ``dist/groundfx-<version>.zip`` whose top-level
folder is ``groundfx/`` with the manifest inside — the layout Blender's
extension installer expects.

Run::

    <python> dev/build.py            # writes dist/groundfx-<version>.zip
    <python> dev/build.py --print    # just print the output path it would use
"""
from __future__ import annotations

import os
import re
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(REPO_ROOT, "groundfx")
DIST_DIR = os.path.join(REPO_ROOT, "dist")

# Files/dirs never shipped.
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo")


def read_version() -> str:
    manifest = os.path.join(PKG_DIR, "blender_manifest.toml")
    with open(manifest, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("could not find version in blender_manifest.toml")
    return m.group(1)


def output_path() -> str:
    return os.path.join(DIST_DIR, f"groundfx-{read_version()}.zip")


def build() -> str:
    out = output_path()
    os.makedirs(DIST_DIR, exist_ok=True)
    if os.path.exists(out):
        os.remove(out)

    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PKG_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for name in files:
                if name.endswith(EXCLUDE_SUFFIXES):
                    continue
                abs_path = os.path.join(root, name)
                # Archive path keeps the top-level "groundfx/" folder.
                rel = os.path.relpath(abs_path, REPO_ROOT)
                zf.write(abs_path, rel.replace(os.sep, "/"))
                count += 1
    print(f"BUILD:OK:{out}:{count} files")
    return out


if __name__ == "__main__":
    if "--print" in sys.argv:
        print(output_path())
    else:
        build()
