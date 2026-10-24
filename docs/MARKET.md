# Marktlösungen und Procedural Materials

Recherche 2026-10. Wozu: einordnen, was es gibt, und welche Ideen GroundFX
übernimmt.

## Blender-Markt

| Produkt | Was es ist | Lücke gegenüber GroundFX |
|---|---|---|
| [Dune Solver](https://superhivemarket.com/products/dune-solver) | Sand-Dünen-Generator mit Material-Setup | statische Landschaft, keine Objekt-Interaktion |
| [Quick Snow](https://blendermarket.com/products/quick-snow) | Schneedecke auf Objekten, Fußspuren | Spuren als Maske, keine Massenerhaltung bzw. Haufen |
| [Snowify](https://ninodefoq.gumroad.com/l/Snowify) | GN-Schneeschicht per Weight Paint, Material austauschbar (Sand, Schmutz) | Oberflächenschicht, nicht deformierbar |
| [Geo-Snow](https://superhivemarket.com/products/geo-snow), [Snow with Geometry Node](https://superhivemarket.com/products/snow-with-geometry-node) | GN-Schneeauflage | statisch |
| [Snow Generator (Ryan King)](https://ryankingart.gumroad.com/l/snow-gen) | GN-Modifier, Menge/Dicke/Detail, Cycles und EEVEE | statisch |
| [Elemental Surface Simulation Pack](https://superhivemarket.com/products/elemental-surface-simulation-pack) | GN-Simulationen Schnee/Schleim mit Kollision | Aufbau-Effekte, keine Pflug-Physik |

Ergebnis: Im Blender-Markt gibt es keine Lösung, die Pflügen, Anhäufen,
Liegenbleiben und Mitfahren auf dem Objekt viewport-tauglich kombiniert.
Diese Lücke füllt GroundFX.

## Film und High-End

- **Houdini MPM**
  - Quellen:
    - [Produktseite](https://www.sidefx.com/products/houdini/vfx/mpm/)
    - [Snowplow-Tutorial](https://www.sidefx.com/tutorials/mpm-snowplow/)
    - [MPM-Schnee-Config](https://www.sidefx.com/docs/houdini/mpm/mpmconfigsnow.html)
    - [MPM auf Heightfields](https://www.sidefx.com/docs/houdini/mpm/heightfields.html)
  - Material Point Method wie im Disney-Paper [A Material Point Method for Snow Simulation](https://www.academia.edu/3847240/A_Material_Point_Method_for_Snow_Simulation).
  - Physikalisch am besten, aber Minuten pro Frame und nicht interaktiv.
  - Übernommen: Die Kopplung zwischen Heightfield und Simulation, also MPM nur dort, wo nötig, ist auch unser Muster. Das Höhenfeld trägt den Großteil der Arbeit.
- **Pixar, *Elio*** ([Technology Library](https://www.pixar.com/technology-libraries))
  - Strände als Punktwolke mit über einer halben Milliarde Körnern.
  - Übernommen: Körner nur dort, wo die Kamera sie auflöst (`op_grains`).

## Procedural Materials: wie sie helfen

1. **Echte Größe statt Kachel.**
   - Voronoi-Zellen in Objektkoordinaten mit Skala `1/Korngröße` ergeben je Zelle ein Korn mit eigener Farbe (Mineral), Kuppel-Höhe und Glint.
   - Das ergibt keine Wiederholung und kein Texel-Limit; dasselbe Material hält von 5 m bis 5 mm Kameradistanz.
   - Quellen: [Blender Artists: Realistic sand](https://blenderartists.org/t/realistic-sand/1168317), [Cycles-Sand ohne Bild](https://blenderartists.org/t/real-looking-cycles-sand-dirt-without-an-image/635405).
2. **Simulation steuert Look.**
   - Die Solver-Felder wirken direkt auf den Shader:
     - Verdichtung (`gfx_comp`): glatter, dunkler, weniger Glints.
     - Fluss (`gfx_flow`): verschmierte Schlammfalten.
     - Nässe: Coat und Kohäsion.
   - Bildtexturen können das nicht.
3. **Schatten verkaufen Körnigkeit.**
   - Kavitäts-Abdunklung zwischen den Kuppeln plus Bump bzw. Displacement in Kornhöhe sind wichtiger als die Farbe.
   - Quelle: [BlenderNation: No-stress CG sand](https://www.blendernation.com/2022/09/05/generating-no-stress-cg-sand-in-blender-3-2/).
4. **Grenze.**
   - Unterhalb von etwa 10 px pro Korn reicht Shading nicht mehr, denn Silhouetten fehlen.
   - Dort übernimmt die Kornebene mit echter Geometrie (vgl. [Blender Artists: Points auf Scan-Düne](https://blenderartists.org/t/the-mandalorian-soundtrack-cd-release-mock-up/1464948)).
5. **Substance Designer** und Ähnliches liefern gebackene Bildtexturen.
   - Für Hintergrundflächen sind sie brauchbar.
   - Für Makro und für simulationsgesteuerte Variation sind sie den Blender-Shadern unterlegen.
   - Deshalb sind sie nicht übernommen.
