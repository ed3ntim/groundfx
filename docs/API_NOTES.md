# GroundFX — Verifizierte Blender-5.2-API-Fakten

Gegen **Blender 5.2.0 LTS / Python 3.13.13** headless geprüft am 2026-08-20
(`dev/probe_api.py`). Diese Notizen ersetzen Vermutungen — hier steht nur, was real getestet ist.

| Thema | Fakt |
|---|---|
| Node-Group-Sockets | Über `ng.interface.new_socket(name, in_out="INPUT"\|"OUTPUT", socket_type=...)`. **Nicht** mehr `ng.inputs`/`ng.outputs`. |
| Socket-Identifier | Schema `Socket_N`. Modifier-Inputs werden per `modifier["Socket_N"] = wert` gesetzt; Zuordnung über `s.identifier` aus `ng.interface.items_tree` (mit `in_out`-Filter). |
| Simulation Zone | Node-Paar `GeometryNodeSimulationInput` / `...Output`. Pairing via `sim_in.pair_with_output(sim_out)`. State-Items auf dem **Output**: `sim_out.state_items.new(TYPE, name)`. Ein Geometry-State wird automatisch angelegt. |
| Repeat Zone | Analog: `GeometryNodeRepeatInput`/`...Output`, `pair_with_output`, `rep_out.repeat_items.new(TYPE, name)`. |
| Blur Attribute | `GeometryNodeBlurAttribute`, Input-Sockets: `Value`, `Iterations`, `Weight`. |
| Raycast | `GeometryNodeRaycast` vorhanden. |
| Collection Info | `GeometryNodeCollectionInfo` — Inputs `Collection`, `Separate Children`, `Reset Children`; Output **`Instances`**; Property `transform_space` (`ORIGINAL`/`RELATIVE`). Für Raycast gegen die Vereinigung: `RELATIVE` → `GeometryNodeRealizeInstances` → `Raycast.Target Geometry`. Verifiziert `dev/probe_collection_raycast.py` (E4-T17): ein Grid trifft die Unterseiten mehrerer Cubes in der Collection. |
| Collection-Socket | Interface-Typ `NodeSocketCollection`. Modifier-Input wird wie Object-Sockets über `modifier.properties.inputs.<Socket_N>.value = collection` gesetzt (gekapselt in `modifier_io.set_input`). |
| Sample Index | `GeometryNodeSampleIndex` vorhanden (für `conserve_mass`). |
| Attribute Statistic | `GeometryNodeAttributeStatistic` (data_type FLOAT, domain POINT). Inputs `Geometry`, **`Selection`** (Bool-Feld), `Attribute`; Outputs `Mean`/`Median`/`Sum`/`Min`/`Max`/`Range`/`Std`/`Variance`. Mit Selection = Maske → gewichtete Reduktion über eine Teilmenge (E4-S3: Fußabdruck-Schwerpunkt via `Mean` von X/Y über `carve>0`). |
| Named Attribute | `GeometryNodeStoreNamedAttribute` / `GeometryNodeInputNamedAttribute`. |
| Capture Attribute | `GeometryNodeCaptureAttribute`, nutzt `capture_items` (mehrere Werte je Node). |
| Grid-Primitive | **`GeometryNodeMeshGrid`** — nicht `GeometryNodeInputMeshGrid` (existiert nicht!). |
| Subdivide / Set Position / Switch | `GeometryNodeSubdivideMesh`, `GeometryNodeSetPosition`, `GeometryNodeSwitch` vorhanden. |
| Bake (Node) | `bpy.ops.object.geometry_node_bake_single()` — bakt einen einzelnen Bake-Node im Modifier. Dazu `..._delete_single`, `..._pack_single`, `..._unpack_single`. |
| Bake (Sim-Cache) | Bake: `bpy.ops.object.simulation_nodes_cache_bake(selected=True)`. **Free heißt `simulation_nodes_cache_delete`** (nicht `_free`!). Beide brauchen `temp_override(selected_objects=…, active_object=…, object=…)`. Memory-Bake läuft auch bei ungespeicherter `.blend`. Achtung: `hasattr(bpy.ops.object, name)` ist IMMER True (Stub) — Operatornamen nur per `dir(bpy.ops.object)` prüfen. Gekapselt in `utils/compat.py`. |
| **Modifier-Inputs setzen** | ⚠️ **Wichtige 5.2-Änderung!** Der alte Weg `modifier["Socket_N"] = wert` ist **weg** (`TypeError: id properties not supported`). Neu: `modifier.properties.inputs.<Socket_N>` ist ein Sub-Struct mit `.value` (Wert), `.type` (`VALUE`/`ATTRIBUTE`) und `.attribute_name`. Setzen: `modifier.properties.inputs.Socket_1.value = 0.08`. **Danach `object.update_tag()`**, sonst propagiert der Wert nicht in die Auswertung. `modifier.properties.inputs.Socket_1` selbst ist read-only (liefert das Sub-Struct, nicht den Wert). Gekapselt in `core/modifier_io.py`. |

## Solver-Erkenntnisse

**Böschungswinkel-Relaxation (E3-S2):** Ein Blur/Laplace-Glätter kann den Böschungswinkel NICHT
erzwingen — auf einem linearen Hang ist sein Wert null, ein zu steiler Hang würde nie kollabieren.
Stattdessen **Toppling** (echtes Nachbar-für-Nachbar-Verfahren) über `Sample Index` mit
Index-Arithmetik auf dem regulären Grid (`index = row*N + col`, Nachbarn bei ±1 und ±N;
Randzellen maskieren die wrap-around-Nachbarn weg). Symmetrischer Fluss (out A→B = in B←A) →
massenerhaltend außer bei Clamp auf h≥0.

- Diskretes 4-Nachbar-Grid hält minimal steiler als das Kontinuum → gemessener Winkel ~+3° zu hoch.
- Korrektur: Schwelle mit `_SLOPE_CALIB = 0.88` skalieren. Danach über 20–55° alle Zielwinkel
  innerhalb **±1,5°** (Test `tests/test_relax.py`, Toleranz ±3°).
- `_STABILITY = 0.25`: Anteil des Überschusses pro Iteration; darüber kann die 4-Nachbar-Summe
  in Oszillation überschießen.
- Messmethode im Test: steilen Materialkegel 600× relaxieren, Flanke (15–85 % der Spitzenhöhe)
  linear fitten, `atan(|slope|)` = gemessener Winkel. Höherer Winkel → höherer Kegel (Physik ok).

**Kohäsion + Wand-Slump (B1, 2026-08-21):** Zwei Relaxations-Bugs im Nahaufnahme-Maßstab:
1. Kohäsion war als **absolute Höhe** zur Schwelle addiert (`T = tan·calib·cell + cohesion`). Bei
   1,5-cm-Zellen ließ Sand-Kohäsion 0.02 eine ~62°-Wand stehen → Böschung wurde nie erreicht. Fix:
   Kohäsion als **Steigungs-Addend** vor der Zell-Skalierung: `T = (tan·calib + cohesion)·cell`.
   Kalibrierung bleibt gültig (Kegel-Test nutzt cohesion=0).
2. Das aufgehäufte Rim-Material relaxte **zurück ins vom Collider besetzte Loch** (carve>0) und
   wurde weggecarvt → kein bleibender Berm. Fix: In `ng_relax` Fluss in besetzte Nachbarzellen
   (carve≥eps) blocken (`_neighbour_free`) UND besetzte Zellen selbst nicht relaxieren
   (`self_free`), sonst Massen-Phantom. Danach: Wände slumpen auf ~34°, Berm bleibt stehen.

**Anti-Kriechen / Settle bei gehaltenem Collider (offen, E7-T14/B2):** Ein *dauerhaft* im Material
stehender Collider settelt kaum — der Berm kann nicht ins besetzte Loch, spreizt stattdessen langsam
über die Domain (max|Δh| fällt nur ~0.05→0.014 über 120 Frames). Nach dem *Abheben* settelt es in
~14 Frames. Der Deposit verteilt Pile zu weit → langsamer Schwanz; lokalere Ablage + Kriech-Deadband
sind der nächste Schritt.

**Gerichtete Bugwelle / Collider-Geschwindigkeit (E4-S3):** Die Bewegungsrichtung eines Colliders
NICHT aus dem Gradienten von `dcarve = carve − carve_prev` ableiten — der zeigt bei jedem
Fußabdruck (auch einem stehenden, nur tiefer eindrückenden) radial nach innen und würgt die
Rim-Diffusion ab (Berm verschwindet). Stattdessen die **Schwerpunkt-Verschiebung** des Fußabdrucks
nehmen: `v = centroid(carve>0) − centroid(carve_prev>0)` über `Attribute Statistic (Mean, Selection)`.
Das ist ein einziger Translationsvektor, exakt null bei Stillstand. Skalierung `v/cell_size`,
Clamp [−1,1] (kein Normalisieren nahe 0 → kein 0/0-Blow-up). Advektions-Korrektur der Pile-Inflow:
`s += 0.25·bow_wave·(vx·(P_−x−P_+x) + vy·(P_−y−P_+y))`, danach `max(s,0)`. Verifiziert: bw=0
symmetrisch, bw=0.7 vorne höher.

**Silhouettentreuer Contact-Carve (E4-S4):** Ein Strahl pro Vertex quantisiert die Abdruckkante
hart auf die Zellgröße → Facettierung bei Nahaufnahmen. Lösung: **Supersampling** der Kontaktzone
— 5er-Quincunx (Zentrum + 4 Ecken) mit Strahlen, die bis zu einer halben Zelle streuen, danach die
resultierende Fläche mitteln → Sub-Zell-Deckung, Kante folgt der Kontur. Spread über `Contact AA`
(0…1) skaliert; bei 0 kollabieren alle 5 Samples auf den Vertex → **bit-identisch** zum Einzelstrahl,
also keine Mehrkosten im Normalfall. Verifiziert: gedrehter flach-unterseitiger Cube, 0 → 88
partielle Kantenzellen bei gleicher Abdrucktiefe. Kein Repeat-Zone-Overhead (entrollt).

**Odd-even-Entkopplung / Schachbrett-Kamm (B2, der Kern der „Zacken“):** Eine Transport-Stufe,
die nur über die **vier Nachbarn** mittelt (`P_neu = 0.25·ΣP_Nachbar`, ohne Selbst-Term), ist auf
dem bipartiten Gitter *odd-even-entkoppelt*: der Pile springt pro Iteration von einem Schachbrett-
Untergitter aufs andere. Nach N Iterationen hat nur jede zweite Zelle überhaupt etwas bekommen —
numerisch nachgerechnet (Delta-Impuls, 6 Iterationen): `0.2 0.0 8.8 0.0 54.9 0.0 97.7 …`, also
**exakt 0** dazwischen. Genau das ist der Zahn-Kamm auf dem Berm. Fix: Selbst-Term behalten
(`w_self = 1 - spread`, je Nachbar `spread/4`) → gleicher Impuls wird `1.1 7.2 30.2 76.5 108.7 …`.
Gemessen am Feld: Schachbrett-Amplitude 0.174 mm → 0.002 mm. Nebeneffekt: die Ablage wird
*lokaler* (σ ≈ sqrt(iters·spread/2) Zellen statt 1 Zelle pro Iteration), was den langsamen
Berm-Schwanz und den Dauer-Churn aus B2(b) gleich mit erledigt.

**Masken nie auf einen Pro-Frame-Delta stützen (B2):** `gfx_carve` ist der Schnitt *dieses Frames*
— unter einem Collider, der pro Frame einen Bruchteil einer Zelle weiterrückt, ist er nur am
Vorderrand ≠ 0 und flackert zellweise. Masken, die darauf gebaut waren (Relaxation blockt besetzte
Zellen, Deposit unterscheidet frei/besetzt), haben deshalb den Graben geriffelt: Sohle
`20 27 20 28 20 29 …`. Neu: `gfx_occ` = **Deckung 0..1** aus demselben Quincunx-Raycast
(`Is Hit AND Unterseite <= alte Oberfläche + eps`, über die 5 Samples gemittelt). Bleibt 1, solange
der Collider steht, ist sub-zellular und flackert nicht → Sohle danach exakt flach. `gfx_occ_prev`
(gleicher Shift wie `carve_prev`) liefert außerdem den Bewegungsvektor als Schwerpunkt-Verschiebung
des *ganzen* Fußabdrucks statt nur des frisch geschnittenen Streifens.

**Advektion als Gather-Gewicht, nicht als additiver Term (B2):** Die Bugwellen-Korrektur additiv
aufzuschlagen und danach `max(s,0)` zu clampen **erfindet Masse** — jede Zelle, deren Zwischenwert
negativ wäre, wird auf 0 angehoben. Bei schwacher Advektion fällt das nicht auf; dreht man die
Transportweite hoch, explodiert das Feld (gemessen: 2.8 m Materialhöhe auf 0.08 m Schicht). Fix:
den Bias in **dieselbe normierte Gather-Maske** legen — der Upwind-Nachbar bekommt Zusatzgewicht
(`bias·bow_wave·max(±v,0)`), alle Gewichte durch ihre Summe geteilt. Damit ist die Stufe per
Konstruktion nicht-negativ, monoton und massenerhaltend; der Clamp entfällt. Zentrale Differenzen
sind hier ohnehin falsch: sie sehen die Ein-Zell-Mode gar nicht, der Kamm wächst frei mit.

**Static Friction / Haften (P1) — zwei Schwellen, nicht eine:** Die Relaxation zieht Material ab,
wenn die Höhendifferenz eines Nachbarpaars die stabile Stufe `T = (tan(repose)*calib + cohesion)*cell`
überschreitet. Erhöht man `T` einfach, steigt der *effektive* Repose-Winkel überall → die
Kalibrierung (und die B1/Repose-Tests) brechen. Für Haftung stattdessen **zwei Schwellen**: `T_stop`
(= altes `T`, das Ziel) und `T_start = T_stop + stickiness*cell` (Losbrech-Schwelle). Ein Paar
tauscht Material nur, wenn `|diff| > T_start`, und relaxiert dann Richtung `T_stop`. Zwischen den
Schwellen ist es *fest* → Material bleibt in Rillen liegen, Haufen sacken nicht flach. Wichtig für
Massenerhaltung: die Gate-Bedingung (`> T_start`) und der Betrag (`- T_stop`) müssen für Aus- und
Einstrom identisch sein, dann gilt weiter *A→B-Ausstrom == B←A-Einstrom* (symmetrisch). Bei
`stickiness = 0` ist `T_start == T_stop` → bit-gleich zum reinen Toppling, Repose-Kalibrierung
unangetastet. Verifiziert: 34°-Spike hält mit stickiness=0.3 rund 6° steiler.

**Swept Carve (E3-S5, löst die zeitliche Unterabtastung von B2):** Substeps NICHT als Schleife über
die ganze Solver-Kette (Carve+Deposit+Relax N×) bauen — die Instabilität sitzt allein im
Carve-Sampling, Relax/Deposit N× laufen zu lassen ist reine Verschwendung. Stattdessen nur den
*Carve* substeppen: die Eindrück-Tiefe ist unabhängig von der Position (feste Unterseite), also ist
die Tiefe an einer Zwischenposition gleich der aktuellen Tiefe *einen Bruchteil des Bewegungsvektors
zurück*. Damit braucht es KEINEN Geometrie-Move und keinen zweiten Raycast: `surf_q` (Quincunx-
Ergebnis) per **Sample Index** an Zell-Offset `round(v/cell · t/T)` lesen, über die Taps das Minimum
(tiefster Schnitt) nehmen. `v` ist die Footprint-Schwerpunkt-Verschiebung (gleicher Schätzer wie die
Bugwelle), gegated auf 0 falls nicht *beide* Frames Kontakt hatten (erster Touch smeart sonst).
Zwei Invarianten fallen gratis ab: (1) `|v| < 1 Zelle` → Offsets runden auf 0 → jeder Tap trifft die
eigene Zelle → **bit-identisch** zum Einzel-Sample, also langsame Bewegung unverändert bei jeder
Substep-Zahl (E3-T21) und der Contact-AA-Pfad (stehender Collider) unangetastet; (2) das Minimum
senkt die Oberfläche nur ab → erfindet nie Masse. Unrollt auf `_MAX_SUBSTEPS=4` Taps, per `t<=T`
maskiert (kein Repeat-Zone-Overhead). Verifiziert: schneller Drag Sohlen-Riffel ~0.9→~0.2 mm bei
T=3, visuell durchgehende Spur.

**Zeitliche Unterabtastung bleibt übrig (→ E3-S5 Substeps):** Pile entsteht nur dort, wo der
Collider *in diesem Frame* schneidet. Rückt er mehrere Zellen pro Frame, legt er pro Frame einen
Klumpen ab. Gemessen: Riffel-Periode = Weg pro Frame, 1.9 Zellen → Periode 2, 2.9 → 3, 3.8 → 4.
Kein räumliches Nachglätten hilft (ein Verschmieren längs der Bahn hat die Amplitude sogar
*erhöht*, 10 mm → 16 mm, weil es zusätzlich Material in den Graben trägt). Das braucht echte
Substeps.

**Field-Re-Evaluation (wichtiger GN-Fallstrick, E3-S3):** Named-Attribute-Felder
(`InputNamedAttribute`) werden gegen **die Geometrie neu ausgewertet, durch die sie fließen** —
nicht einmalig eingefroren. Wenn man `gfx_h` speichert und danach ein Wert, der `gfx_h` liest
(z. B. `carve = surface_old - new_surface` mit `surface_old = base + read_h`), gegen die bereits
überschriebene Geometrie ausgewertet wird, liest er das NEUE h → Ergebnis kollabiert auf 0.
**Regel:** Ein Attribut, das gelesen UND geschrieben wird (`gfx_h`), immer **zuletzt** speichern —
nachdem alle abgeleiteten Werte (carve/pile/comp) berechnet und gespeichert sind. Alternativ
`Capture Attribute` zum Einfrieren. Reihenfolge in `ng_ground_sim`: carve → pile → comp → h.

**Konsequenzen für den Code:**

- Das Grid erzeugen wir als echtes Mesh am Domain-Objekt (`bpy.ops.mesh.primitive_grid_add`
  bzw. direkte Mesh-Konstruktion), unabhängig vom GN-Grid-Primitive.
- `core/ng_builder.py` adressiert Sockets ausschließlich über `identifier`, nie über Index.
- Für den Bake bevorzugen wir einen expliziten **Bake-Node** im Display-Zweig
  (`geometry_node_bake_single`), weil das pro Modifier steuerbar ist; der Sim-Cache-Bake bleibt
  als Fallback. Endgültige Wahl fällt bei E7.
