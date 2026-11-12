# GroundFX - Projektstatus

**Letzte Aktualisierung:** 2026-11-12
**Tests:** 205/205 grün (Blender 5.2.0 LTS, headless)

Wiedereinstieg: diese Datei, dann `../CONTEXT.md` (Architektur, Fallstricke)
und `../DECISIONS.md`. Die Historie vor Solver v2 steht in der Git-Historie
dieser Datei, nicht mehr hier.

## Stand

| Baustein | Stand |
|---|---|
| Solver v2 | fertig. Massenerhaltend, Böschungswinkel, Bugwelle, Material auf dem Objekt |
| Look-Felder | `gfx_comp`, `gfx_flow`, `gfx_age`, neu `gfx_dist` (aufgewühlt) und `gfx_damp` (feucht, trocknet) |
| **Sand Gen 3** | fertig als erstes Element der neuen Generation: Surface-Stufe (Rippel, Relief, Krümel, Umgebung) plus Shader v3 |
| Schnee | Look v2, keine Surface-Stufe |
| **Schlamm Gen 3** | fertig: Surface-Stufe (unebene Fläche, Wülste, Spritzklumpen, stehendes Wasser) plus Shader v3 und Wasser-Shader |
| Kornebene | nur Sand, im Kamera-Frustum |
| Workflow | Add-Menü, Presets, Collider, Live-Sculpt, Bake, Freeze, Photo-Setup |

Belege Sand Gen 3: `g3_sand_hero.png`, `g3_sand_wide.png`,
`g3_sand_close.png`, `g3_sand_macro.png` (Cycles, 160 Samples, Quality High).
Belege Schlamm Gen 3: `g3_mud_hero.png`, `g3_mud_wide.png`,
`g3_mud_close.png`.
Test-ZIP: `dist/groundfx-0.4.0.zip` (lokal, nicht im Repo).

## Bekannte Schwächen

- Tiefes, langes Pflügen (4,5 cm über 57 cm) türmt den Haufen höher als eine
  20-cm-Box, dann läuft Sand auf die Oberseite. Das Volumen stimmt
  rechnerisch, die Form ist ein Plateau statt eines Grats.
- Im Viewport ungeprüft, alle Belege sind headless gerendert.
- Schnee hat noch keine Surface-Stufe.
- Schlamm: Das Wasser ist ein fester Pegel. Es wird nicht verdrängt, schwappt
  nicht und spritzt nicht. Die Spur hat harte, rechteckige Ufer.

## Performance (headless, ms/Frame, nur Solver)

| Quality | Grid | ms/Frame |
|---|---|---|
| Low | 64² | 9 |
| Medium | 128² | 21 |
| High | 256² | 45 |
| Ultra | 512² | 194 |

Gemessen vor Gen 3. Die Surface-Stufe kommt im Viewport dazu (Level 0, nur
Versatz plus Krümel) und ist noch nicht einzeln gemessen.

## Testen und bauen

```sh
blender --background --factory-startup --python tests/run_all.py
blender --background --factory-startup --python dev/build.py
blender -b --factory-startup --python dev/hero_scene.py -- --element SAND --cam wide --frames 80
```
