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
| Sample Index | `GeometryNodeSampleIndex` vorhanden (für `conserve_mass`). |
| Named Attribute | `GeometryNodeStoreNamedAttribute` / `GeometryNodeInputNamedAttribute`. |
| Capture Attribute | `GeometryNodeCaptureAttribute`, nutzt `capture_items` (mehrere Werte je Node). |
| Grid-Primitive | **`GeometryNodeMeshGrid`** — nicht `GeometryNodeInputMeshGrid` (existiert nicht!). |
| Subdivide / Set Position / Switch | `GeometryNodeSubdivideMesh`, `GeometryNodeSetPosition`, `GeometryNodeSwitch` vorhanden. |
| Bake (Node) | `bpy.ops.object.geometry_node_bake_single()` — bakt einen einzelnen Bake-Node im Modifier. Dazu `..._delete_single`, `..._pack_single`, `..._unpack_single`. |
| Bake (Sim-Cache) | `bpy.ops.object.simulation_nodes_cache_bake()` — bakt alle Simulation Zones der Szene/Objekte. |

**Konsequenzen für den Code:**

- Das Grid erzeugen wir als echtes Mesh am Domain-Objekt (`bpy.ops.mesh.primitive_grid_add`
  bzw. direkte Mesh-Konstruktion), unabhängig vom GN-Grid-Primitive.
- `core/ng_builder.py` adressiert Sockets ausschließlich über `identifier`, nie über Index.
- Für den Bake bevorzugen wir einen expliziten **Bake-Node** im Display-Zweig
  (`geometry_node_bake_single`), weil das pro Modifier steuerbar ist; der Sim-Cache-Bake bleibt
  als Fallback. Endgültige Wahl fällt bei E7.
