# Changelog

All notable changes to GroundFX. Versions follow
`groundfx/blender_manifest.toml`; each released version has a tag
`v<version>` and a ZIP on the
[releases page](https://github.com/ed3ntim/groundfx/releases).

## 0.8.7 - 2026-11-20

### Changed

- Mud splats on an object are no longer round dots: each splat is a core
  with a few smaller lobes smeared out in one direction, and its rim is
  frayed by noise.

## 0.8.6 - 2026-11-20

### Changed

- Mud lying on an object is drawn as flat, wet splats with soft round
  edges instead of the grid cells of its layer, which showed as square,
  angular flakes. A splat lies at most about a millimetre thick and runs
  out wide; very thin traces are left out.

## 0.8.5 - 2026-11-20

### Fixed

- Thin towers of material under objects that do not touch the ground
  everywhere (a rifle lying in mud: under its stock and barrel). The volume
  an object pushes aside no longer lands in the cells under it, where it
  was never spread out again.
- Sharp cones along the flank of an object on fine grids (Ultra): the
  ground now also trades material between cells 8 and 16 apart, so a
  frame's bow wave becomes a rounded bank within the frame. Material lying
  on an object spreads across its top the same way.

## 0.8.4 - 2026-11-17

### Changed

- Mud: drops and clots take their shape from their flight. Each points
  along its current direction, which bends with the arc, with a round head
  in front and a tail behind, and stretches with its speed: round when
  slow, up to about twice as long as wide when fast. Drops of muddy water
  are smooth bodies now as well, the clots keep a ragged section and a
  little scatter in their heading.

## 0.8.3 - 2026-11-17

### Changed

- Mud: thrown pieces wear the ground's own mud shader, churned and soaked,
  so they have the colour, grain and wet film of the mass they were torn
  from. Drops of muddy water are dark and glossy like wet mud instead of
  milky beige.

## 0.8.2 - 2026-11-17

### Changed

- Mud: thrown pieces look like splashes instead of moulded drops. Each
  piece has a ragged, flattened cross-section turned its own way, clots
  point in all directions around the flight, there are many small pieces
  and a few big lumps, fewer and shorter strings, and the surface is wet
  but no longer glazed.

## 0.8.1 - 2026-11-17

### Changed

- Mud: thrown mud no longer flies as balls. Clots leave as rounded
  teardrops with a tail, and about a quarter of the pieces tear into
  sagging strings that stretch the longer they fly and finally snap. Drops
  of muddy water stay round. The viewport shows the strings at a lower
  resolution.

## 0.8.0 - 2026-11-16

### Added

- Mud: the standing water moves. An object below the water table pushes
  the water up where it goes in and leaves a trough where it comes out;
  the waves run through the puddles and tracks at the speed of shallow
  water and calm down within a second or two. New setting `Waves` next to
  the water level (0 keeps the water still).

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
