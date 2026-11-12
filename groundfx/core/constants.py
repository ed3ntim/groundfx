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
# v4 (E4-S1): single Collider object socket -> Collider Collection socket.
# v5 (E4-S3): carve_prev + bow-wave (directional deposit) input.
# v6 (E4-S4): supersampled contact carve (Contact AA) for hero silhouettes.
# v7 (B1): cohesion scales with cell size (extra-slope yield), so walls relax.
# v8 (B2): lazy pile diffusion + upwind bow wave + Deposit Spread/Rate inputs.
# v9 (E3-S5): swept carve along collider motion + Carve Substeps input.
# v10 (P1): static-friction hold in relaxation + Stickiness input.
# v11 (E3-S4): gfx_comp recovery + gfx_age + gfx_flow fields, Recovery input.
# v20 (solver v2): pairwise 8-neighbour relax, exact scatter displacement,
#      per-vertex collider velocity + swept sub-frame copies, Yield input.
# v22 (gen 3): gfx_dist / gfx_damp fields, Drying input; surface stage group.
NODEGROUP_VERSION = 22

# --- UI ---------------------------------------------------------------------
PANEL_CATEGORY = "GroundFX"     # N-panel tab label
COLLECTION_NAME = "GroundFX"    # collection that holds domain objects
# Per-domain collider collection: "<domain name> Colliders", nested under the
# GroundFX collection. Raycast targets the union of everything inside it (E4).
COLLIDER_COLLECTION_SUFFIX = " Colliders"

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
# Coverage 0..1: how much of the cell the collider currently *stands on*. Unlike
# gfx_carve (a per-frame delta that is only non-zero where material was cut this
# frame) this stays 1 while a collider rests, so the masks built on it don't
# flicker cell by cell as the collider advances a fraction of a cell per frame.
ATTR_OCC = "gfx_occ"
ATTR_COMP = "gfx_comp"          # compaction 0..1 -> shader
ATTR_WET = "gfx_wet"            # wetness 0..1 -> cohesion & shader
ATTR_FLOW = "gfx_flow"          # last displacement direction (vector) -> shader
ATTR_AGE = "gfx_age"            # frames since last disturbance
# Two-layer collider coupling (solver v2): a column is *covered* when a
# collider spans it; gfx_zhi is the collider's top there and gfx_top the
# material lying on it, which rides along with the collider.
ATTR_COV = "gfx_cov"
ATTR_ZHI = "gfx_zhi"
ATTR_TOP = "gfx_top"
# Gen 3 look fields: gfx_dist is 1 where the surface ever moved (persistent),
# gfx_damp is 1 on freshly exposed material and dries out over time, gfx_geo
# is the share of meso relief already present as geometry (surface stage).
ATTR_DIST = "gfx_dist"
ATTR_DAMP = "gfx_damp"
ATTR_GEO = "gfx_geo"
# 0 on sand, 0.05..1 on a scattered pebble (picks its stone colour).
ATTR_PEBBLE = "gfx_pebble"

# --- Collider proxy modes ---------------------------------------------------
# How a collider is presented to the raycast: the original mesh, or a cheap
# low-poly stand-in that follows the original (incl. deformation) via Object
# Info. Bounding box is the guaranteed perf win; convex hull keeps the shape of
# compact objects. Silhouette-true "hero" mode (original geometry) is E4-S4.
PROXY_NONE = "NONE"
PROXY_BBOX = "BBOX"
PROXY_HULL = "HULL"
PROXY_MODES = (PROXY_NONE, PROXY_BBOX, PROXY_HULL)
PROXY_MODE_LABELS = {
    PROXY_NONE: "Original",
    PROXY_BBOX: "Bounding Box",
    PROXY_HULL: "Convex Hull",
}
PROXY_TYPE_INT = {PROXY_BBOX: 0, PROXY_HULL: 1}  # -> node-group menu int
# Above this face count, a hero (Original) collider is flagged as heavy and the
# user is nudged toward a proxy (E4-T14, "wenn Poly-Zahl vertretbar").
HERO_POLY_WARN = 200_000

# --- Object custom-property keys -------------------------------------------
PROP_IS_DOMAIN = "gfx_is_domain"       # marks a GroundFX domain object
PROP_IS_COLLIDER = "gfx_is_collider"   # marks a collider object
PROP_ELEMENT = "gfx_element"           # which element a domain carries
PROP_NG_VERSION = "gfx_ng_version"     # node-group version stamp on the tree

# --- Node-group names -------------------------------------------------------
NG_GROUND_SIM = "GFX_GroundSim"        # top-level solver group
NG_COLLIDER_PROXY = "GFX_ColliderProxy"  # low-poly stand-in for a collider
NG_SURFACE = "GFX_Surface"             # display stage after the solver

# --- Modifier ---------------------------------------------------------------
MODIFIER_NAME = "GroundFX"      # name of the geometry-nodes modifier on a domain
SURFACE_MODIFIER_NAME = "GroundFX Surface"   # display stage, after the solver

# --- Material names ---------------------------------------------------------
MAT_SAND = "GFX_Sand"
MAT_SNOW = "GFX_Snow"
MAT_MUD = "GFX_Mud"

# Marks a material as GroundFX-authored, so the element switch may rebuild it
# but a material the user assigned themselves is left untouched (E8-T10).
PROP_MAT_GENERATED = "gfx_generated"

# Names of the control nodes the Look sliders write into. Looked up per material
# so a slider edit re-pushes into the right node without hard-coding indices.
MAT_CTRL_BASECOLOR = "GFX_BaseColor"
MAT_CTRL_ROUGHNESS = "GFX_Roughness"
MAT_CTRL_DETAIL = "GFX_Detail"
MAT_CTRL_WETNESS = "GFX_Wetness"
MAT_CTRL_RIPPLE_LEN = "GFX_RippleLength"
MAT_CTRL_RIPPLE_AMT = "GFX_RippleAmount"
MAT_CTRL_WIND = "GFX_Wind"

# --- Defaults (close-up scale, decided in phase 2) -------------------------
DEFAULT_DOMAIN_SIZE = 2.0        # metres, square domain
DEFAULT_MATERIAL_HEIGHT = 0.08   # metres of material at rest


# --- Operator id prefix -----------------------------------------------------
# Blender operator ids look like "groundfx.add_ground"; keep the namespace
# constant so every op stays under one roof.
OP_PREFIX = "groundfx"
