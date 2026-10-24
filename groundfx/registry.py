# SPDX-License-Identifier: GPL-3.0-or-later
"""Single source of truth for class registration.

Every module that defines Blender classes exposes a module-level ``classes``
tuple. This file lists those modules in dependency order; ``all_classes()``
flattens them. Registration and unregistration happen in one place, so there
is never a stray ``register_class`` call hiding in a feature module.

PropertyGroup pointer properties (which are not classes) are handled by the
explicit register/unregister hooks below.
"""
from __future__ import annotations

from .data import prefs
from .data import properties
from .ops import op_add
from .ops import op_collider
from .ops import op_freeze
from .ops import op_bake
from .ops import op_preset
from .ops import op_live
from .ops import op_bench
from .ops import op_grains
from .ui import panels

# Order matters: PropertyGroups before the panels/operators that reference
# them. As features land in later epics their modules get appended here.
_MODULES = (
    prefs,
    properties,
    op_add,
    op_collider,
    op_freeze,
    op_bake,
    op_preset,
    op_live,
    op_bench,
    op_grains,
    panels,
)


def all_classes():
    """Yield every registrable class, in registration order."""
    for module in _MODULES:
        yield from getattr(module, "classes", ())


def register_extras():
    """Register non-class bits (pointer properties, menu append) after classes."""
    properties.register_pointers()
    panels.register_menu()


def unregister_extras():
    """Tear down non-class bits before classes go away."""
    panels.unregister_menu()
    properties.unregister_pointers()
