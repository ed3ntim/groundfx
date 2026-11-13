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

## Gen 4: fliegendes Material (`ng_ejecta.py`, `ng_spray.py`, seit 2026-11-12)

Auslöser: Vergleich mit Hurricane (BeFX, XPBD-Partikel) und realen Aufnahmen.
Ein Höhenfeld kann Material nur seitlich von Zelle zu Zelle schieben. Was
Sand im Film echt macht, ist die Phase in der Luft: Schleier, Strähnen,
einzelne Körner. Die fehlte komplett. GroundFX hat jetzt drei Zustände:
Bett (`gfx_h`), Top-Schicht (`gfx_top`), Luft (Partikel).

Solver (`ng_ejecta`, zweiter Simulationszustand `Ejecta`, eine Punktwolke):

- **Start.** Das Volumen, das die Verdrängung auf den Ring legen würde, wird
  nach der Geschwindigkeit des nächsten belegten Collider-Punkts geteilt:
  unter 0,25 m/s bleibt alles im Bett, ab 2,2 m/s fliegt der Anteil `Spray`.
  Startgeschwindigkeit: Collider-Geschwindigkeit (0,45 bis 1,0), dazu ein
  Anteil nach außen und nach oben, alles gestreut. Zufälliger Startzeitpunkt
  innerhalb des Frames, sonst stroboskopiert der Schleier.
- **Flug.** Schwerkraft plus quadratischer Luftwiderstand, halb-implizit.
  Kleine Partikel bremsen stärker (Regel von DNEG für *Dune*).
- **Landung.** Unter der Bettoberfläche oder auf der Oberseite eines
  Colliders: Volumen geht per Accumulate-Scatter exakt zurück in `gfx_h`
  bzw. `gfx_top`. Trifft ein Partikel eine Flanke, fährt es mit der Fläche
  mit und fällt daneben herunter.
- Gelandete Partikel bleiben 4 Frames als Geist (Volumen 0), damit die
  Körner der Anzeige zu Ende fallen können.

Anzeige (`ng_spray`, Modifier `GroundFX Spray`, letzte Stufe, ohne Zustand):
Jedes Partikel wird zu so vielen Körnern, wie sein Volumen enthält (mal
`Detail`, Deckel `Max Grains`). Jedes Korn sitzt einen zufälligen Bruchteil
eines Frames zurück auf der Bahn und hat eine eigene kleine
Geschwindigkeitsabweichung, die Wolke wächst also mit der Flugzeit. Körner
unter dem sichtbaren Boden werden entfernt (Raycast). Punkte mit
`velocity`-Attribut, Cycles rendert sie als Kugeln mit Motion Blur.

Gemessen (Box 20 cm, 1,5 m/s, Quality Medium): Spitze rund 700 Partikel und
1,7 l in der Luft. Im 6-m-Feld bleibt die Summe aus Bett und Luft nach dem
Stopp exakt gleich. Im 2-m-Feld fehlt, was über den Rand fliegt.

Nur für Sand, und nur wo der volle Look verlangt ist (`surface=True` bzw.
UI): `create_domain` ohne das bleibt bei `spray = 0`. Der Solver-Eingang
`Spray` hat den Standard 0.

Fallstricke:

- **Starthöhe.** Bei schneller Fahrt (Weg pro Frame größer als die
  Ringreichweite von 4 cm) lädt die Verdrängung das Bugvolumen eines Frames
  auf wenigen Ringzellen ab, bis 70 cm hoch. Die Relaxation zieht das im
  selben Frame glatt, im Bild sieht man es nie. Partikel müssen deshalb von
  der Oberfläche vor dem Abladen starten, sonst steht eine meterhohe Säule
  an der Box. Messen mit `dev/probe_spray_shape.py`.
- Der Probe liest das Mesh nach der Surface-Stufe: Summen über `gfx_h`
  zählen dort Krümel mit und sind wertlos, Maxima stimmen.
- Relative `--out`-Pfade der Hero-Szene landen neben dem Arbeitsverzeichnis
  von Blender, nicht im Repo. Absolut angeben.
- **Attribute Domain Size** stürzt in 5.2 auf einer Punktwolke ab, deren
  letzter Punkt gerade gelöscht wurde. Zählen über Attribute Statistic.
- **Remove Named Attribute**: `Pattern Mode` ist ein Menü-Socket
  ("Wildcard"), keine Node-Property.
- Punkte aus Mesh to Points erben alle Gitter-Attribute. Vor dem Speichern
  der Partikel-Attribute mit `gfx_*` entfernen, sonst vervielfacht die
  Anzeige jedes davon mit der Kornzahl.
- `evaluated_geometry()` in Python: das GeometrySet in einer Variable
  halten, sonst ist `pointcloud` sofort ungültig.

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

## Spalt an der Collider-Wand (seit 2026-11-13 geschlossen)

Ein Höhenfeld kann keine senkrechte Fläche halten: Die Zelle unter dem Objekt
ist abgetragen, die freie Zelle daneben voll, das Mesh verbindet beide mit
einer Rampe von einer Zelle Breite. Bei 2 m Domain und Quality Medium sind das
1,6 cm sichtbarer Spalt. Die Anzeige im Solver zeichnet deshalb die äußersten
belegten Zellen auf der Höhe des freien Materials daneben (Blur über zwei
Zellen, gedeckelt auf die Oberkante des Objekts). Die Rampe liegt so im
Inneren des Objekts. `gfx_h` bleibt unverändert, nur die Position ändert sich.
Wer Höhen misst, liest `gfx_h`, nicht die Vertex-Position.

## Haften am Objekt (`core/nodegroups/ng_coat.py`, `ops/op_coat.py`)

Je Collider und Domain ein eigenes Coat-Objekt (`<Collider> Coat`) mit dem
Modifier `GroundFX Coat`. Ein eigenes Objekt, weil der Collider selbst einen
Abhängigkeitszyklus ergäbe: Die Domain liest den Collider, der Coat liest die
Domain.

- Kandidatenpunkte werden einmal im lokalen Raum des Colliders verteilt
  (Object Info ORIGINAL) und als Simulationszustand gehalten. Weltposition
  pro Frame über die Transform-Matrix. Deshalb nur starre Collider, und das
  Coat-Objekt muss im Ursprung ohne Rotation und Skalierung bleiben.
- Pro Frame: Strahl von oben auf die Domain-Oberfläche, anderthalb Zellen
  außerhalb der Fläche. Liegt der Boden dort auf oder über dem Punkt, ist er
  vergraben. Bewegt sich das Objekt, werden Punkte bis `Splash Height` mal
  Zufall hoch drei bespritzt. Getroffen bleibt getroffen, wenn die eigene
  Zufallszahl unter `Cling` liegt.
- Treffer werden zu kleinen Meshes auf der Fläche: Sand Körner 0,3 bis
  0,9 mm, Schlamm flache Kleckse 0,6 bis 4,5 mm, nach unten gestreckt.
- Schalter `Cling To Colliders` an der Domain (Standard an). `sync_coats`
  hält Coats mit Collider-Liste, Element und Schalter in Einklang.
- Blender 5.2: Align Rotation to Vector hat `axis` und `pivot_axis`, nicht
  `rotation_axis`.

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

- Fliegendes Material: kein Staub (feine Schwebfraktion), Körner stoßen
  nicht untereinander und prallen nicht ab, nur Sand. Staub als Volumen
  braucht additive Dichte aus Punkten: in 5.2 nicht vorhanden, 5.3 bringt
  laut Release Notes "Rasterize Points" (ungeprüft, 5.3 ist hier nicht
  installiert).
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
