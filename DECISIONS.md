# GroundFX - Entscheidungen

Kurzer Log: was, warum. Neueste oben. Ältere Detailentscheidungen stehen in
`docs/OPEN_QUESTIONS.md` und `docs/PLAN.md`.

## 2026-11-12 Gen 4: Hybrid aus Höhenfeld und Partikeln, kein Partikel-Solver

Hurricane simuliert das ganze Bett als XPBD-Partikel in nativem Code. Das
ergibt echte 3D-Dynamik, kostet aber Auflösung: Ein Bett aus Partikeln hat
nie Korngröße, und im Viewport läuft es nicht flüssig. GroundFX bleibt beim
Höhenfeld für die Masse und nimmt Partikel nur für das, was das Höhenfeld
nicht kann: Material in der Luft. Das ist das Muster der Filmproduktion
(Bett als Feld, Partikel an der Interaktion, Vervielfachung für den Render).

- Partikel leben im Solver, nicht in der Anzeige, weil die Kopplung in
  beide Richtungen massengenau sein soll: Was fliegt, fehlt im Bett, und
  was landet, lawiniert weiter.
- Wenige Partikel (tausende) mit Volumen, die Körner entstehen analytisch
  in der Anzeige. So bleibt die Simulation viewport-tauglich und der Render
  bekommt trotzdem die reale Kornzahl.
- Die Startregel hängt an der Collider-Geschwindigkeit. Langsamer Kontakt
  verhält sich exakt wie Solver v2, deshalb bleiben alle alten Tests grün.
- Standard aus für geskriptete Domains, an für die UI-Operatoren, wie bei
  der Surface-Stufe.

## 2026-11-12 Gen 3: Anzeige-Stufe getrennt vom Solver

Die Lücke zwischen Simulationszelle (rund 5 mm) und Korn (0,4 mm) war der
Hauptgrund für den künstlichen Look. Sie wird in einem eigenen Modifier nach
dem Solver gefüllt, nicht im Solver und nicht nur im Shader:

- Der Solver bleibt ein schlankes Höhenfeld auf festem Gitter (schnell,
  bakebar, testbar).
- Echte Geometrie statt Bump, weil Rippel und Krümel bei flacher Sonne
  Schatten werfen müssen.
- Im Viewport Level 0, damit die Motion flüssig bleibt.

Rippel und Relief stehen als gemeinsame Funktion in `surface_fn.py`, damit
Geometrie und Shader nie auseinanderlaufen.

## 2026-11-12 Sand als erstes Gen-3-Element

Sand war am weitesten (Kornebene, Mineralpalette) und lässt sich prozedural am
glaubwürdigsten treffen. Schnee und Schlamm folgen auf derselben Stufe.

## 2026-11-12 Feuchte aus der Simulation

Frisch aufgewühlter Sand ist dunkler, weil er unter der trockenen Kruste
liegt. `gfx_damp` hängt deshalb an der Tiefe unter bzw. Höhe über der
Ruhelage, nicht an der bloßen Berührung: Ein dünner Überwurf bleibt hell, ein
tiefer Graben wird dunkel. Das gibt weiche Verläufe statt eines Flecks.

## 2026-11-12 Umgebung als Teil des Addons

Eine Domain als Platte im leeren Raum wirkt nie echt. Die Umgebung (Ring plus
Fernfeld bis zum Horizont) ist eine Option der Surface-Stufe, standardmäßig
aus, weil sie in fremden Szenen mit eigenem Terrain stört.

## 2026-11-13 Haften als Geometrie auf einem eigenen Objekt

Staub und Spritzer am Objekt sind echte kleine Meshes auf einem Coat-Objekt,
keine Maske im Material des Colliders. Gründe: Das Material des Nutzers bleibt
unangetastet, die Auflösung hängt nicht vom Mesh des Colliders ab (ein Würfel
hat acht Vertices), und Körner werfen Schatten. Preis: nur starre Collider,
und ein zusätzliches Objekt pro Collider in der Szene.

## 2026-11-13 Schlamm: Pfützen als fester Wasserspiegel

Pfützen sind eine einzige ebene Fläche auf Pegelhöhe, keine eigene
Simulation. Das kostet nichts, läuft im Viewport und füllt automatisch jede
Spur. Preis: Das Wasser wird nicht verdrängt und bewegt sich nicht. Eine
echte Flachwasser-Schicht wäre der nächste Schritt, falls das stört.

## 2026-11-13 Eine Surface-Group je Element

Sand und Schlamm teilen die `build`-Funktion, bekommen aber je eine eigene
Node-Group. So trägt keine Group Nodes des anderen Elements mit, und der
Elementwechsel tauscht nur den Group-Zeiger.

## 2026-11-12 Verdrängungsring in Metern statt Zellen

Bei hoher Auflösung waren drei Zellen nur 1,4 cm. Ein eintauchendes Objekt
lud sein ganzes Volumen dort ab, der Sand stand höher als das Objekt und lief
auf dessen Oberseite. Jetzt 4 cm Reichweite und ein zweistufiger Wurf nach
außen. Die Solver-Tests blieben unverändert grün.

## 2026-11-12 Aufgeräumt

Gelöscht: der tote v1-Pfad in `mat_builder.py` (rund 400 Zeilen, wurde nie
mehr erreicht), ungenutzte Konstanten alter Solver-Bausteine, Renders der
Shader-Generationen vor v2 und die v2-Sandrenders. Die Historie in
`docs/STATUS.md` wurde durch den aktuellen Stand ersetzt.

## 2026-10-24 Lizenz: PolyForm Noncommercial (ed3n)

ed3n hat PolyForm Noncommercial 1.0.0 festgelegt. Manifest und SPDX-Header
(noch GPL-3.0) sind nicht angeglichen. Offen ist, ob GPL-Implikationen von
`bpy` und der Vertrieb über extensions.blender.org dagegen sprechen.

## 2026-10 Solver v2 statt Toppling plus Deposit

Der alte Solver (4-Nachbar-Toppling, Deposit-Advektion) hatte mehrere Probleme:

- Schachbrett-Artefakte und Massenfehler.
- Wände direkt am Collider.
- Diffuse Bugwellen.

v2 nutzt einen antisymmetrischen 8-Nachbar-Paarfluss (exakt massenerhaltend),
Multiskalen-Strides mit Pfadprüfung (kein Tunneln), eine exakte
Scatter-Verdrängung über Accumulate Field und eine Fließgrenze für Schlamm.

Die alten Bausteine `ng_relax`/`ng_deposit` wurden gelöscht.

## 2026-10 Zwei-Schicht-Kopplung statt Partikel für "Material auf dem Objekt"

Partikel/MPM wären teuer und nicht viewport-tauglich. Stattdessen gibt es
eine zweite Höhenschicht `gfx_top` über der Collider-Oberseite: Sie fährt per
Scatter mit dem Objekt und nimmt an derselben Relaxation teil, rutscht also
im Böschungswinkel über Kanten ab. Das deckt Haufen auf Schaufeln, Kisten und
Motorhauben ab. Seitliches Haften an Flanken deckt sie nicht ab.

## 2026-10 Look v2: physikalische Shader in echter Korngröße

Die Shader arbeiten in Objektkoordinaten mit echter Korngröße: Sand 0,4 mm,
Schnee 0,8 mm. Damit funktioniert dasselbe Material von der Totale bis zum
Makro.

Simulationsfelder (`gfx_comp`, `gfx_flow`) steuern die Verdichtung, das
Verschmieren und die Nässe. Prozedural statt Bildtexturen: keine Kachelung,
kein Auflösungslimit.

## 2026-10 Kornebene optional, nur im Kamera-Frustum

Echte 3D-Körner gibt es nur dort, wo die Kamera sie auflöst (bis zur Distanz,
an der ein Korn 4 px groß wird), nach dem Vorbild von Pixar (*Elio*). Die
Auswahl ist über die Distribute-Selection stabil, damit Körner nicht
flackern. Im Viewport ist die Kornebene aus, damit die Motion flüssig bleibt.
