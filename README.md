# GroundFX

Blender-Extension (5.2 LTS) für deformierbaren **Sand, Schnee und Schlamm**:
Objekte pflügen durch das Material, davor häuft es sich an, dahinter fällt es
in sich zusammen, beim Stopp bleibt es liegen, und wo es physikalisch passt,
bleibt es **auf dem Objekt** liegen und fährt mit. Die Animation läuft live im
Viewport (Geometry-Nodes-Simulation, kein Python im Frame-Loop). Für
Nahaufnahmen gibt es Shader in echter Korngröße und eine optionale Kornebene
aus 3D-Körnern.

Autor: ed3n

## Was drin ist

| Teil | Kurz |
|---|---|
| Solver v2 | 2,5D-Höhenfeld, exakt massenerhaltender 8-Nachbar-Fluss, Multiskalen-Relaxation auf den Böschungswinkel, Bingham-Fließgrenze (Schlamm), Volumenverdrängung mit Bugwelle, Swept-Collider mit Sub-Frames |
| Zwei-Schicht-Kopplung | Material auf Collider-Oberseiten (`gfx_top`) wird mit dem Objekt advektiert und rutscht über Kanten ab |
| Sand Gen 3 | Surface-Stufe nach dem Solver: Windrippel, Relief und Krümel als echte Geometrie, feuchter Sand aus der Tiefe, optionale Umgebung bis zum Horizont. Belege: `docs/g3_sand_*.png` |
| Schlamm Gen 3 | Unebene Schlammfläche mit echten Pfützen, die auch jede Spur füllen, gequetschte Wülste, fleckiger Wasserfilm. Belege: `docs/g3_mud_*.png` |
| Look v2 | Schnee 0,8 mm (SSS, Kristallfacetten) |
| Kornebene | instanzierte Körner nur im Kamera-Frustum (`groundfx.grain_layer`), im Viewport aus |
| Workflow | Add-Menü, Presets, Collider-Collection, Live-Sculpt, Bake, Freeze-to-Mesh, Photo-Setup |

## Setup

Voraussetzung: Blender 5.2 LTS.

```sh
python dev/build.py                 # -> dist/groundfx-<version>.zip
```

In Blender: *Edit > Preferences > Get Extensions > Install from Disk* und das
ZIP wählen. Danach im 3D-Viewport *Add > GroundFX > Sand/Snow/Mud*, ein Objekt
markieren (*Mark Collider*) und abspielen.

## Tests

```sh
blender --background --factory-startup --python tests/run_all.py
```

Ausgabe endet mit `TEST:SUMMARY:<bestanden>/<gesamt>`.

## Dev-Werkzeuge

| Skript | Zweck |
|---|---|
| `dev/hero_scene.py` | Testszene (Box pflügt und stoppt), rendert nach `dev/_renders/`. Optionen `--element SAND|SNOW|MUD --cam close|wide|macro|micro --frames --samples --quality --grains --save` |
| `dev/sim_probe.py` | ms/Frame, Masse, Höhen pro Frame |
| `dev/probe_scatter.py` | prüft Join-Reihenfolge und Accumulate-Scatter |

Beispiel:

```sh
blender -b --factory-startup --python dev/hero_scene.py -- --element SNOW --cam close --frames 90
```

## Doku

- `CONTEXT.md` - Erkenntnisse, Blender-5.2-Fallstricke, laufender Kontext
- `DECISIONS.md` - Entscheidungs-Log
- `docs/BACKLOG.md` - Backlog
- `docs/STATUS.md` - Stand und Nachweise
- `docs/MARKET.md` - Marktlösungen und Procedural Materials
- `docs/g3_*.png`, `docs/v2_*.png` - Belegrenders
