# GroundFX — Backlog

**Struktur:** Epic → User Story → Tasks
**Schätzung:** S ≈ ½ Arbeitseinheit · M ≈ 1 · L ≈ 2–3 · XL ≈ 4+
**Priorität:** P0 = MVP-blockierend · P1 = für Release 1.0 nötig · P2 = nice-to-have · P3 = Forschung

Meilenstein-Zuordnung: M1 = E0–E2, M2 = E3–E4, M3 = E5–E9, M4 = E10, E13–E15, E11, E12 offen.

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

### E2-S2 — Als User will ich, dass das Material sich an vorhandenes Terrain anpasst. `M`

- [ ] E2-T5 Terrain-Slot: beliebiges Objekt als Untergrund wählbar
- [ ] E2-T6 `gfx_base` einmalig aus dem Terrain raycasten und cachen (nicht pro Frame!)
- [ ] E2-T7 Fallback flache Ebene, wenn kein Terrain gesetzt ist
- [ ] E2-T8 Rand-Verhalten: offen (Material fällt hinaus) oder geschlossen (Wanne)

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

- [ ] E3-T5 `ng_relax`: Repeat Zone mit slope-limitierter Relaxation
- [ ] E3-T6 Kohäsions-Schwelle (Bingham-Fließkriterium)
- [ ] E3-T7 Fließrate/Viskosität als Dämpfung + Iterationszahl
- [ ] E3-T8 `conserve_mass`-Modus über symmetrischen Nachbaraustausch (High/Ultra)
- [ ] E3-T9 Stabilität: Clamping gegen Oszillation bei hohen Fließraten
- [ ] E3-T10 Test: Böschungswinkel-Messung; Test: Massebilanz über 100 Frames (< 2 % Abweichung)

### E3-S3 — Als User will ich, dass verdrängtes Material realistisch aufgehäuft wird. `L`

- [ ] E3-T11 `ng_displace`: Pile-Puffer, gerichtete Verteilung entlang des Carve-Gradienten
- [ ] E3-T12 `displacement_ratio` — Anteil Aufhäufen gegenüber Verdichten
- [ ] E3-T13 Berm-Bildung an den Spurrändern, Bugwelle vor dem Objekt
- [ ] E3-T14 Ablage nur außerhalb des Colliders (Maskierung)

### E3-S4 — Als User will ich Verdichtung und Feuchtigkeit als sichtbare Effekte. `M`

- [ ] E3-T15 `gfx_comp` aufbauen und über Zeit abbauen („Nachrieseln", Schnee rieselt zu)
- [ ] E3-T16 `gfx_wet` mit Diffusion, koppelt an Kohäsion
- [ ] E3-T17 `gfx_flow` (Richtungsvektor) für die Shader
- [ ] E3-T18 `gfx_age` für Zeit-basierte Effekte

### E3-S5 — Als User will ich Substeps für stabile schnelle Bewegungen. `M`

- [ ] E3-T19 Substep-Schleife innerhalb eines Frames (Repeat Zone über die Solver-Kette)
- [ ] E3-T20 dt-Korrektheit über alle Raten hinweg
- [ ] E3-T21 Test: gleiche Endform bei 1 vs. 3 Substeps für langsame Bewegung

---

## E4 · Collider-System `M2` `P0`

### E4-S1 — Als User will ich beliebige Objekte per Knopfdruck zu Collidern machen. `M`

**Akzeptanz:** Markierte Objekte hinterlassen sofort Spuren, ohne dass etwas am Node-Setup angefasst werden muss.

- [ ] E4-T1 Operator „Als Collider markieren / entfernen" (Multi-Select)
- [ ] E4-T2 Collider-Collection pro Domain, automatisch angelegt
- [ ] E4-T3 UIList mit Status, Proxy-Typ, Offset pro Collider
- [ ] E4-T4 Unterstützung für Instanzen und animierte Objekte

### E4-S2 — Als User will ich, dass auch High-Poly-Charaktere performant bleiben. `L`

**Akzeptanz:** Ein Charakter mit 500 k Tris kostet mit Proxy weniger als 20 % der Zeit ohne Proxy.

- [ ] E4-T5 Proxy-Generator: Convex Hull, Decimate, Bounding Box
- [ ] E4-T6 Proxy folgt dem Original (Constraint oder Modifier-Kette), inklusive Armature-Deformation
- [ ] E4-T7 Bounding-Box-Vorfilter im Node-Tree
- [ ] E4-T8 Benchmark-Test: mit und ohne Proxy

### E4-S3 — Als User will ich, dass schnelle Objekte durchgehende Spuren erzeugen. `M`

- [ ] E4-T9 Geschwindigkeit aus `carve - carve_prev` ableiten
- [ ] E4-T10 Richtungsabhängige Verdrängung (nach vorn und zur Seite, nicht rückwärts)
- [ ] E4-T11 Lückenfüllung bei schneller Bewegung über Substeps
- [ ] E4-T12 Einstellbarer Collider-Offset (Penetrationstoleranz)

---

## E5 · Elemente und Presets `M3` `P0`

### E5-S1 — Als User will ich zwischen Sand, Schnee und Schlamm wechseln, ohne Parameter zu kennen. `M`

- [ ] E5-T1 Element-Enum mit vollständigem Parametersatz je Element
- [ ] E5-T2 Elementwechsel tauscht Physik **und** Material atomar
- [ ] E5-T3 Nachfrage/Warnung, wenn dabei manuelle Anpassungen verloren gehen

### E5-S2 — Als User will ich fertige Presets, die sofort gut aussehen. `L`

**Akzeptanz:** Mindestens acht Presets, jedes mit Beschreibung, sichtbar unterschiedlichem Verhalten und dokumentierten Kennwerten.

- [ ] E5-T4 JSON-Preset-Format samt Schema-Validierung
- [ ] E5-T5 Sand: Fine Dry Sand · Coarse Sand · Wet Sand · Beach Sand
- [ ] E5-T6 Snow: Dry Powder · Packed Snow · Heavy Wet Snow · Fresh Fluff
- [ ] E5-T7 Mud: Thick Mud · Thin Mud · Wet Clay · Slush
- [ ] E5-T8 Operator „Preset anwenden" mit Vorschau der Kennwerte
- [ ] E5-T9 User-Presets speichern und löschen (in den Addon-Config-Ordner)

---

## E6 · Qualitätsstufen und LOD `M3` `P0`

### E6-S1 — Als User will ich mit einem Regler zwischen schnell und schön wählen. `M`

**Akzeptanz:** Die vier Stufen unterscheiden sich messbar gemäß der Budget-Tabelle in `PLAN.md`; der Wechsel benötigt keinen Neuaufbau der Szene.

- [ ] E6-T1 Qualitätsprofile als Datentabelle (Auflösung, Iterationen, Substeps, Spray-Cap, LOD)
- [ ] E6-T2 Operator „Set Quality" wendet das Profil auf alle oder das aktive Objekt an
- [ ] E6-T3 Auflösungswechsel überträgt vorhandene Sim-Daten nicht (klare Warnung: Sim startet neu)
- [ ] E6-T4 UI-Anzeige der Auswirkungen samt Ampel und ms-Schätzung

### E6-S2 — Als User will ich flüssiges Viewport-Feedback trotz hoher Renderqualität. `M`

- [ ] E6-T5 Getrennte Viewport-/Render-Pfade über `Is Viewport`
- [ ] E6-T6 Display-Subdivision und Detail-Displacement erst nach der Sim
- [ ] E6-T7 Optionale Distance-LOD-Ausdünnung für die Anzeige
- [ ] E6-T8 „Solo Sim"-Modus: Shading vereinfachen während des Scrubbings

### E6-S3 — Als User will ich Messwerte statt Bauchgefühl. `M`

- [ ] E6-T9 Benchmark-Operator: misst ms/Frame über N Frames und schreibt einen Report
- [ ] E6-T10 Ergebnisse der vier Stufen in der Doku festhalten
- [ ] E6-T11 Optionale Warnung, wenn die gemessene Zeit das Budget deutlich überschreitet

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

- [ ] E7-T1 Bake-Operator für das aktive Objekt (API-Abstraktion in `compat.py`)
- [ ] E7-T2 Bake All für alle GroundFX-Objekte, mit Fortschrittsanzeige
- [ ] E7-T3 Free / Free All
- [ ] E7-T4 Eigener Cache-Pfad, standardmäßig relativ zur `.blend`

### E7-S2 — Als User will ich sehen, was mein Cache kostet und ob er noch gültig ist. `M`

- [ ] E7-T5 Cache-Größe auf Platte anzeigen
- [ ] E7-T6 Parameter-Hash → Status „aktuell / veraltet"
- [ ] E7-T7 Warnung bei ungespeicherter `.blend` (relativer Pfad nicht auflösbar)
- [ ] E7-T8 Eigene Bake-Framerange abweichend von der Szene

### E7-S3 — Als User will ich ein Sim-Ergebnis als statisches Mesh einfrieren. `M`

- [ ] E7-T9 „Freeze to Mesh": aktueller Frame → neues Objekt mit Attributen
- [ ] E7-T10 Materialübernahme und Attributerhalt (`gfx_comp`, `gfx_wet` bleiben nutzbar)

---

## E8 · Shader `M3` `P0`

### E8-S1 — Als User will ich Materialien, die ohne Nacharbeit gut aussehen. `L`

- [ ] E8-T1 `mat_builder`: gemeinsame Bausteine (Triplanar-Noise, Wetness-Mix, Detail-Bump)
- [ ] E8-T2 Sand-Shader: Körnung, Farbvariation, Ripples entlang `gfx_flow`
- [ ] E8-T3 Schnee-Shader: Sparkle, Bläue in Vertiefungen, SSS (Cycles) / Approximation (EEVEE)
- [ ] E8-T4 Schlamm-Shader: nasser Glanz, Pfützen in Senken, Risse bei niedriger Feuchtigkeit

### E8-S2 — Als User will ich, dass der Shader auf die Physik reagiert. `M`

- [ ] E8-T5 Attribut-Anbindung `gfx_comp`, `gfx_wet`, `gfx_flow`, `gfx_h`
- [ ] E8-T6 Spuren sichtbar dunkler/glatter als unberührtes Material
- [ ] E8-T7 Feuchtigkeitsregler wirkt gleichzeitig auf Physik und Optik

### E8-S3 — Als User will ich die Optik schnell anpassen können. `S`

- [ ] E8-T8 Wenige, gut benannte Regler im Panel (Farbe, Rauheit, Detailstärke, Feuchtigkeit)
- [ ] E8-T9 Beide Render-Engines geprüft; Displacement nur wo sinnvoll
- [ ] E8-T10 Materialwechsel und eigene Materialien werden nicht überschrieben

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
