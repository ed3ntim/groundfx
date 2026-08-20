# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point for headless tests.

Run::

    blender --background --factory-startup --python tests/run_all.py

Makes the repo importable, discovers ``test_*`` modules in this folder, and
runs every ``test_*`` function they expose through the harness. Exits non-zero
on any failure.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import sys

# Make both the repo root (so ``import groundfx``) and this folder importable.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
for p in (_REPO_ROOT, _THIS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import harness  # noqa: E402


def _discover():
    funcs = []
    for mod_info in pkgutil.iter_modules([_THIS_DIR]):
        name = mod_info.name
        if not name.startswith("test_"):
            continue
        module = importlib.import_module(name)
        for attr in sorted(dir(module)):
            if attr.startswith("test_"):
                funcs.append(getattr(module, attr))
    return funcs


if __name__ == "__main__":
    harness.finish_and_exit(_discover())
