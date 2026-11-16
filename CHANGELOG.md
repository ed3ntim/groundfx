# Changelog

All notable changes to GroundFX. Versions follow
`groundfx/blender_manifest.toml`; each released version has a tag
`v<version>` and a ZIP on the
[releases page](https://github.com/ed3ntim/groundfx/releases).

## 0.7.2 - 2026-11-16

### Changed

- Sand: walls and the start of a track end in a soft, rounded crest instead
  of a hard edge. Sand now creeps very slightly, about a fifth as much as
  mud.

## 0.7.1 - 2026-11-16

### Changed

- Mud: the banks of a track sag and round off instead of standing as hard
  walls with a sharp edge. Mud creeps slowly below its angle of repose,
  which rounds lips and crests while flat slopes stay, and wetness no
  longer stiffens mud the way it stiffens damp sand.

## 0.7.0 - 2026-11-16

First public release.

### Added

- Snow: glinting ice crystals. Plates of a couple of millimetres with
  tilted facets flash when they catch the sun, in front light as well as
  against it. Flying snow pieces glint too.
- Snow: a dense layer of loose single grains on broken snow, rendered as
  instances (renders only, not in the viewport).

### Changed

- Snow no longer looks like a moulded mass: grid-scale spikes of broken
  snow are smoothed in the surface stage (not next to the object), crumbs
  are angular instead of smooth spheres, subsurface scattering is weaker
  on broken snow.
- Snow spray is finer: grain 0.7 mm instead of 1 mm, fewer large lumps.
- Powder cloud: lower and wider, rolls out along the ground; the volume
  is broken into wisps instead of an even fog and stays white from the
  side.

## 0.6.3 - 2026-11-16

### Added

- Snow: a powder cloud raised by the moving object itself, scaled by the
  Dust setting.

## 0.6.2 - 2026-11-15

### Changed

- Faster surface stage and deposit with identical geometry (mud about
  half the time per frame in renders, snow about a third less).

## 0.6.1 - 2026-11-13

### Added

- Mud: part of what flies is drops of muddy water.

## 0.6.0 - 2026-11-13

### Added

- Dust as a volume for sand and snow (needs Blender 5.3).
- Surface stage for snow; the snow shader reads disturbed snow.

### Fixed

- Seam line at the edge of the simulation field.

## Earlier

Solver v2, flying material for sand, mud and snow, surface stages for sand
and mud, material sticking to colliders, presets, live sculpting, bake and
freeze. See the git history.
