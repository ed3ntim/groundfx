# GroundFX — Projektstatus

**Letzte Aktualisierung:** 2026-08-20
**Aktueller Meilenstein:** M3 (Workflow) — E7 in Arbeit (E4/M2-Kern fertig)
**Tests:** 71/71 grün (Blender 5.2.0 LTS, headless)

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

## In Arbeit — M2 (Physik) — Collider-Kern (E4) fertig

> Offen in M2 und bewusst nach hinten geschoben: **E3-S1** Emitter/„Rain" (Material aus der Luft
> auffüllen), **E3-S4** gfx_comp/wet/flow/age, **E3-S5** Substeps. Laut User-Priorität geht es nach
> E4 zunächst mit **M3** weiter; diese E3-Reste werden bei Bedarf nachgezogen.


- **E3-S2 Böschungswinkel-Relaxation** ✅ fertig (Toppling-Solver, ±1,5° kalibriert)
- E3-S3 Aufhäufen / Bugwelle / Berm ✅ fertig (isotroper Berm; Richtung folgt in E4-S3)
- **E4-S1 Multi-Collider** ✅ fertig — Solver raycastet gegen die vereinigte Collider-Collection
  (Collection Info → Realize → Raycast); beliebig viele Objekte carven gleichzeitig. Pro Domain
  eine Auto-Collection „<Domain> Colliders"; Mark/Unmark-Operatoren + UIList. Test: zwei Cubes
  carven simultan.
- **E4-S3 Geschwindigkeit / gerichtete Bugwelle** ✅ fertig — `gfx_carve_prev`; Bewegungsrichtung
  aus der Schwerpunkt-Verschiebung des Fußabdrucks (robust null bei Stillstand); Pile wird per
  Advektion nach vorne verlagert (`bow_wave`-Input pro Element). Test: vorne > hinten; bw=0
  symmetrisch. Schließt E3-T13 (Bugwelle) mit ab.
- **E4-S2 Proxy (High-Poly)** ✅ fertig — `ng_collider_proxy` (Bounding Box / Convex Hull), folgt
  dem Original inkl. Deformation via `Object Info`; Mark-Operator legt Proxy an, Original bleibt aus
  der Raycast-Menge. Benchmark-Test: Zielflächen 6 statt Tausende. Decimate-Proxy + BBox-Vorfilter
  (E4-T5/T7) offen.
- **E4-S4 Hero-Collider / Silhouette** ✅ fertig — Original-Modus (silhouettentreu) + Poly-Warnung;
  Supersampled Contact-Carve (5er-Quincunx, `Contact AA`, Domain-Toggle „Hero Contact"): löst die
  Abdruckkante sub-zellulär auf (Test: 0 → 88 Kanten-Zwischenzellen). AA=0 bit-identisch zum
  Einzelstrahl. Decimate-Proxy (E4-T13) aufgeschoben.
- **E4 abgeschlossen** (bis auf aufgeschobene Optimierungen E4-T5 Decimate / E4-T7 BBox-Vorfilter
  / E4-T11 Substeps→E3-S5).
- **E7-S3 Freeze-to-Mesh + E7-S4 Settle & Freeze** ✅ fertig — `ops/op_freeze.py`: Freeze-to-Mesh
  (statisches Objekt, `gfx_*`+Material erhalten), Settle-Erkennung (max |Δgfx_h| < Schwelle) mit
  Auto-Freeze, Photo-Setup (Hero-Contact + Cycles + dichtere Relaxation). Test: Ruhe erkannt @Frame 46.
- **E7-S1 Bake/Free** ✅ fertig — `ops/op_bake.py` (Bake / Bake All / Free / Free All),
  API in `compat.py` gekapselt (`simulation_nodes_cache_bake` / `..._delete`). Panel-Sektion „Cache".
- E7-S2 Cache-Info (Größe/Hash/veraltet, `.blend`-Warnung, eigene Framerange) — offen
  (unter Memory-Bake geringer Wert; zurückgestellt).
- **E5-S1 Elementwechsel (Physik)** ✅ — Update-Callback am `element`-Enum pusht die Element-Physik
  atomar in den Solver; Material-Swap folgt mit E8. Nächstes: E5-S2 Presets (JSON), E8 Shader.

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
      ng_deposit.py      Pile-Transport + gerichtete Bugwelle (Repeat-Zone)
      ng_collider_proxy.py  Low-Poly-Stand-in (BBox/Convex Hull) via Object Info
  data/
    prefs.py             AddonPreferences (Debug-Schalter)
    properties.py        GroundFXObjectSettings (obj.groundfx) + Callbacks
    quality.py           4 Qualitätsprofile + Zellgröße + Ampel
    elements.py          Physik-Kennwerte je Element
  ui/panels.py           N-Panel: Add-Buttons + Domain-Panel + Collider-UIList
  ops/op_add.py          Add-Operator (numpy-Grid, headless-fest)
  ops/op_collider.py     Mark/Unmark-Collider, Auto-Collider-Collection (E4-S1)
tests/                   harness + test_smoke/test_builder/test_domain/test_collider
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
