# SPDX-License-Identifier: GPL-3.0-or-later
"""Central catalogue of every name GroundFX reuses across modules.

Rule of the codebase: if a string is referenced in two places, it lives here.
That keeps operator ids, attribute names and node-group names collision-free
(all carry the ``groundfx``/``gfx`` prefix) and refactorable from one spot.
"""
from __future__ import annotations

# --- Addon identity --------------------------------------------------------
ADDON_PKG = "groundfx"          # top-level package name (import root)
ADDON_ID = "groundfx"           # extension id, matches blender_manifest.toml
ADDON_NAME = "GroundFX"

# Node-group / node-tree data-block version. Bumped whenever the generated
# node graph changes shape, so ensure_node_group() knows to rebuild.
NODEGROUP_VERSION = 1

# --- UI ---------------------------------------------------------------------
PANEL_CATEGORY = "GroundFX"     # N-panel tab label
COLLECTION_NAME = "GroundFX"    # collection that holds domain objects

# --- Elements ---------------------------------------------------------------
ELEM_SAND = "SAND"
ELEM_SNOW = "SNOW"
ELEM_MUD = "MUD"
ELEMENTS = (ELEM_SAND, ELEM_SNOW, ELEM_MUD)

ELEMENT_LABELS = {
    ELEM_SAND: "Sand",
    ELEM_SNOW: "Snow",
    ELEM_MUD: "Mud",
}

# --- Quality levels ---------------------------------------------------------
QUALITY_LOW = "LOW"
QUALITY_MEDIUM = "MEDIUM"
QUALITY_HIGH = "HIGH"
QUALITY_ULTRA = "ULTRA"
QUALITY_LEVELS = (QUALITY_LOW, QUALITY_MEDIUM, QUALITY_HIGH, QUALITY_ULTRA)

# --- Simulation-state attribute names --------------------------------------
# Stored on the domain mesh points; consumed by the solver and the shaders.
ATTR_HEIGHT = "gfx_h"           # material height above base (the "mass")
ATTR_BASE = "gfx_base"          # static ground height sampled from terrain
ATTR_CARVE = "gfx_carve"        # collider penetration this frame
ATTR_CARVE_PREV = "gfx_carve_prev"   # previous frame's carve (velocity source)
ATTR_PILE = "gfx_pile"          # displaced volume awaiting deposition
ATTR_COMP = "gfx_comp"          # compaction 0..1 -> shader
ATTR_WET = "gfx_wet"            # wetness 0..1 -> cohesion & shader
ATTR_FLOW = "gfx_flow"          # last displacement direction (vector) -> shader
ATTR_AGE = "gfx_age"            # frames since last disturbance

# --- Object custom-property keys -------------------------------------------
PROP_IS_DOMAIN = "gfx_is_domain"       # marks a GroundFX domain object
PROP_IS_COLLIDER = "gfx_is_collider"   # marks a collider object
PROP_ELEMENT = "gfx_element"           # which element a domain carries
PROP_NG_VERSION = "gfx_ng_version"     # node-group version stamp on the tree

# --- Node-group names -------------------------------------------------------
NG_GROUND_SIM = "GFX_GroundSim"        # top-level solver group
NG_DEPOSIT = "GFX_Deposit"
NG_COLLIDE = "GFX_Collide"
NG_DISPLACE = "GFX_Displace"
NG_RELAX = "GFX_Relax"
NG_SPRAY = "GFX_Spray"
NG_DISPLAY = "GFX_Display"

# --- Material names ---------------------------------------------------------
MAT_SAND = "GFX_Sand"
MAT_SNOW = "GFX_Snow"
MAT_MUD = "GFX_Mud"

# --- Defaults (close-up scale, decided in phase 2) -------------------------
DEFAULT_DOMAIN_SIZE = 2.0        # metres, square domain
DEFAULT_MATERIAL_HEIGHT = 0.08   # metres of material at rest
DEFAULT_EMITTER_RADIUS = 0.30    # metres

# --- Cache ------------------------------------------------------------------
CACHE_DIRNAME = "groundfx_cache"

# --- Operator id prefix -----------------------------------------------------
# Blender operator ids look like "groundfx.add_ground"; keep the namespace
# constant so every op stays under one roof.
OP_PREFIX = "groundfx"
