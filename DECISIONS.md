# GroundFX - Entscheidungen

Kurzer Log: was, warum. Neueste oben. Ältere Detailentscheidungen stehen in
`docs/OPEN_QUESTIONS.md` und `docs/PLAN.md`.

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
