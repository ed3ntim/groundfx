# GroundFX — Backlog

**Struktur:** Epic → User Story → Tasks
**Schätzung:** S ≈ ½ Arbeitseinheit · M ≈ 1 · L ≈ 2–3 · XL ≈ 4+
**Priorität:** P0 = MVP-blockierend · P1 = für Release 1.0 nötig · P2 = nice-to-have · P3 = Forschung

Meilenstein-Zuordnung: M1 = E0–E2, M2 = E3–E4, M3 = E5–E9, M4 = E10, E13–E15, E11, E12 offen.

## Offene Beobachtungen / Solver-Qualität (User-Feedback 2026-08-21)

- [x] **B1 Senkrechte Wände am Collider** — GELÖST: (1) Kohäsion skaliert jetzt mit der Zellgröße
  (Steigungs-Yield statt absoluter Höhe) → Wände slumpen auf ~34° statt 62°; (2) Relaxation blockt
  Fluss in vom Collider besetzte Zellen → Berm bleibt stehen statt ins Loch zu rinnen. NG-Version 7.
  Verifiziert: nach Abheben max|dh|≈0.0096 (≈34°), Berm-Höhe hält. Details in API_NOTES.
- [x] **B2 Bugwelle spiky / Anti-Kriechen** — größtenteils GELÖST, drei Ursachen gefunden und
  einzeln nachgemessen (Details in API_NOTES):
  1. **Schachbrett-Kamm:** Der Pile-Transport mittelte nur über die 4 Nachbarn ohne Selbst-Term →
     odd-even-entkoppelt, jede zweite Zelle bekam **exakt nichts**. Das war der Zahn-Kamm.
     Fix: `Deposit Spread` (Selbst-Anteil bleibt liegen). Schachbrett 0.174 mm → 0.002 mm.
  2. **Flackernde Maske:** Relaxation und Deposit maskierten über `gfx_carve` (Pro-Frame-Delta) →
     riffelte die Grabensohle (`20 27 20 28 …`). Fix: neues `gfx_occ` (Deckung 0..1 aus dem
     Quincunx-Raycast). Sohle danach exakt flach.
  3. **Massen-Erfindung:** additive Advektion + `max(s,0)`-Clamp erzeugte Material (Feld explodierte
     auf 2.8 m bei höherer Transportweite). Fix: Bias als Gewicht in der normierten Gather-Maske,
     Clamp entfällt. Test `test_carving_never_creates_material` hält das fest.
  Neue Group-Inputs: `Deposit Spread`, `Deposit Rate`. NG-Version 8. Tests: 85/85.
- [x] **B2-Rest: Klumpen pro Frame bei schnellem Collider** — GELÖST via E3-S5 Swept Carve (s. u.).
  Der dashed Graben (eine Rippe pro Frame, Periode = Weg pro Frame) wird durch Sub-Frame-Abtastung
  entlang der Bewegung zu einer durchgehenden Spur gefüllt. Visuell verifiziert
  (docs/substeps_1_dashed.png vs substeps_3_filled.png).
- [x] **B3 Collider per Picker hinzufügen** — Objekt-Auswahlfeld (Pipette) im Panel statt nur über
  Selektion. → umgesetzt (`collider_pick`).
- [x] **B4 Presets nach Element vorfiltern** — Preset-Dropdown zeigt nur Presets des aktiven Elements.

## User-Punkte (2026-08-21, nach E8)

- [x] **P3 Live-Spur ohne Timeline** — Collider im Viewport ziehen zeigt die Spur sofort, ohne Play.
  Modaler Operator `groundfx.live_sculpt` mit Timer: bei Collider-Bewegung wird EIN Sim-Frame-Schritt
  ausgelöst (Range auto-verlängert). Nutzt den kompletten bestehenden Solver wieder (inkl. B2/Swept
  Carve), statt Physik in Python zu duplizieren. Toggle-Button im Collider-Panel. Playhead wandert dabei
  mit (= faktisch eine Animation, ausgelöst durchs Ziehen); Scrub auf Startframe = Reset. Kern in
  `LiveStepper`, headless getestet (`tests/test_live.py`). Visuell: docs/live_sculpt.png.
- [~] **P1 Anhaftung / Verfangen (gestuft)**
  - [x] **(a) Haften/Verfangen im Höhenfeld** — Static-Friction-Schwellwert in der Relaxation:
    Material fließt erst, wenn die Steigung `Repose + Stickiness*cell` überschreitet, und relaxiert
    dann zurück Richtung Repose (Hysterese über zwei Schwellen `T_stop`/`T_start`, symmetrisch →
    massenerhaltend). Effekt: Material bleibt in Rillen/Ritzen liegen, Haufen sacken nicht flach.
    Neuer `Stickiness`-Input + Regler, pro Element (Sand 0.05 / Snow 0.25 / Mud 0.4). Stickiness 0 =
    exakt altes Verhalten (Repose-Kalibrierung unberührt). NG-Version 10. Tests
    `test_stickiness_holds_a_steeper_slope`, `test_zero_stickiness_matches_plain_repose`.
  - [ ] **(b) Oben-auf mitreiten (Schaufel)** — sprengt 2.5D: Sand liegt AUF dem Collider und wird
    mitgehoben → Partikel-/Zweitschicht (E10/E14). Aufgeschoben.

**Rahmen (entschieden am 2026-08-20):** Addon-Name `GroundFX` · Höhenfeld + Spray (Modell B) ·
nur Einweg-Kollision · UI und Code Englisch, Doku Deutsch · Nahaufnahme-Maßstab, Default-Domain
2 × 2 m.

---

## E0 · Projekt-Setup und Infrastruktur `M1` `P0`

### E0-S1 — Als Entwickler will ich ein installierbares Extension-Gerüst, um von Anfang an in Blender testen zu können. `M`

**Akzeptanz:** `GroundFX` erscheint in Blenders Extension-Liste, lässt sich aktivieren und deaktivieren, ohne Fehler in der Konsole; ein Dummy-Panel ist sichtbar.

- [ ] E0-T1 `blender_manifest.toml` (id, version, blender_version_min, permissions, license)
- [ ] E0-T2 Paketstruktur samt `__init__.py` mit sauberem `register()` / `unregister()`
- [ ] E0-T3 Zentrale Registry-Liste aller Klassen (eine Registrierungsquelle, kein verstreutes `register_class`)
- [ ] E0-T4 Versions-Guard: klare Fehlermeldung bei Blender < Mindestversion statt Traceback
- [ ] E0-T5 Logging-Modul mit Debug-Schalter in den Addon-Preferences

### E0-S2 — Als Entwickler will ich schnelle Iteration ohne Blender-Neustart. `S`

- [ ] E0-T6 Reload-freundliche Modulstruktur (`importlib.reload`-Kette)
- [ ] E0-T7 Build-Skript: ZIP für Extension-Installation erzeugen
- [ ] E0-T8 `dev/install_local.py` — Addon direkt ins Blender-Extensions-Verzeichnis symlinken/kopieren

### E0-S3 — Als Entwickler will ich headless testen können, damit Regressionen sofort auffallen. `M`

**Akzeptanz:** `blender --background --python tests/run_all.py` läuft durch und liefert einen Exit-Code.

- [ ] E0-T9 Test-Harness (Discovery, Reporting, Exit-Code)
- [ ] E0-T10 Smoke-Test: Addon registrieren, Sand hinzufügen, Sim 10 Frames auswerten, deregistrieren
- [ ] E0-T11 `dev/run_tests.ps1` als Einzeiler für Windows

---

## E1 · Node-Group-Framework `M1` `P0`

### E1-S1 — Als Entwickler will ich Node-Trees deklarativ in Python bauen, damit sie diffbar und wartbar sind. `L`

**Akzeptanz:** Eine Node-Group aus ~20 Nodes entsteht aus einer deklarativen Beschreibung, ist im Editor lesbar angeordnet und verlinkt korrekt.

- [ ] E1-T1 `NodeTreeBuilder`: Node-Erzeugung, Default-Werte, Link-Helper
- [ ] E1-T2 Interface-Helper für Input-/Output-Sockets (Typ, Min/Max, Default, Subtype, Tooltip)
- [ ] E1-T3 Auto-Layout: Spalten nach Topologie, Frames mit Beschriftung
- [ ] E1-T4 Helfer für Simulation Zone und Repeat Zone (Zonen-Paare korrekt anlegen, State-Items verwalten)
- [ ] E1-T5 Unit-Test: Builder erzeugt erwartete Node- und Link-Anzahl

### E1-S2 — Als User will ich, dass meine alten Szenen nach einem Addon-Update weiter funktionieren. `M`

- [ ] E1-T6 Versionsstempel als Custom Property auf jeder Node-Group
- [ ] E1-T7 `ensure_node_group()`: vorhanden und aktuell → wiederverwenden, sonst neu bauen
- [ ] E1-T8 Migration: Parameterwerte beim Rebuild über Namen (nicht Index) retten
- [ ] E1-T9 Operator „Node-Setups reparieren / neu aufbauen" für Notfälle

---

## E2 · Domain- und Ground-System `M1` `P0`

### E2-S1 — Als User will ich mit einem Klick eine Sandfläche in der Szene haben. `M`

**Akzeptanz:** „Add Sand" erzeugt ein benanntes Objekt mit Grid, GN-Modifier, Material und sinnvollen Defaults, ausgerichtet am 3D-Cursor.

- [ ] E2-T1 Operator `groundfx.add_ground(element)` samt Undo-Support
- [ ] E2-T2 Domain-Objekt: Grid, korrekte Skalierung, Objekt-Custom-Props
- [ ] E2-T3 Integration ins `Add`-Menü und ins N-Panel
- [ ] E2-T4 Auto-Benennung und Collection-Organisation (`GroundFX` Collection)

### E2-S2 — Als User will ich, dass das Material sich an vorhandenes Terrain anpasst. `M` ✅ (E2-T8 offen)

- [x] E2-T5 Terrain-Slot (`groundfx.terrain`, PointerProperty) im Domain-Panel
- [x] E2-T6 Grid wird beim Rebuild einmalig aufs Terrain geraycastet (BVH, nach unten), Vertex-Z = Treffer → `gfx_base` = Terrain-Höhe. Kein Per-Frame-Cost (`conform_grid_to_terrain`)
- [x] E2-T7 Fallback flache Ebene, wenn kein Terrain gesetzt (Standard); Punkte, die das Terrain verfehlen, bleiben flach
- [ ] E2-T8 Rand-Verhalten: offen (Material fällt hinaus) oder geschlossen (Wanne) — offen

### E2-S3 — Als User will ich sehen, wie fein mein Setup wirklich ist. `S`

- [ ] E2-T9 Live-Anzeige: Auflösung, Vertexzahl, Zellgröße in cm
- [ ] E2-T10 Warnung, wenn die Zellgröße zu grob für das gewählte Preset ist

---

## E3 · Solver-Kern `M2` `P0`

### E3-S1 — Als User will ich Material auf die Szene fallen lassen. `L`

**Akzeptanz:** Ein Emitter füllt die Domain sichtbar über die Zeit; Rate, Radius und Falloff wirken unmittelbar.

- [ ] E3-T1 `ng_deposit`: Emitter-Objekt, radialer Falloff, Rate pro Sekunde (framerate-unabhängig)
- [ ] E3-T2 Modus „Fill" (Starthöhe sofort) und „Rain" (gleichmäßig über die Fläche, für Schnee)
- [ ] E3-T3 Start-/Endframe der Emission
- [ ] E3-T4 Mehrere Emitter über eine Collection

### E3-S2 — Als User will ich, dass Material im materialtypischen Winkel nachrieselt. `XL`

**Akzeptanz:** Eine Materialsäule kollabiert zu einem Kegel, dessen gemessener Flankenwinkel innerhalb ±3° des eingestellten Böschungswinkels liegt. Automatisierter Test.

- [x] E3-T5 `ng_relax`: Repeat Zone mit slope-limitierter Relaxation (Toppling, nicht Blur)
- [x] E3-T6 Kohäsions-Schwelle (Bingham-Fließkriterium) — als `cohesion` in der Schwelle T
- [x] E3-T7 Fließrate/Viskosität als Dämpfung + Iterationszahl
- [~] E3-T8 `conserve_mass`-Modus über symmetrischen Nachbaraustausch — Grundfluss ist bereits
  symmetrisch/massenerhaltend; exakter Modus mit h≥0-Ausgleich später (High/Ultra)
- [x] E3-T9 Stabilität: Clamping gegen Oszillation (`_STABILITY=0.25`)
- [x] E3-T10 Test: Böschungswinkel-Messung (Kegel-Kollaps, ±1,5° erreicht bei ±3° Toleranz).
  Massebilanz-Test noch offen → E3-T10b
- [ ] E3-T10b Test: Massebilanz über 100 Frames (< 2 % Abweichung)

### E3-S3 — Als User will ich, dass verdrängtes Material realistisch aufgehäuft wird. `L`

- [x] E3-T11 `ng_deposit`: Pile-Puffer, Transport zum Rand (isotrop; Richtung folgt in E4)
- [x] E3-T12 `displacement_ratio` als Group-Input (Aufhäufen vs. Verdichten)
- [x] E3-T13 Gerichtete Bugwelle — in E4-S3 umgesetzt (Pile-Advektion in Collider-Bewegungsrichtung)
- [x] E3-T14 Ablage nur außerhalb des Colliders (free-Maske carve<eps)

### E3-S4 — Als User will ich Verdichtung und Feuchtigkeit als sichtbare Effekte. `M` ✅ (bis auf gfx_wet-Feld)

- [x] E3-T15 `gfx_comp` baut unter dem Collider auf und **fällt** per `Recovery`-Rate wieder ab
  (Spuren verheilen; Schnee rieselt zu). Pro Element. Test `test_compaction_recovers_over_time`.
- [ ] E3-T16 `gfx_wet` als *Feld* mit Diffusion (Pfützen) — offen. Wetness ist bisher global
  (Regler koppelt an Kohäsion, E8-T7); ein räumliches Feld folgt, wenn Senken/Pfützen dran sind.
- [x] E3-T17 `gfx_flow` (Einheits-Bewegungsrichtung pro Zelle) aus der Footprint-Schwerpunkt-
  Verschiebung; treibt die Track-Ripples im Sand-Shader (E8-T2). Test `test_flow_points_along_the_drag`.
- [x] E3-T18 `gfx_age` (Frames seit letzter Störung; 0 unter Collider, sonst +1).
  Test `test_age_zero_under_collider_grows_elsewhere`.

### E3-S5 — Als User will ich Substeps für stabile schnelle Bewegungen. `M` ✅

- [x] E3-T19/T20 **Swept Carve** statt Substep-Schleife über die *ganze* Kette. Die Instabilität
  saß allein im Carve-Sampling (Pile entsteht nur, wo der Collider *diesen* Frame schneidet), nicht
  in Relax/Deposit — die dreimal laufen zu lassen wäre 3× teurer und würde das Falsche kurieren.
  Stattdessen: die aktuelle Schnitt-Tiefe an ein paar Sub-Frame-Positionen entlang des
  Bewegungsvektors abtasten (Sample Index auf Zell-Offset `v/cell·t/T`, Minimum) → durchgehender
  Graben. Kein Geometrie-Move nötig (Eindrücken schneidet auf feste Unterseite, Tiefe an
  Zwischenposition = Tiefe einen Bewegungsvektor zurück). Tap-Zahl = `Carve Substeps` (quality:
  Low/Med 1, High 2, Ultra 3). NG-Version 9.
- [x] E3-T21 Test: `tests/test_substeps.py` — unter einer Zelle Bewegung/Frame **bit-identisch** bei
  1 vs. 3 Substeps (Offsets runden auf 0); bei schnellem Drag halbiert 3 Substeps die
  Grabensohlen-Riffelung mindestens (gemessen ~0.9→~0.2 mm). Damit ist **B2 komplett**.

---

## E4 · Collider-System `M2` `P0`

### E4-S1 — Als User will ich beliebige Objekte per Knopfdruck zu Collidern machen. `M`

**Akzeptanz:** Markierte Objekte hinterlassen sofort Spuren, ohne dass etwas am Node-Setup angefasst werden muss.

> **Explizit vom User gewünscht (2026-08-20):** mehrere Objekte gleichzeitig kollidieren.
> Ist Kernbestandteil dieser Story (Collider-Collection) und landet damit in **v1**, nicht
> erst v2. Der aktuelle M1-Solver unterstützt nur einen Collider; E4 hebt das auf beliebig viele.

- [x] E4-T1 Operator „Als Collider markieren / entfernen" (Multi-Select) — `ops/op_collider.py`
- [x] E4-T2 Collider-Collection pro Domain, automatisch angelegt („<Domain> Colliders" unter GroundFX)
- [~] E4-T3 UIList mit Collidern (Status/Proxy-Typ/Offset pro Collider folgt mit E4-S2/S3)
- [x] E4-T4 Instanzen und animierte Objekte — Collection Info (RELATIVE) wertet den Depsgraph
  aus, Realize Instances löst Instanzen auf → beides trifft automatisch
- [x] E4-T17 Raycast gegen die vereinigte Collider-Collection (Collection Info → Realize
  Instances → Raycast Target) statt gegen ein Einzelobjekt. API in `dev/probe_collection_raycast.py` verifiziert.

### E4-S2 — Als User will ich, dass auch High-Poly-Charaktere performant bleiben. `L`

**Akzeptanz:** Ein Charakter mit 500 k Tris kostet mit Proxy weniger als 20 % der Zeit ohne Proxy.

- [~] E4-T5 Proxy-Generator — Bounding Box + Convex Hull als GN-Group (`ng_collider_proxy.py`);
  Decimate offen (kein GN-Node, später als Mesh-Copy+Decimate-Modifier)
- [x] E4-T6 Proxy folgt dem Original inkl. Armature/Deformation — via `Object Info` (evaluierte
  Geometrie), ganz ohne Constraints/Bake
- [ ] E4-T7 Bounding-Box-Vorfilter im Node-Tree — separate Solver-Optimierung; der Proxy liefert
  bereits den Hauptgewinn (aufgeschoben)
- [x] E4-T8 Benchmark-Test: BBox-Proxy reduziert die Raycast-Zielflächen massiv (6 statt Tausende)
  und carvt weiterhin; Original bleibt aus der Raycast-Menge

### E4-S4 — Als User will ich für Produktfotos einen exakten Abdruck der Objekt-Silhouette. `M` `P1`

**Akzeptanz:** Eine Waffe/ein Produkt, in Sand gedrückt, hinterlässt einen Abdruck, dessen Kante
im Nahaufnahme-Maßstab der echten Objektkontur folgt (kein sichtbares Facettieren durch einen zu
groben Proxy).

- [ ] E4-T13 Silhouettentreuer Decimate-Proxy (Außenkanten erhalten) — aufgeschoben (kein GN-Decimate;
  der Hero-Modus mit Originalgeometrie deckt Silhouettentreue bereits ab)
- [x] E4-T14 „Hero Collider" — Original-Modus nutzt die Geometrie direkt (silhouettentreu);
  Poly-Warnung beim Markieren über `HERO_POLY_WARN` (Vorschlag Proxy)
- [x] E4-T15 Kontaktzone feiner sampeln — Supersampled Contact-Carve (5er-Quincunx, `Contact AA`);
  domain-Toggle „Hero Contact". AA=0 bit-identisch zum Einzelstrahl (keine Mehrkosten im Normalfall)
- [x] E4-T16 Test: gedrehter flach-unterseitiger Cube — ohne AA binäre Kante (0 partielle Zellen),
  mit AA anti-aliaste Silhouette (88 Kanten-Zwischenzellen), Abdrucktiefe innen gleich

### E4-S3 — Als User will ich, dass schnelle Objekte durchgehende Spuren erzeugen. `M`

- [x] E4-T9 Geschwindigkeit ableiten — `gfx_carve_prev` gespeichert; Bewegungsrichtung aus der
  Schwerpunkt-Verschiebung des Fußabdrucks (centroid(carve) − centroid(carve_prev)), robust null
  bei stehendem Collider (Attribute Statistic + Selection)
- [x] E4-T10 Richtungsabhängige Verdrängung — Pile-Advektion in Bewegungsrichtung (`bow_wave`-Input,
  pro Element gesetzt: Sand 0.7 / Snow 0.6 / Mud 0.45). Test: vorne > hinten, bw=0 symmetrisch
- [ ] E4-T11 Lückenfüllung bei schneller Bewegung über Substeps → hängt an E3-S5 (Substep-Infra)
- [x] E4-T12 Einstellbarer Collider-Offset (Penetrationstoleranz) — `IN_COLLIDER_OFFSET` (seit M1)

---

## E5 · Elemente und Presets `M3` `P0`

### E5-S1 — Als User will ich zwischen Sand, Schnee und Schlamm wechseln, ohne Parameter zu kennen. `M`

- [x] E5-T1 Element-Enum mit vollständigem Parametersatz je Element (`data/elements.py`)
- [~] E5-T2 Elementwechsel tauscht **Physik** atomar (Update-Callback pusht repose/cohesion/flow/
  bow_wave); Material-Swap folgt mit E8
- [ ] E5-T3 Warnung, wenn dabei manuelle Anpassungen verloren gehen — offen

### E5-S2 — Als User will ich fertige Presets, die sofort gut aussehen. `L`

**Akzeptanz:** Mindestens acht Presets, jedes mit Beschreibung, sichtbar unterschiedlichem Verhalten und dokumentierten Kennwerten.

- [ ] E5-T4 JSON-Preset-Format + Schema-Validierung — aufgeschoben (aktuell Datentabelle
  `data/presets.py`; Externalisierung später)
- [x] E5-T5 Sand: Fine Dry Sand · Coarse Sand · Wet Sand · Beach Sand
- [x] E5-T6 Snow: Dry Powder · Packed Snow · Heavy Wet Snow · Fresh Fluff
- [x] E5-T7 Mud: Thick Mud · Thin Mud · Wet Clay · Slush
- [x] E5-T8 Operator „Preset anwenden" (`ops/op_preset.py`, Dropdown im Panel; Kennwert-Vorschau später)
- [ ] E5-T9 User-Presets speichern/löschen (Config-Ordner) — aufgeschoben (mit E5-T4)

---

## E6 · Qualitätsstufen und LOD `M3` `P0`

### E6-S1 — Als User will ich mit einem Regler zwischen schnell und schön wählen. `M` ✅

**Akzeptanz:** Die vier Stufen unterscheiden sich messbar gemäß der Budget-Tabelle in `PLAN.md`; der Wechsel benötigt keinen Neuaufbau der Szene.

- [x] E6-T1 Qualitätsprofile als Datentabelle (`data/quality.py`: Auflösung, Iterationen, Substeps, Spray-Cap, LOD)
- [x] E6-T2 `groundfx.rebuild_grid` wendet Quality+Domain-Size aufs aktive Objekt an (baut Grid neu, re-pusht cell_size/grid_n/relax/substeps, Material bleibt erhalten)
- [x] E6-T3 Auflösungswechsel = neues Mesh → Sim startet neu; Panel warnt „Grid outdated" + „Rebuild"-Button (`grid_is_current`)
- [x] E6-T4 UI-Anzeige: Auflösung/Verts, Zellgröße-Ampel, ms-Schätzung + gemessene ms (E6-S3)

### E6-S2 — Als User will ich flüssiges Viewport-Feedback trotz hoher Renderqualität. `M`

- [ ] E6-T5 Getrennte Viewport-/Render-Pfade über `Is Viewport`
- [ ] E6-T6 Display-Subdivision und Detail-Displacement erst nach der Sim
- [ ] E6-T7 Optionale Distance-LOD-Ausdünnung für die Anzeige
- [ ] E6-T8 „Solo Sim"-Modus: Shading vereinfachen während des Scrubbings

### E6-S3 — Als User will ich Messwerte statt Bauchgefühl. `M` ✅ (E6-T10 Doku-Tabelle offen)

- [x] E6-T9 Benchmark-Operator `groundfx.benchmark`: misst Median-ms/Frame über N Frames, schreibt `measured_ms` auf die Domain, Panel-Button „Measure" + Anzeige
- [ ] E6-T10 Ergebnisse der vier Stufen in der Doku festhalten
- [x] E6-T11 Warnung (Report + rotes Icon), wenn gemessen > 2× Budget der Qualitätsstufe

### E6-S4 — Als User will ich große Szenen abdecken, ohne eine riesige Domain zu bauen. `L` `P3`

*Wegen des Nahaufnahme-Fokus (Default-Domain 2 m) von P2 auf P3 herabgestuft — erst relevant,
wenn doch größere Szenen dazukommen.*

- [ ] E6-T12 „Follow Object"-Domain: Domain bewegt sich mit dem Fahrzeug/Charakter mit
- [ ] E6-T13 Höhenfeld beim Verschieben korrekt umindizieren (Scroll ohne Sprung)
- [ ] E6-T14 Mehrere Domains nebeneinander ohne sichtbare Naht

---

## E7 · Caching und Baking `M3` `P0`

### E7-S1 — Als User will ich die Simulation backen, um sie flüssig abzuspielen. `L`

**Akzeptanz:** Bake über die Szenen-Framerange, danach Wiedergabe in Echtzeit; nach `Free` läuft wieder die Live-Sim.

- [x] E7-T1 Bake-Operator (aktives Objekt) — `ops/op_bake.py`, API gekapselt in `compat.py`
  (`simulation_nodes_cache_bake`)
- [x] E7-T2 Bake All für alle GroundFX-Domains (Fortschrittsanzeige später)
- [x] E7-T3 Free / Free All — `simulation_nodes_cache_delete` (Operator heißt `_delete`, nicht `_free`)
- [~] E7-T4 Cache-Pfad relativ zur `.blend` — aktuell Memory-Bake; Disk-Cache-Pfad aufgeschoben

### E7-S2 — Als User will ich sehen, was mein Cache kostet und ob er noch gültig ist. `M`

- [ ] E7-T5 Cache-Größe auf Platte anzeigen
- [ ] E7-T6 Parameter-Hash → Status „aktuell / veraltet"
- [ ] E7-T7 Warnung bei ungespeicherter `.blend` (relativer Pfad nicht auflösbar)
- [ ] E7-T8 Eigene Bake-Framerange abweichend von der Szene

### E7-S3 — Als User will ich ein Sim-Ergebnis als statisches Mesh einfrieren. `M`

- [x] E7-T9 „Freeze to Mesh": aktueller Frame → neues statisches Objekt (`new_from_object`,
  `preserve_all_data_layers`), live-Domain wird versteckt
- [x] E7-T10 Materialübernahme + Attributerhalt (alle `gfx_*` bleiben auf dem Frozen-Mesh)

### E7-S4 — Als Produktfotograf will ich einen „Settle & Freeze"-Workflow für Hero-Shots. `M` `P1`

**Akzeptanz:** Ein Objekt fällt/wird in Sand gedrückt; das Addon simuliert bis zum Ruhezustand,
erkennt den Stillstand und friert automatisch auf ein rendfertiges High-Res-Mesh ein.

- [~] E7-T11 „Photo"-Setup-Operator: Hero-Contact an, Cycles, dichtere Relaxation. Höhere Auflösung
  (Quality) + Substeps als Hinweis (Regrid = E6, Substeps = E3-S5)
- [x] E7-T12 Ruhezustand-Erkennung: max |Δgfx_h| pro Frame < Schwelle → „settled" (numpy `foreach_get`)
- [x] E7-T13 Auto-Freeze auf den Ruheframe (Frozen-Mesh ohne Solver; Live-Domain versteckt → schnelles Look-Dev)
- [~] E7-T14 Anti-Kriechen: Settle-Schwelle stoppt sauber; Kohäsions-Yield begrenzt Restfluss (ok für v1)
- [x] E7-T15 Turntable-tauglich: Frozen-Mesh ist ein statisches Objekt mit Materialien, frei rotierbar

---

## E8 · Shader `M3` `P0`

### E8-S1 — Als User will ich Materialien, die ohne Nacharbeit gut aussehen. `L` ✅

- [x] E8-T1 `mat_builder`: gemeinsame Bausteine (Object-Coords-Noise, Wetness-Mix, Detail-Bump, Track-Darken) — eine Principled-Kette, Elemente unterscheiden sich nur in `LOOKS`-Tabelle
- [x] E8-T2 Sand: Körnung + Farbvariation (zwei Töne über Noise) + **Track-Ripples** transversal zu `gfx_flow`, per `gfx_comp` auf die Spur maskiert (docs/ripples.png)
- [x] E8-T3 Schnee: hell, leicht bläuliche Nass-/Track-Farbe, Subsurface-Weight, **Sparkle** (hochfrequentes Voronoi senkt die Roughness in winzigen Facetten → Glitzern unter hartem Licht; Cycles + EEVEE, docs/snow_sparkle.png). Bläue-in-Senken (braucht `gfx_h`-Auswertung) später
- [x] E8-T4 Schlamm: nasser Glanz (Specular ↑, Roughness ↓ mit Wetness), dunkel. Pfützen-in-Senken + Trockenrisse aufgeschoben (brauchen `gfx_h`/`gfx_wet`-Felder → E3-S4)

### E8-S2 — Als User will ich, dass der Shader auf die Physik reagiert. `M` ✅ (gfx_comp; Rest → E3-S4)

- [x] E8-T5 Attribut-Anbindung: `gfx_comp` (Track) angebunden — das einzige heute vom Solver erzeugte Feld. `gfx_wet`/`gfx_flow`/`gfx_h`-Bindung folgt, sobald E3-S4 die Felder liefert
- [x] E8-T6 Spuren dunkler + glatter über `gfx_comp` (visuell verifiziert, docs/mat_*.png)
- [x] E8-T7 Wetness-Regler: verdunkelt/glänzt die Optik UND hebt die Solver-Kohäsion (`_effective_cohesion`, Test `test_wetness_moves_look_and_physics`)

### E8-S3 — Als User will ich die Optik schnell anpassen können. `S` ✅

- [x] E8-T8 Panel `GFX_PT_look`: Base Color, Roughness, Detail, Wetness
- [x] E8-T9 EEVEE (Bump) + Cycles (echtes adaptives Displacement via Hero-Detail-Toggle) beide gerendert; Displacement nur wo sinnvoll (Cycles-Nahaufnahme, docs/disp_*.png)
- [x] E8-T10 Materialien sind als `gfx_generated` gestempelt; Elementwechsel tauscht nur ein gestempeltes Material, ein eigenes bleibt unberührt (Test `test_user_material_is_never_overwritten`)

---

## E9 · UI und Workflow `M3` `P0`

### E9-S1 — Als User will ich alles an einer Stelle bedienen. `L`

- [ ] E9-T1 N-Panel mit den Sektionen aus `PLAN.md` §7
- [ ] E9-T2 Spiegel-Panel in den Physics-Properties
- [ ] E9-T3 Kontextsensitivität: nur relevante Optionen sichtbar
- [ ] E9-T4 Tooltips für jeden Parameter, inklusive Performance-Hinweis
- [ ] E9-T5 Eigene Icons

### E9-S2 — Als User will ich das „Drop"-Erlebnis aus dem Video. `L`

**Akzeptanz:** Vom Klick bis zum fallenden, auf Collider reagierenden Material vergehen weniger als fünf Sekunden Nutzerinteraktion.

- [ ] E9-T6 Modaler Operator: Klick setzt Position, Ziehen setzt Radius, Mausrad setzt Rate
- [ ] E9-T7 Viewport-Overlay (GPU-Draw) für den Emitter-Radius
- [ ] E9-T8 Auto-Setup: Domain anlegen falls keine da, Emitter erzeugen, Wiedergabe starten
- [ ] E9-T9 Sichtbare Objekte optional automatisch als Collider markieren
- [ ] E9-T10 Abbruch per Escape stellt den Ausgangszustand wieder her

### E9-S3 — Als User will ich nicht in Fehlerzustände laufen. `M`

- [ ] E9-T11 Validierung: keine Domain, kein Collider, ungespeicherte Datei, extreme Werte
- [ ] E9-T12 Verständliche Meldungen statt Tracebacks
- [ ] E9-T13 Konsistentes Undo über alle Operatoren

---

## E10 · Spray- und Partikel-Layer `M4` `P1`

### E10-S1 — Als User will ich aufspritzendes Material für mehr visuellen Impact. `XL`

**Akzeptanz:** Bei schneller Collider-Bewegung entsteht sichtbarer Spray; die Partikel landen wieder im Höhenfeld; Kosten bleiben unter dem Budget der jeweiligen Qualitätsstufe.

- [ ] E10-T1 `ng_spray`: Simulation Zone mit Punkten, Emission proportional zur Carve-Rate
- [ ] E10-T2 Ballistische Integration mit Gravitation und Luftwiderstand
- [ ] E10-T3 Kollision gegen das Höhenfeld (Lookup statt Raycast)
- [ ] E10-T4 Rückkopplung: gelandete Partikel erhöhen `gfx_h` (Masseerhalt)
- [ ] E10-T5 Harte Obergrenze der Partikelzahl je Qualitätsstufe, ältestes zuerst löschen
- [ ] E10-T6 Darstellung: Point Cloud (Cycles) beziehungsweise Instanzen (EEVEE)
- [ ] E10-T7 Staub-Variante für Pulverschnee und trockenen Sand (Volumen oder Billboards)

---

## E11 · QA, Benchmarks, Doku, Release `M4` `P1`

### E11-S1 — Als Entwickler will ich Regressionen automatisch erkennen. `L`

- [ ] E11-T1 Physik-Tests: Böschungswinkel, Massebilanz, Spurtiefe, Stabilität
- [ ] E11-T2 API-Tests: Registrierung, alle Operatoren, Preset-Roundtrip, Bake-Roundtrip
- [ ] E11-T3 Performance-Regressionstest gegen die Budget-Tabelle
- [ ] E11-T4 Testszenen-Generator (Würfel, Kugel, Fahrzeug, Charakter)

### E11-S2 — Als User will ich verstehen, was die Regler tun. `M`

- [ ] E11-T5 README samt Installation und Schnellstart
- [ ] E11-T6 Parameter-Referenz mit Physikbezug und Performance-Auswirkung
- [ ] E11-T7 Performance-Guide (die dokumentierten Qualitätsstufen-Messwerte)
- [ ] E11-T8 Troubleshooting (Material verschwindet, Spur zu flach, Cache veraltet …)

### E11-S3 — Als User will ich sofort loslegen können. `M`

- [ ] E11-T9 Beispielszene je Element
- [ ] E11-T10 Release-ZIP, Versionierung, Changelog
- [ ] E11-T11 Lizenz und Attributionen

---

## E13 · Profilmuster in der Spur `M4` `P1`

### E13-S1 — Als User will ich, dass ein Rad ein Reifenprofil hinterlässt, keine glatte Rinne. `L`

**Akzeptanz:** Ein rollendes Rad hinterlässt ein wiederkehrendes Profilmuster, dessen Abstand mit
dem abgerollten Weg übereinstimmt (kein Rutschen des Musters), und das im Nahaufnahme-Maßstab
sauber aufgelöst wird.

- [ ] E13-T1 Profil als Textur oder prozedurales Muster, im Collider-Raum projiziert
- [ ] E13-T2 Musterphase folgt der zurückgelegten Strecke, nicht der Zeit
- [ ] E13-T3 Profiltiefe und -stärke als Parameter je Collider
- [ ] E13-T4 Alternative: Profil aus der Collider-Geometrie selbst (grobes Rad-Mesh mit echten Stollen)
- [ ] E13-T5 Sohlenprofil-Variante für Schuhe/Fußabdrücke
- [ ] E13-T6 Test: Musterabstand gegen Radumfang prüfen
- [ ] E13-T7 Warnung, wenn die Zellgröße zu grob für die gewählte Profilfrequenz ist

---

## E14 · Materialanhaftung am Objekt `M4` `P1`

### E14-S1 — Als User will ich, dass Schlamm am Auto und Schnee an den Schuhen kleben bleibt. `L`

**Akzeptanz:** Ein Collider, der durch Schlamm fährt, zeigt an den Kontaktflächen sichtbar
Material, das über die Zeit aufgebaut wird und langsam wieder abgeht.

- [ ] E14-T1 Kontaktflächen am Collider ermitteln (Eintauchtiefe pro Vertex/Face)
- [ ] E14-T2 Anhaftungs-Attribut auf dem Collider aufbauen, gedämpft über die Zeit
- [ ] E14-T3 Stickiness je Element (Schlamm hoch, trockener Sand fast null)
- [ ] E14-T4 Shader-Overlay auf dem Collider: Material-Layer über dem Originalmaterial
- [ ] E14-T5 Optionale geometrische Variante (dünne Schicht per Displacement) für Nahaufnahmen
- [ ] E14-T6 Abfallen/Abtrocknen über Zeit, mit Rückgabe der Masse ins Höhenfeld
- [ ] E14-T7 Nicht-destruktiv: Originalmaterial des Colliders bleibt unangetastet

---

## E15 · Schneefall aus der Luft `M4` `P1`

### E15-S1 — Als User will ich Schneeflocken, die fallen und sich auf der Szene ansammeln. `M`

**Akzeptanz:** Sichtbarer Schneefall über der Domain; die Schneehöhe wächst gleichmäßig, wird
von Collidern abgeschattet (kein Schnee unter einem Dach) und fügt sich in die bestehende
Relaxation ein.

- [ ] E15-T1 Fallende Partikel oberhalb der Domain (nutzt die Spray-Infrastruktur aus E10 rückwärts)
- [ ] E15-T2 Akkumulation ins Höhenfeld beim Aufkommen
- [ ] E15-T3 Abschattung durch Collider (Raycast nach oben, einmal pro Zelle, gecacht)
- [ ] E15-T4 Windversatz und Flockengröße als Parameter
- [ ] E15-T5 Günstiger Modus ohne sichtbare Flocken (nur Höhenzuwachs) für schnelles Vorheizen
- [ ] E15-T6 Spuren schneien über die Zeit wieder zu (Kopplung an `gfx_age`)

---

## E17 · Vollständige Parametrisierung / „alles einstellbar" `P2` — User-Wunsch (2026-08-20)

**Durchgehendes Designprinzip, nicht nur ein Epic:** Jeder verhaltens- oder look-steuernde Wert
wird als Node-Group-Input gebaut (min/max/default/description), sodass später nur ein Panel-Regler
drangehängt werden muss. Nicht v1-UI-blockierend, aber die Architektur zieht das von Anfang an mit.

### E17-S1 — Hartcodierte Konstanten als Parameter freischalten `M`
- [ ] E17-T1 `_STABILITY` (ng_relax) → Group-Input „Solver Stability" (Advanced)
- [ ] E17-T2 `_SLOPE_CALIB` (ng_relax) → Group-Input „Repose Calibration" (Advanced)
- [ ] E17-T3 `_RAY_LENGTH` (ng_ground_sim) → Group-Input „Collider Reach"
- [ ] E17-T4 displacement_ratio / Pile-Parameter (E3-S3) als Inputs (schon so gebaut)
- [ ] E17-T5 Spray-Parameter (E10) als Inputs

### E17-S2 — Quality-Profil pro Objekt überschreibbar `M`
- [ ] E17-T6 Auflösung/Iterationen/Substeps/LOD einzeln pro Domain editierbar (Custom-Quality)
- [ ] E17-T7 „Custom"-Qualitätsstufe, die die Profil-Defaults als Startwerte übernimmt

### E17-S3 — Advanced-Panel `S`
- [ ] E17-T8 Panel-Sektion „Advanced" sammelt alle Feinregler, eingeklappt per Default
- [ ] E17-T9 Reset-auf-Preset-Button je Sektion

---

## E16 · Weitere Elemente (Lava, Schleim, …) `P3` — v3-Wunsch des Users (2026-08-20)

**Architektur unterstützt das bereits:** Elemente sind datengetrieben (`data/elements.py`,
`data/presets/*.json`, Shader-Builder). Neue Elemente = neue Datensätze + Shader, kein
Solver-Umbau. Lava und Schleim brauchen zusätzlich temperatur-/zeitabhängige Viskosität und
Emission — deshalb eigener Epic statt bloßes Preset.

### E16-S1 — Lava `L`
- [ ] E16-T1 Viskosität als Funktion der „Temperatur" (kühlt über `gfx_age` ab → erstarrt)
- [ ] E16-T2 Emissiver Shader mit Kruste (kühle Bereiche dunkel, heiße glühend)
- [ ] E16-T3 Sehr niedriger Böschungswinkel heiß → hoch beim Erstarren

### E16-S2 — Schleim / zähe Flüssigkeiten `M`
- [ ] E16-T4 Hohe Kohäsion + hohe Viskosität, langsames Zurückfließen
- [ ] E16-T5 Transluzenter Shader (SSS, Glanz), Fäden/Strähnen optional
- [ ] E16-T6 Generisches „Custom Fluid"-Preset mit frei einstellbaren Kennwerten

---

## E12 · Forschung: echte 3D-Granulate `P3` (nicht in v1.0)

### E12-S1 — Position-Based-Dynamics-Granulate in Geometry Nodes `XL`

- [ ] E12-T1 Machbarkeitsstudie: Nachbarsuche über räumliches Hashing in GN
- [ ] E12-T2 Dichte-Constraint und Reibung
- [ ] E12-T3 Kopplung an das Höhenfeld (Granulate nur dort, wo die Kamera hinschaut)
- [ ] E12-T4 Ehrliche Bewertung: Partikelzahl gegen Bildzeit — Abbruch, falls unbrauchbar

---

## Reihenfolge der Abarbeitung (Vorschlag)

1. **E0** komplett — ohne installierbares, testbares Gerüst ist alles andere blind.
2. **E1** komplett — jede weitere Node-Group hängt am Builder.
3. **E2-S1**, dann ein minimaler Solver aus **E3-S1** und ein rohes **E4-S1** → **M1 erreicht.**
4. **E3-S2** (Böschungswinkel) — der Kern, hier entscheidet sich der Look.
5. **E3-S3**, **E4-S2**, **E4-S3** → **M2 erreicht.**
6. **E5**, **E6**, **E7** parallel möglich; **E8** und **E9** danach → **M3 erreicht.**
7. **E10** (Spray), dann **E13** (Profilmuster), **E15** (Schneefall), **E14** (Anhaftung),
   zuletzt **E11** (QA und Doku) → **M4, Release 1.0.**

Reihenfolge innerhalb von M4 mit Absicht so: E13 und E15 setzen auf bereits gebauter
Infrastruktur auf (Collider-Sampling beziehungsweise Spray-Layer) und sind damit günstig;
E14 ist das aufwendigste der drei, weil es als einziges Geometrie **außerhalb** der Domain
verändert.

**Kritischer Pfad:** E1 → E3-S2 → E3-S3. Wenn die Relaxation nicht stabil und schnell ist,
trägt das Produkt nicht. Deshalb bekommt E3-S2 einen eigenen automatisierten Physik-Test, bevor
darauf aufgebaut wird.
