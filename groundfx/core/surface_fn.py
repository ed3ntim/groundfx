# SPDX-License-Identifier: GPL-3.0-or-later
"""Meso-scale surface functions shared by geometry and shading (gen 3).

The simulation resolves centimetres, the grain shader fractions of a
millimetre. Everything in between (wind ripples, clods of dug-up sand) is
synthesised here, as plain field math on the XY position.

The functions are written against ``Expr`` and use only nodes that exist in
both geometry and shader trees (Math, Vector Math, Noise). The surface stage
therefore displaces real geometry with exactly the function the shader uses
to sort grain colours into ripple troughs and to bump the far field, and the
two never drift apart.
"""
from __future__ import annotations

import math

_TAU = 2.0 * math.pi


def smoothstep(x):
    """Hermite 0..1 of an already normalised value."""
    x = x.clamp(0.0, 1.0)
    return x * x * (3.0 - x * 2.0)


def _noise(g, vec, scale=1.0, detail=2.0, roughness=0.5):
    n = g.node("ShaderNodeTexNoise",
               {"Vector": vec, "Scale": scale, "Detail": detail,
                "Roughness": roughness})
    return g.out(n, 0) - 0.5


def ripple_height(g, P, wavelength, angle):
    """Aeolian ripples, normalised to about -1..1 (crest = +1).

    ``angle`` is the wind direction in the XY plane; crests run across it.
    Real ripple fields are never a clean sine: crests wander, vary in height
    and end in Y-junctions. Three ingredients give that:

    * a low-frequency phase warp, stretched along the crest, bends the lines;
    * a skewed profile (gentle windward side, short lee side);
    * two phase-shifted copies blended by a patch mask, so where patches meet
      a crest runs into a trough and terminates, as real defects do.
    """
    c = g.math("COSINE", angle)
    s = g.math("SINE", angle)
    u = P.x * c + P.y * s          # along the wind, across the crests
    v = P.y * c - P.x * s          # along the crests
    k = 1.0 / wavelength
    uk, vk = u * k, v * k

    warp = _noise(g, g.vec(uk * 0.30, vk * 0.10, 3.1), detail=2.0) * 2.2
    warp = warp + _noise(g, g.vec(uk * 1.1, vk * 0.45, 7.7), detail=1.0) * 0.5
    phase = (uk + warp) * _TAU

    def profile(t):
        p = g.math("SINE", t + g.math("SINE", t) * 0.6)
        # narrow crests over wide, flat troughs (extremes stay at +-1)
        return p - (1.0 - p * p) * 0.3

    patch = _noise(g, g.vec(uk * 0.22, vk * 0.07, 19.3), detail=1.0)
    blend = smoothstep(patch * 9.0 + 0.5)
    wave = g.mix(profile(phase), profile(phase + math.pi * 0.9), blend)
    amp = (0.75 + _noise(g, g.vec(uk * 0.17, vk * 0.17, 11.0)) * 1.1).clamp(0.25, 1.2)
    return wave * amp


def clod_height(g, P):
    """Lumps of disturbed, slightly damp sand, about -1..1.

    Two octaves: centimetre clods and the half-centimetre crumbs between
    them. Finer structure is left to the grain shader.
    """
    big = _noise(g, P, scale=48.0, detail=3.0, roughness=0.55)
    small = _noise(g, P, scale=150.0, detail=2.0, roughness=0.6)
    # ridged: crumbled sand has sharp little crests, not round pillows
    ridged = 0.5 - (small * 2.0).abs()
    return (big * 2.4 + ridged * 2.2).clamp(-1.5, 1.5)


def mud_undulation(g, P):
    """The uneven lie of a mud flat: broad shallow hollows and rises, about
    -1..1. Hollows are where water stands."""
    broad = _noise(g, P, scale=3.2, detail=3.0, roughness=0.5)
    mid = _noise(g, P, scale=11.0, detail=2.0, roughness=0.5)
    return (broad * 3.6 + mid * 1.2).clamp(-1.5, 1.5)


def mud_pocks(g, P):
    """Fine lumpiness of a settled mud surface, about -1..1."""
    return (_noise(g, P, scale=70.0, detail=4.0, roughness=0.6) * 4.0).clamp(-1.5, 1.5)


def mud_lobes(g, P):
    """Squeezed-out mud: rounded bulges with creases between them, about
    0..1. Smooth Voronoi gives the pillow shape viscous material takes when
    it is pushed aside and sags."""
    v = g.node("ShaderNodeTexVoronoi",
               {"Vector": P, "Scale": 26.0, "Smoothness": 0.35,
                "Randomness": 1.0},
               feature="SMOOTH_F1", voronoi_dimensions="3D")
    d = g.out(v, "Distance")
    warp = _noise(g, P, scale=9.0, detail=2.0)
    return (1.0 - d * 1.5 + warp * 1.2).clamp(0.0, 1.2)


def dune_height(g, P):
    """Very broad undulation for the far surround, about -1..1."""
    return _noise(g, P, scale=0.045, detail=2.0, roughness=0.45) * 2.0
