# GroundFX - Kontext

Was Context-Clears überleben muss. Stand: 2026-10-24.

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
- Lichtkalibrierung der Testszene: Sonne 3.2, Nishita-Himmel 0.08, AgX. Mehr
  Himmel gibt Blaustich.

## Bekannte Grenzen

- Boden unter schwebenden (bedeckten, aber nicht berührenden) Objekten ist
  eingefroren.
- Seitliches Haften an senkrechten Flächen (Schlamm an Reifenflanken) fehlt.
- Schlamm-Makro: Der Himmelsreflex auf dem Wasserfilm dominiert, der Body
  braucht noch mehr Struktur.
- Schnee-Mikro: Körner lesen sich, wirken aber leicht kunststoffartig.
  Echte Facettengeometrie (Kornebene für Schnee) wäre der nächste Schritt.
- Kornebene gibt es bisher nur für Sand.

## Lizenz

Manifest und SPDX-Header stehen auf GPL-3.0-or-later. Blender-Addons, die `bpy`
importieren, gelten nach Blender-Foundation-Auslegung als GPL-abgeleitet. Die
Standardlizenz (PolyForm Noncommercial) wurde deshalb **nicht** eingesetzt;
Entscheidung durch ed3n offen.
