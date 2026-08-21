# GroundFX — Projektstatus

**Letzte Aktualisierung:** 2026-08-21
**Aktueller Meilenstein:** M3 (Workflow) — E7 in Arbeit (E4/M2-Kern fertig)
**Tests:** 143/143 grün (Blender 5.2.0 LTS, headless)

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
- **E5-S1 Elementwechsel (Physik + Material)** ✅ — Update-Callback am `element`-Enum pusht die
  Element-Physik atomar in den Solver und tauscht (seit E8) das Material mit (User-Material bleibt).
- **E5-S2 Presets** ✅ — 12 benannte Presets (4×Sand/Snow/Mud) als Datentabelle `data/presets.py`,
  Apply-Operator + Panel-Dropdown; wechselt auch das Element. JSON-Format + User-Presets (E5-T4/T9)
  aufgeschoben.
- **B2 Zacken/Spikes** ✅ **komplett** — vier Ursachen, einzeln nachgemessen:
  (1) Pile-Transport war odd-even-entkoppelt (4-Nachbar-Mittel ohne Selbst-Term) → jede zweite Zelle
  bekam exakt nichts = der Zahn-Kamm; (2) Relaxations-/Deposit-Masken lagen auf `gfx_carve`
  (Pro-Frame-Delta) und flackerten → neues Deckungs-Attribut `gfx_occ`; (3) additive Advektion +
  `max(s,0)`-Clamp erfand Masse; (4) schneller Collider legte pro Frame einen Klumpen ab (dashed
  Graben, Riffel-Periode = Weg pro Frame) → **E3-S5 Swept Carve** (s. u.). Neue Inputs
  `Deposit Spread` / `Deposit Rate` / `Carve Substeps`, `tests/test_deposit.py` +
  `tests/test_substeps.py` halten alles fest.
- **E3-S5 Substeps (Swept Carve)** ✅ — schließt B2 ab. Carve-seitiges Sub-Frame-Sampling entlang des Bewegungsvektors füllt den dashed Graben schneller Collider zu einer durchgehenden Spur; unter einer Zelle Bewegung/Frame bit-identisch (E3-T21). NG-Version 9, `Carve Substeps`-Input quality-gesteuert. Visuell verifiziert (docs/substeps_*.png).
- **E8 Shader** ✅ — prozedurale Principled-Materialien je Element (`core/materials/mat_builder.py`), Elemente = eine Zahlen-Tabelle. `gfx_comp` macht Spuren dunkler+glatter (E8-T6); Wetness-Regler bewegt Optik UND Kohäsion zugleich (E8-T7). Vier Look-Regler im Panel `GFX_PT_look`. Materialien `gfx_generated`-gestempelt → Elementwechsel tauscht nur eigene, User-Material bleibt (E8-T10). EEVEE gerendert (docs/mat_*.png). Aufgeschoben (brauchen E3-S4-Felder): Ripples/`gfx_flow`, Pfützen+Risse via `gfx_h`/`gfx_wet`, Snow-Sparkle.
- **E8 Material-Überarbeitung** ✅ (2026-08-21) — echte Struktur/Tiefe: Sand Voronoi-Körnung+Grau-Jitter+Quarz-Sparkle; Snow Voronoi-Klumpen+Kristallfacetten+Sparkle+Subsurface+Fresnel-Sheen; Mud nasser Glanz+Trockenrisse. Mehrlagige Bumps (Makro/Meso/Mikro)+Kerben-AO. docs/mat2_*.png (EEVEE). Cycles-Gegenprüfung offen (siehe Memory groundfx-verify).
- **E8 Nahaufnahme / echtes Displacement** ✅ (2026-08-21) — Materialien hatten trotz Struktur einen Plastik-Look (Bump flacht ab). Jetzt: (1) Roughness-Breakup + Sparkle-Flakes gegen den Plastik-Glanz; (2) **echtes Cycles-Displacement** — Material-Displacement-Branch (`displacement_method=BOTH`) + Toggle **Hero Detail** (`groundfx.hero_detail`, Settle-&-Freeze-Panel) fügt adaptive Subdivision nach dem Solver ein → Korn-/Kristall-/Riss-Silhouette nahe der Kamera. Nahaufnahmen (Hauptusecase) jetzt fotoreal: docs/disp_*.png. `disp_scale` pro Element. Nur Cycles echtes Displacement, EEVEE Bump.
- **P3 Live-Spur (Live Sculpt)** ✅ — modaler Operator `groundfx.live_sculpt` + Timer löst bei Collider-Bewegung EINEN Sim-Schritt aus → Spur ohne Play. Nutzt den ganzen Solver wieder; Kern `LiveStepper` (headless getestet). Toggle im Collider-Panel; Playhead wandert mit. docs/live_sculpt.png.
- **P1(a) Haften/Verfangen** ✅ — Static-Friction-Schwellwert in der Relaxation (`T_start`/`T_stop`-Hysterese, symmetrisch/massenerhaltend): Material fließt erst über `Repose + Stickiness` und bleibt so in Rillen liegen / Haufen sacken nicht flach. Neuer `Stickiness`-Input+Regler, pro Element. Stickiness 0 = altes Verhalten. NG-Version 10. Tests grün, docs/stick_high.png. **Offen P1(b):** Sand oben-auf mitreiten (Schaufel) → braucht E10/E14 Partikel/Zweitschicht.
- **E3-S4 Physik-Felder** ✅ (bis auf gfx_wet-Feld) — `gfx_comp` mit Recovery (Spuren verheilen), `gfx_age` (Frames seit Störung), `gfx_flow` (Bewegungsrichtung). Keine Physik-Rückkopplung → Solver unberührt. `gfx_flow` treibt Sand-Track-Ripples (E8-T2, docs/ripples.png). `Recovery`-Input pro Element, NG-Version 11. Offen: `gfx_wet` als räumliches Feld (Pfützen).

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
      ng_relax.py        Böschungswinkel-Toppling (Repeat-Zone), Maske auf gfx_occ
      ng_deposit.py      Pile-Transport + Bugwelle als eine normierte Gather-Maske
      ng_collider_proxy.py  Low-Poly-Stand-in (BBox/Convex Hull) via Object Info
    materials/mat_builder.py  prozedurale Principled-Materialien je Element (E8)
  ops/op_live.py         Live-Sculpt: Drag → Sim-Schritt via Timer (P3)
  data/
    prefs.py             AddonPreferences (Debug-Schalter)
    properties.py        GroundFXObjectSettings (obj.groundfx) + Callbacks
    quality.py           4 Qualitätsprofile + Zellgröße + Ampel
    elements.py          Physik-Kennwerte je Element
  ui/panels.py           N-Panel: Add-Buttons + Domain-Panel + Collider-UIList
  ops/op_add.py          Add-Operator (numpy-Grid, headless-fest)
  ops/op_collider.py     Mark/Unmark-Collider, Auto-Collider-Collection (E4-S1)
tests/                   harness + test_smoke/test_builder/test_domain/test_collider/
                         test_relax/test_deposit/test_freeze/test_presets/test_elements
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
- **Kein 4-Nachbar-Mittel ohne Selbst-Term** — das ist odd-even-entkoppelt und
  liefert garantiert einen Ein-Zell-Kamm (B2).
- **Masken nie auf einen Pro-Frame-Delta bauen** (`gfx_carve`) — sie flackern
  unter einem langsam wandernden Collider. Dafür gibt es `gfx_occ`.
- **Clamps in Transport-Stufen erfinden Masse.** Bias lieber als Gewicht in eine
  normierte Gather-Maske legen, dann braucht es keinen Clamp.
