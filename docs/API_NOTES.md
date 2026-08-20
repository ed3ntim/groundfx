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
| Bake (Sim-Cache) | `bpy.ops.object.simulation_nodes_cache_bake()` — bakt alle Simulation Zones der Szene/Objekte. |
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
