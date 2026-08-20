# GroundFX — Projektstatus

**Letzte Aktualisierung:** 2026-08-20
**Aktueller Meilenstein:** M2 (Physik) — in Arbeit
**Tests:** 32/32 grün (Blender 5.2.0 LTS, headless)

> Diese Datei ist der Wiedereinstiegspunkt. Wer den Kontext geleert hat, liest
> `STATUS.md` → `PLAN.md` → `BACKLOG.md` → `API_NOTES.md` und ist wieder im Bild.

---

## Kurzfassung

GroundFX ist ein Blender-5.2-Addon für deformierbaren Sand/Schnee/Schlamm
(2.5D-Höhenfeld-Solver in Geometry/Simulation Nodes, Einweg-Kollision, kein
Python im Frame-Loop → bake-fähig). Zwei Haupt-Use-Cases: dynamische Interaktion
(EEVEE) und Produktfoto-Hero-Shots (Cycles). Details in `PLAN.md`.

Alle Grundsatzfragen sind entschieden (siehe `OPEN_QUESTIONS.md`). Referenzvideos
sind nicht bindend, nur optionale Hilfe fürs spätere Preset-Fine-Tuning.

---

## Fertig

| Epic | Inhalt | Nachweis |
|---|---|---|
| **E0** | Installierbares Extension-Gerüst, Registry, Versions-Guard, Logging, Build-ZIP, Test-Harness | Extension installiert/aktiviert sich über echten `bl_ext`-Pfad |
| **E1** | NodeTreeBuilder, Simulation-/Repeat-Zonen-Helfer, Versionierung (`ensure_node_group`) | Sim-Zone akkumuliert Attribut über Frames korrekt |
| **E2** | Add Sand/Snow/Mud, Domain-Objekt (2×2 m), Properties, Quality-Profile, Element-Kennwerte, UI-Panels mit Live-Info | Ein Klick erzeugt fertiges Setup |
| **M1** | Minimaler Carve: bewegter Collider hinterlässt messbare Spur | Carve-Test grün |

## In Arbeit — M2 (Physik)

- **E3-S2 Böschungswinkel-Relaxation** ✅ fertig (Toppling-Solver, ±1,5° kalibriert)
- E3-S3 Aufhäufen / Bugwelle / Berm ✅ fertig (isotroper Berm; Richtung folgt in E4)
- E4 Collider-System (Mark-Operator, Proxy, **Multi-Collider** [User-Wunsch, v1], Geschwindigkeit)

## Danach

M3 (E5 Presets, E6 Quality/LOD, E7 Cache/Bake, E8 Shader, E9 UII/Drop-Tool),
M4 (E10 Spray, E13 Reifenprofil, E14 Anhaftung, E15 Schneefall, E11 QA/Doku).

---

## Wie testen / bauen

```
# Tests (headless)
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python tests/run_all.py
# oder:  powershell -File dev/run_tests.ps1

# Build-ZIP nach dist/
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python dev/build.py

# Install-Verifikation (installiert + aktiviert + deinstalliert)
"/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
  --background --factory-startup --python dev/verify_install.py -- "C:\dev\blender addon"
```

---

## Projektstruktur (Ist-Zustand)

```
groundfx/
  __init__.py            register/unregister (self-healing), Versions-Guard
  registry.py            zentrale Klassenliste + Pointer-Registrierung
  core/
    constants.py         alle Namen (Attribute gfx_*, Sockets, NG-Namen)
    ng_builder.py        deklarativer Node-Tree-Builder + Auto-Layout
    ng_zones.py          Simulation-/Repeat-Zonen-Helfer
    ng_library.py        ensure_node_group (Versionsstempel, reuse/rebuild)
    modifier_io.py       Modifier-Inputs per Socket-NAME (5.2-API gekapselt!)
    nodegroups/
      ng_ground_sim.py   Solver-Toplevel: Init → Carve → Deposit → Relax → SetPos
      ng_relax.py        Böschungswinkel-Toppling (Repeat-Zone)
      ng_deposit.py      Pile-Transport zum Rand / Berm (Repeat-Zone)
  data/
    prefs.py             AddonPreferences (Debug-Schalter)
    properties.py        GroundFXObjectSettings (obj.groundfx) + Callbacks
    quality.py           4 Qualitätsprofile + Zellgröße + Ampel
    elements.py          Physik-Kennwerte je Element
  ui/panels.py           N-Panel: Add-Buttons + Domain-Panel
  ops/op_add.py          Add-Operator (numpy-Grid, headless-fest)
tests/                   harness + test_smoke/test_builder/test_domain
dev/                     build.py, verify_install.py, run_tests.ps1, probe_*.py
docs/                    PLAN, BACKLOG, OPEN_QUESTIONS, API_NOTES, STATUS
```

## Wichtigste Fallstricke (Details in `API_NOTES.md`)

- **Modifier-Inputs (5.2):** `modifier["Socket_N"]=wert` ist WEG. Neu:
  `modifier.properties.inputs.Socket_N.value = wert` + `object.update_tag()`.
- Grid-Node heißt `GeometryNodeMeshGrid` (nicht `...InputMeshGrid`).
- AddonPreferences-Registrierung prüft man über `cls.is_registered`.
- Simulation caches pro Frame: Collider-Position VOR `frame_set` setzen, sonst
  sieht der gebakte Frame die alte Position.
- **Field-Re-Evaluation:** `InputNamedAttribute` wird gegen die durchfließende
  Geometrie neu ausgewertet. Ein Attribut, das gelesen UND geschrieben wird
  (`gfx_h`), immer ZULETZT speichern (carve/pile/comp davor).
