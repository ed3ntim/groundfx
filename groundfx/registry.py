# SPDX-License-Identifier: GPL-3.0-or-later
"""Single source of truth for class registration.

Every module that defines Blender classes exposes a module-level ``classes``
tuple. This file lists those modules in dependency order; ``all_classes()``
flattens them. Registration and unregistration happen in one place, so there
is never a stray ``register_class`` call hiding in a feature module.
"""
from __future__ import annotations

from .data import prefs
from .ui import panels

# Order matters: a class must be registered after anything it references
# (e.g. PropertyGroups before the panels that draw them). As features land in
# later epics their modules get appended here.
_MODULES = (
    prefs,
    panels,
)


def all_classes():
    """Yield every registrable class, in registration order."""
    for module in _MODULES:
        yield from getattr(module, "classes", ())
