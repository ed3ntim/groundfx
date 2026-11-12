# GroundFX - Kontext

Was Context-Clears überleben muss. Stand: 2026-11-12.

## Ziel (User)

- Fotorealistische, hyperrealistische Shots und Animationen von Schlamm, Schnee
  und Sand, bis auf Sandkorn- bzw. Eiskristallebene.
- Motion muss im Viewport funktionieren.
- Verhalten: hinter dem Objekt zusammenfallen, davor anhäufen, beim Stopp
  liegen bleiben, wo realistisch **auf dem Objekt** hängen oder liegen bleiben.
- So performant wie möglich. Bestand durfte verworfen werden.

## Architektur (Solver v2, `core/nodegroups/ng_ground_sim.py`)

Ein Geometry-Nodes-Modifier auf einem Grid-Mesh (Domain). Pro Frame in der
Simulation Zone:

1. Collider holen (Collection Info, RELATIVE, Realize), Geschwindigkeit pro
   Vertex aus dem Sim-State `Colliders Prev`, Swept-Kopien für Sub-Frames.
2. Top-Schicht (`gfx_top`) mit der Collider-Geschwindigkeit advektieren
   (Scatter).
3. Raycast von unten (`lo`, Belegung `gfx_occ`) und von oben (`gfx_zhi`),
   `gfx_cov` = beide treffen.
4. Verdrängtes Volumen (Carve) auf einen Ring freier Zellen scattern, Ziel
   vorwärts verschoben (Bugwelle).
5. Vereinte Relaxation: jede Zelle zeigt Boden oder `zhi + top`; antisymmetrischer
   Paarfluss in Repeat Zone, Strides 4,4,2,2,1,1,...
6. Felder `gfx_comp`, `gfx_flow`, `gfx_age` für die Shader.
7. Ausgabe: Boden-Mesh plus Top-Schicht als Instanz.

Massenerhaltung ist exakt (Paarfluss, Scatter per Accumulate Field), nur der
Kompaktionsanteil `1 - displace` verschwindet bewusst.

## Gen 3: Surface-Stufe (`core/nodegroups/ng_surface.py`)

Zweiter Geometry-Nodes-Modifier `GroundFX Surface` direkt nach dem Solver,
reine Anzeige ohne Rückwirkung auf die Simulation. Für Sand und Schlamm
(`ops/op_surface.SURFACE_ELEMENTS`), je Element eine eigene Node-Group
(`GFX_Surface_Sand`, `GFX_Surface_Mud`) aus derselben `build`-Funktion.

1. Top-Schicht realisieren, `gfx_dist`/`gfx_damp` weichzeichnen.
2. Catmull-Clark-Subdivision: Viewport Level 0, Render Level nach Quality
   (256² ergibt Level 2, rund 1 Mio. Vertices).
3. Versatz in Z: Windrippel auf ungestörtem Boden, Klumpenrelief wo
   `gfx_dist` gesetzt ist, flach wo `gfx_comp` gesetzt ist.
4. Krümel: 1 bis 5 mm große, verformte Icosphären als echte Meshes, nur auf
   aufgewühltem Boden. Steinchen und Muschelbruch (`gfx_pebble` wählt die
   Steinfarbe im Shader) überall, wo der Boden Geometrie ist.
5. Umgebung (optional): feiner Ring (3x Domain) mit denselben Rippeln, dann
   Fernfeld mit Dünen (rund 100x Domain).

`core/surface_fn.py` enthält Rippel- und Klumpenfunktion als Feldmathematik,
die in Geometry- und Shader-Bäumen identisch läuft. Der Sand-Shader sortiert
damit dunkle Körner in die Rippeltäler und bumpt das Fernfeld (`gfx_geo` sagt,
wo die Rippel schon Geometrie sind).

Neue Solver-Felder (nur Look): `gfx_dist` wächst, wo sich die Höhe ändert, und
bleibt. `gfx_damp` skaliert mit dem Abstand zur Ruhehöhe (3 cm = voll feucht)
und trocknet mit `Drying` pro Frame.

Die Stufe ist opt-in (`obj.groundfx.surface_detail`). `create_domain` liefert
ohne `surface=True` das nackte Sim-Gitter, darauf verlassen sich Tests, Bake
und Freeze. Die UI-Operatoren schalten sie ein.

## Schlamm Gen 3

Profil der Surface-Stufe für Schlamm:

- Keine Rippel. Stattdessen breite Unebenheit (`Undulation`, Standard 12 mm)
  überall, auch im Ring.
- Aufgewühlt: runde Wülste aus Smooth-Voronoi (`mud_lobes`), Höhe `Clod
  Height` mal 2. Dazu wenige flache Spritzklumpen.
- Stehendes Wasser: ein einzelnes Quad auf Höhe Ruhelage plus `Water Level`
  (Standard -5 mm) mit Material `GFX_Water`. Weil der Schlamm ein Höhenfeld
  ist, zeigt sich das Wasser nur dort, wo er tiefer liegt: in Senken und in
  jeder Spur.
- `gfx_shore`: 1 auf oder unter dem Wasserspiegel, 0 ab 12 mm darüber. Der
  Shader macht daraus den durchnässten Rand um jede Pfütze.

Shader: lokale Nässe aus Regler, `gfx_shore`, `gfx_comp`, `gfx_dist` und
Relief. Der Clearcoat ist über einen Noise-Schwellwert fleckig, sonst wirkt
nasser Schlamm wie Plastik. Feuchter Boden muss dunkel sein (linear rund
0.08/0.05/0.03), sonst liest er sich in der Sonne als Sand.

## Zielbild (Referenzen von ed3n, 2026-11-13)

- Schlamm: aufgewühlter Acker-Schlamm, klumpig, überall kleine nasse
  Glanzpunkte, milchig-braune Pfützen in den Senken, dicker faltiger Wulst
  um eine runde Spur, Spritzer am Objekt, einzelne Halme.
- Sand: goldbraun, aus der Totale sichtbar körnig, flaches warmes Streiflicht
  mit weichen Rippelschatten, wenige größere Steinchen, Sand haftet unten
  am Objekt, Spur als runde Mulde mit weichem Wall.

Daraus gelernt:

- Körnigkeit aus der Distanz braucht eine grobe Kornfraktion (1 mm) im
  Shader. Zu groß (2 mm) ergibt im Makro flache Farbflecken.
- Schlamm-Klumpen: Billowed Noise mit wenig Detail. Mit viel Detail wird
  daraus scharfkantiges Geröll.
- Der Wasserstand ist sehr empfindlich: zwischen -7 mm (fast keine Pfützen)
  und 0 mm (halbe Fläche unter Wasser) liegen nur 7 mm. Standard -4 mm.

## Verdrängung (Solver, seit 2026-11-12)

Der Ring, auf den verdrängtes Volumen fällt, hat eine Reichweite in Metern
(4 cm), nicht in Zellen. Jede Quellzelle sucht erst den nächsten Ringpunkt
(Richtung nach außen) und wirft von dort zufällig weiter. Vorher landete das
gesamte Volumen eines eintauchenden Objekts auf der innersten Ringreihe und
stand als Wand über dem Objekt.

## Element-Kennwerte (`data/elements.py`)

| | repose | cohesion | yield | compact | displace | stick |
|---|---|---|---|---|---|---|
| Sand | 34° | 0.02 | 0 | 5° | 0.95 | 0.15 |
| Snow | 40° | 0.25 | 0 | 35° | 0.35 | 0.6 |
| Mud | 10° | 0 | 0.003 | 4° | 1.0 | 0.8 |

## Performance (headless, ms/Frame, Hero-Szene)

| Quality | Grid | Relax-Iter | Substeps | ms/Frame |
|---|---|---|---|---|
| Low | 64² | 4 | 1 | 9 |
| Medium | 128² | 8 | 2 | 21 |
| High | 256² | 14 | 3 | 45 |
| Ultra | 512² | 24 | 4 | 194 |

## Blender-5.2-Fallstricke (teuer gelernt)

- **Capture Attribute** hat in 5.2 einen Selection-Socket an Index 1. Items
  immer per Name füttern und lesen, nie per Index.
- **Join Geometry** stellt das zuletzt verlinkte Input zuerst. Für Scatter
  per Index (`Join(src, grid)`) muss die Link-Reihenfolge stimmen
  (`dev/probe_scatter.py`).
- **Index nach Mesh to Points** zählt die erzeugten Punkte, nicht die
  Grid-Vertices. Quell-Index vorher als Attribut speichern (`gfx_src_i`).
- **Shader-Socketnamen**: Attribute-Output heißt `Factor` (nicht `Fac`),
  ColorRamp- und Noise-Fac per Index 0 ansprechen.
- **ColorRamp** sortiert beim Setzen der Positionen um: `mat_sand.set_ramp`
  nutzen.
- **Makro-Kameras**: Clip-Start auf 2 mm, sonst schwarzes Bild.
- Lichtkalibrierung der Testszene: Himmel "Multiple Scattering" mit eigener
  Sonnenscheibe, Stärke 0.06, Sonne 22° hoch, AgX. Keine separate Sonnenlampe
  mehr, das Verhältnis Sonne zu Himmel stimmt so von selbst.
- **Generierte Meshes in Geometry Nodes haben kein Material** und rendern
  weiß. Umgebung und Krümel brauchen Set Material mit dem Domain-Material.
- **Menu-Sockets** (Subdivision Surface, Boundary Smooth) nehmen den
  Anzeigenamen als String, z. B. "Keep Corners".
- **Noise minus 0.5** streut nur etwa ±0.15. Amplituden danach kalibrieren,
  nicht nach dem theoretischen Bereich ±0.5.
- Bash-Heredocs mit Python-Code voller Anführungszeichen brechen hier. Dateien
  mit dem Write-Tool anlegen.

## Bekannte Grenzen

- Boden unter schwebenden (bedeckten, aber nicht berührenden) Objekten ist
  eingefroren.
- Seitliches Haften an senkrechten Flächen (Schlamm an Reifenflanken) fehlt.
- Schlamm-Makro: Der Himmelsreflex auf dem Wasserfilm dominiert, der Body
  braucht noch mehr Struktur.
- Schnee-Mikro: Körner lesen sich, wirken aber leicht kunststoffartig.
  Echte Facettengeometrie (Kornebene für Schnee) wäre der nächste Schritt.
- Kornebene gibt es bisher nur für Sand.
- Surface-Stufe (Gen 3) gibt es für Sand und Schlamm, nicht für Schnee.
- Schlamm-Wasser ist ein fester Pegel ohne Verdrängung oder Spritzer.
- Haufen haben flache Plateaus statt eines Grats. Tiefes, langes Pflügen
  türmt sie über die Box, dann liegt Sand auf deren Oberseite (Volumen
  stimmt, Form nicht).

## Lizenz

Repo-Lizenz ist PolyForm Noncommercial 1.0.0 (`LICENSE.md`, `COMMERCIAL.md`,
festgelegt von ed3n). Inkonsistent ist noch: `blender_manifest.toml` und rund
65 SPDX-Header stehen auf GPL-3.0-or-later. Angleichen erst nach
Entscheidung, weil Blender-Addons über `bpy` als GPL-abgeleitet gelten und
extensions.blender.org nur GPL-kompatible Lizenzen annimmt.
