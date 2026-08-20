# GroundFX — Technischer Plan

**Addon-Arbeitstitel:** `GroundFX` (Sand · Schnee · Schlamm)
**Ziel-Blender:** 5.2 (Extension-Format, `blender_manifest.toml`)
**Dokumentstand:** 2026-08-20 · Phase 1 (Planung)

---

## 1. Produktvision in einem Satz

Ein Blender-Addon, das per Knopfdruck eine deformierbare Bodenschicht aus Sand, Schnee oder
Schlamm erzeugt, die auf bewegte Objekte in Echtzeit reagiert — Spuren, Aufhäufen,
Verdrängung, Nachrieseln — mit Presets, Qualitätsstufen, Baking und fertigen Shadern.

### 1.1 Zwei gleichrangige Haupt-Use-Cases

1. **Dynamische Interaktion** (Referenzvideo): ein Objekt — z. B. eine Standard-Box — fährt durchs
   Material und verschiebt es. Es zählt flüssiges Feedback und durchgehende Spuren. → Live/Bake,
   Quality Low–Medium, EEVEE.
2. **Produktfotografie / Hero-Shot**: ein Objekt (Waffe, kleines Produkt) fällt in Sand oder
   Schnee, das Material setzt sich, dann wird ein **hochauflösendes Standbild** gerendert. Hier
   zählt maximale Abdruck-Schärfe entlang der **exakten Objekt-Silhouette**, ein glaubwürdiger
   aufgeworfener Rand (Berm) und ein sauberer Ruhezustand — nicht Echtzeit. → Bake auf einen
   Ruheframe bzw. Freeze-to-Mesh, Quality High–Ultra, **Cycles mit Displacement**.

Der zweite Use-Case verschiebt drei Prioritäten gegenüber der reinen Video-Vorlage:

- **Collider-Proxys müssen die Silhouette erhalten** (kein grober Convex Hull für Hero-Objekte;
  ein silhouettentreuer Modus wird Default für den Produktshot). → E4-S2 erweitert.
- **Ruhezustand-Qualität**: das Material muss nach dem Eintauchen sichtbar zur Ruhe kommen, ohne
  zu „kriechen". Ein „Settle & Freeze"-Ablauf gehört ins UI. → neue Story E7-S4.
- **Cycles-Displacement und Micro-Detail** steigen von „nice-to-have" zu „für Use-Case 2
  erforderlich". → E8 priorisiert den Cycles-Pfad mit.

Praktisch heißt das: Der Solver ist derselbe, aber es gibt einen **„Photo"-Workflow-Schalter**,
der Quality auf High/Ultra hebt, in Cycles rendert, Substeps für ein sauberes Eintauchen erhöht
und nach dem Ruhezustand automatisch einfriert.

---

## 2. Grundsatzentscheidung: Simulationsmodell

Die wichtigste Architekturentscheidung überhaupt. Drei Optionen:

| Modell | Was es kann | Was es nicht kann | Kosten/Frame |
|---|---|---|---|
| **A · 2.5D Heightfield** | Spuren, Fußabdrücke, Aufhäufen, Böschungswinkel, Bugwelle, Fließen, Verdichtung, Nachrieseln | Überhänge, Objekt komplett zuschütten, wegfliegende Brocken, Tunnel | **1–20 ms** |
| **B · Hybrid: Heightfield + Spray-Partikel** (Empfehlung) | wie A + aufspritzende Körner/Schneestaub, die zurück in den Boden fallen | dasselbe wie A für die Hauptmasse | **3–35 ms** |
| **C · Echte 3D-Granulate** (PBD/DEM in Geometry Nodes) | alles, physikalisch echt | praktisch nicht in Echtzeit; ~5–10 k Partikel = ein Sandhäufchen, keine Szene | **200 ms – Sekunden** |

**Entschieden am 2026-08-20: Modell B (Hybrid), als Ausbaustufe von A gebaut.**

Begründung:

- Blender hat **keinen MPM-/Granular-Solver**. Der klassische „Sand-Sim"-Look aus Houdini
  (POP Grains / Vellum Grains / MPM) ist in Blender nur mit massiven Kompromissen erreichbar.
- Das Heightfield löst genau die im Briefing genannten Effekte: *„hinterlassen Spuren, schieben
  Material weg, lassen es aufhäufen"*. Das sind **alles 2.5D-Phänomene**.
- Der Spray-Layer (B) liefert die visuelle Würze (Staubfahne, hochspritzende Körner) für
  ~10 % der Kosten einer echten Partikelsimulation, weil die Partikel nur gegen das
  **Höhenfeld** kollidieren (ein Lookup) statt gegen Geometrie (Raycast).
- C bleibt als Forschungs-Epic im Backlog (E12), nicht im Produkt.

> **Bewusst außerhalb des Scopes:** Objekte vollständig zuschütten, Überhänge, Material das über
> eine Tischkante fällt, wegfliegende Brocken. Wer das braucht, braucht einen anderen Solver.

**Ebenfalls entschieden: Einweg-Kopplung.** Objekte verformen das Material, das Material wirkt
nicht auf die Objekte zurück (kein Einsinken von Rädern, keine Bremswirkung im Schlamm). Das ist
keine reine Scope-Frage, sondern eine Architekturgarantie: Rigid-Body-Welt und Geometry Nodes
sind in Blender getrennte Systeme, eine Rückkopplung bräuchte zwingend einen Python-Handler pro
Frame — und genau der würde die Bake-Fähigkeit und Thread-Sicherheit des Solvers zerstören.

### 2.1 Warum kein GPU-Solver?

Geometry Nodes werden in Blender **auf der CPU** ausgewertet (multithreaded, SIMD-optimiert).
Es gibt keinen öffentlichen GPU-Compute-Pfad für GN. GPU-beschleunigt ist bei diesem Addon
ausschließlich das **Shading/Displacement** (EEVEE Next / Cycles). Ein echter GPU-Solver würde
ein C++-Modul mit eigenem Compute-Backend bedeuten — außerhalb des Addon-Scopes.

Konsequenz für die Umsetzung: Performance-Arbeit heißt hier **Zellzahl niedrig halten,
Iterationen minimieren, Sim-LOD und Display-LOD strikt trennen.**

---

## 3. Solver-Architektur (das Herzstück)

### 3.1 Datenmodell im Simulation State

Ein Grid-Objekt („Domain") trägt pro Vertex folgende Attribute im Simulation-Zone-State:

| Attribut | Typ | Bedeutung |
|---|---|---|
| `gfx_h` | Float | Materialhöhe über der Basis (die eigentliche „Masse") |
| `gfx_base` | Float | Untergrundhöhe (aus Terrain gesampelt, statisch → einmal berechnet) |
| `gfx_carve` | Float | Eindringtiefe des Colliders in diesem Frame (0 = kein Kontakt) |
| `gfx_carve_prev` | Float | Vorframe-Carve → liefert Bewegungsrichtung des Colliders ohne Python |
| `gfx_pile` | Float | Puffer für verdrängtes, noch nicht abgelegtes Volumen |
| `gfx_comp` | Float | Verdichtung 0–1 (getretener Schnee, festgefahrene Spur) → Shader |
| `gfx_wet` | Float | Feuchtigkeit 0–1 → Kohäsion **und** Shader (dunkler, glänzender) |
| `gfx_flow` | Vector | letzte Verdrängungsrichtung → anisotrope Shader-Streifen |
| `gfx_age` | Float | Frames seit letzter Störung → Antrocknen / Zuschneien |

### 3.2 Pipeline pro Frame (innerhalb der Simulation Zone)

```
[State t-1]
   │
   ├─ 1. DEPOSIT      h += emit_rate * falloff(emitter) * dt        "Drop / Regen / Fill"
   │
   ├─ 2. CARVE        Raycast nach unten auf die Collider-Collection
   │                  penetration = (base + h) - hit_y
   │                  h    -= penetration
   │                  pile += penetration * displacement_ratio
   │                  comp += penetration * compaction_rate      (Rest wird verdichtet)
   │
   ├─ 3. DISPLACE     pile → Nachbarn, gewichtet mit
   │                  grad(carve - carve_prev)  → Bugwelle/Berm vor und neben dem Objekt
   │                  (Blur Attribute, 1–2 Iterationen, maskiert auf carve == 0)
   │
   ├─ 4. RELAX        ┌ Repeat Zone × relax_iterations ───────────┐
   │   (Böschungs-    │  H      = base + h                        │
   │    winkel)       │  H_avg  = Blur Attribute(H, 1)            │
   │                  │  excess = max(0, (H - H_avg)              │
   │                  │            - tan(theta_repose) * cell_size│
   │                  │            - cohesion_yield)              │
   │                  │  h     -= excess * flow_rate              │
   │                  │  h     += Blur(excess * flow_rate, 1)     │ ← Masse zurück
   │                  └───────────────────────────────────────────┘
   │
   ├─ 5. AGING        comp -= recovery*dt ; wet = Blur(wet) ; age += 1
   │
   └─ [State t] ──► Display-Stufe (NICHT in der Sim!):
                     Subdivide (LOD) → Noise-Displacement → Normalen → Material
```

**Kernpunkt der Physik:** Der Böschungswinkel (*angle of repose*, Schritt 4) ist der Parameter,
der Sand von Schnee von Schlamm unterscheidet. Alles andere ist Feinabstimmung.

| Material | θ Böschungswinkel | Kohäsion | Fließrate | Dichte kg/m³ |
|---|---|---|---|---|
| Feiner trockener Sand | 34° | 0.02 | hoch | 1600 |
| Nasser Sand | 45° | 0.25 | mittel | 1900 |
| Pulverschnee | 40° | 0.10 | mittel | 80 |
| Nassschnee (Schneeball) | 62° | 0.60 | sehr niedrig | 450 |
| Dicker Schlamm | 18° | 0.45 | niedrig (zäh) | 1750 |
| Dünner Schlamm | 6° | 0.10 | hoch (dünnflüssig) | 1400 |

Die `cohesion_yield`-Schwelle in Schritt 4 ist ein **Bingham-artiges Fließkriterium**:
unterhalb der Schwelle fließt gar nichts. Genau das lässt Nassschnee als Wand stehen und
dicken Schlamm als Wulst hängen, während trockener Sand sofort nachrieselt.

### 3.3 Warum `Blur Attribute` statt manueller Nachbar-Indizierung

Auf einem Grid liefert `Blur Attribute` mit einer Iteration exakt das Mittel der vier
Kantennachbarn — also den diskreten Laplace-Operator, den Relaxation und Diffusion brauchen.
Der Node ist in C++ implementiert und multithreaded; ein manueller Nachbar-Lookup über
`Sample Index` bräuchte vier Sample-Nodes und ist grob 3–4× langsamer. Für `conserve_mass`
(nur High/Ultra) gibt es optional den exakten, symmetrischen Austausch über `Sample Index`.

### 3.4 Collider-Erfassung

Ein Raycast pro Grid-Punkt gegen die Collider-Collection ist der Flaschenhals. Gegenmaßnahmen:

1. **Proxy-Meshes:** Ein Operator erzeugt optional decimierte Proxys oder Convex Hulls — der
   Ray trifft 50 Tris statt 500 k Tris eines Charakters.
2. **Bounding-Box-Vorfilter:** Punkte außerhalb der vereinigten Collider-Bounding-Box
   überspringen den Raycast über einen `Switch` (spart real Zeit, da GN Switch-Zweige lazy
   auswertet).
3. **Collider-Geschwindigkeit ohne Python:** aus `carve - carve_prev` (Gradient). Keine Driver,
   keine Frame-Change-Handler, kein Python im Sim-Loop → bake-fest und threadsicher.

### 3.5 Die kritische Größe ist die Zellgröße, nicht die Auflösung

`cell_size = domain_size / resolution`. Ein Reifenprofil braucht ~2 cm, ein Fußabdruck ~5 cm,
eine sichtbare Fingerspur im Sand ~5 mm.

**Zielmaßstab (entschieden): Nahaufnahme, 1–3 m Domain.** Das ist der günstigste Fall überhaupt,
denn bei kleiner Domain wird jede Auflösungsstufe extrem fein:

| Domain | 64² | 128² | 256² | 512² |
|---|---|---|---|---|
| **2 m (Default)** | 3,1 cm | **1,6 cm** | 0,8 cm | 0,4 cm |
| 3 m | 4,7 cm | 2,3 cm | 1,2 cm | 0,6 cm |
| 8 m | 12,5 cm | 6,3 cm | 3,1 cm | 1,6 cm |

Bei 2 m Domain liefert bereits **Quality Medium (128²) 1,6 cm pro Zelle** — genug für
Fußabdrücke und grobe Reifenprofile bei nur 16 k Vertices. Quality High erreicht 8 mm und damit
Fingerspur-Detail. Der gewählte Maßstab macht das Addon also deutlich billiger als geplant.

**Defaults daraus:** Domain 2 × 2 m, Quality Medium, Materialhöhe 8 cm, Emitter-Radius 30 cm.

Das Addon zeigt die **effektive Zellgröße live im UI** und warnt, wenn sie über dem für das
gewählte Preset sinnvollen Wert liegt. Für große Szenen gilt: mehrere kleine Domains statt einer
riesigen (Backlog E6-S4, wegen des Nahaufnahme-Fokus auf P3 herabgestuft).

---

## 4. Performance-Budget

Zielhardware-Annahme: 8-Kern-Desktop-CPU. Die GN-Sim ist CPU-gebunden.

| Quality | Sim-Grid | Verts | Relax-Iter | Substeps | Spray-Cap | Display-LOD | Ziel ms/Frame |
|---|---|---|---|---|---|---|---|
| **Low** | 64² | 4 k | 2 | 1 | 0 | keine Subdiv | **< 2 ms** |
| **Medium** | 128² | 16 k | 4 | 1 | 5 k | 1× Subdiv | **3–6 ms** |
| **High** | 256² | 66 k | 6 | 2 | 20 k | 1–2× + Noise | **10–20 ms** |
| **Ultra** | 512² | 262 k | 10 | 3 | 80 k | 2× + Noise + Adaptive | **40–120 ms** (Bake empfohlen) |

Bei der Default-Domain von 2 m entspricht das 3,1 cm / 1,6 cm / 0,8 cm / 0,4 cm pro Zelle.
Für Nahaufnahmen ist **Medium der Arbeitsmodus und High der Renderfall**; Ultra braucht man
erst für formatfüllende Makroaufnahmen.

Skalierungsverhalten: Kosten ≈ `verts × substeps × (1 + relax_iter)`. Von High auf Ultra
vervierfacht sich die Vertexzahl **und** steigen die Iterationen → ungefähr 7× teurer. Das ist
beabsichtigt und wird im UI mit einer Ampel (grün/gelb/rot) plus geschätzten ms/Frame
kommuniziert.

**Regeln, die im Code hart durchgezogen werden:**

1. Detail-Displacement (Noise, Körnung, Ripples) passiert **nach** der Sim, nie darin.
2. Viewport- und Render-Auflösung sind getrennt (`Is Viewport`-Switch im Node-Tree).
3. Keine Python-Handler pro Frame. Der Solver ist rein node-basiert → bake-fähig.
4. Der Spray-Layer kollidiert gegen das Höhenfeld, nie gegen Geometrie.

---

## 5. Python-Architektur

```
groundfx/
├── blender_manifest.toml          Extension-Metadaten (kein bl_info mehr)
├── __init__.py                    register/unregister, Versions-Guard
├── core/
│   ├── constants.py               Node-/Attribut-/Socket-Namen zentral (keine Magic Strings)
│   ├── ng_builder.py              NodeTreeBuilder: Sockets, Links, Frames, Auto-Layout
│   ├── ng_library.py              ensure_node_group() + Versionsstempel + Migration
│   └── nodegroups/
│       ├── ng_ground_sim.py       Simulation Zone, Top-Level
│       ├── ng_deposit.py          Emission / Drop / Fill
│       ├── ng_collide.py          Raycast, Proxy, Penetration, Velocity
│       ├── ng_displace.py         Bugwelle / Berm
│       ├── ng_relax.py            Repeat Zone, Böschungswinkel
│       ├── ng_spray.py            Partikel-Layer (optional)
│       └── ng_display.py          LOD, Detail-Displacement, Normalen
├── shading/
│   ├── mat_builder.py             gemeinsame Bausteine (Triplanar-Noise, Wetness-Mix)
│   └── mat_sand.py / mat_snow.py / mat_mud.py
├── data/
│   ├── properties.py              PropertyGroups (Scene + Object)
│   ├── quality.py                 vier Qualitätsprofile als Daten
│   └── presets/*.json             Presets als Daten, nicht als Code
├── ops/
│   ├── op_add.py                  Add Sand/Snow/Mud
│   ├── op_preset.py               Apply / Save User Preset / Reset
│   ├── op_collider.py             Mark/Unmark Collider, Proxy erzeugen
│   ├── op_bake.py                 Bake, Free, Bake All, Freeze to Mesh
│   └── op_drop.py                 Modales Drop-Tool
├── ui/
│   ├── panels.py                  N-Panel + Physics-Properties-Tab
│   ├── menus.py                   Add > GroundFX
│   └── icons/
└── utils/
    ├── compat.py                  API-Abstraktion (5.x-Änderungen kapseln)
    └── perf.py                    Timing/Statistik-Overlay
```

### 5.1 Node-Groups: in Python generiert, nicht als `.blend` mitgeliefert

**Entscheidung: Node-Trees werden zur Laufzeit aus Python gebaut.**

| Kriterium | Python-Builder (gewählt) | `.blend` mitliefern |
|---|---|---|
| Git-diffbar | ✅ voll | ❌ binär |
| Blender-Versionsbindung | ✅ baut gegen die laufende Version | ⚠️ an Autoren-Version gebunden |
| Autorenkomfort bei 150+ Nodes | ⚠️ mühsam | ✅ komfortabel |
| Migration alter Szenen | ✅ Versionsstempel + Rebuild | ⚠️ Append-Duplikate |

Der Mehraufwand wird durch `ng_builder.py` abgefedert (deklarative Node-Definition,
Auto-Layout). Zusätzlicher Grund: In dieser Entwicklungsumgebung ist **kein Blender
installiert** — ein `.blend`-Asset könnte hier weder erzeugt noch verifiziert werden.
Python-Code ist ohne Blender-Instanz reviewbar.

### 5.1a Konventionen

- **Sprache:** UI-Beschriftungen, Property-Namen, Tooltips, Docstrings und Code-Kommentare
  durchgängig **Englisch** (Blender-Konvention, i18n-fähig). Projektdokumentation in `docs/`
  bleibt **Deutsch**.
- **Stil:** PEP 8, Zeilenlänge 99 (Blender-Standard), Type Hints an öffentlichen Funktionen.
- **Namensraum:** Alle Bezeichner mit dem Addon-Präfix, um Kollisionen mit anderen Addons
  auszuschließen (Operator-IDs, Attributnamen, Custom Properties, Node-Group-Namen).
- **Keine Magic Strings:** Jeder Name, der an zwei Stellen vorkommt, steht in `core/constants.py`.

### 5.2 Property-Anbindung

`obj.groundfx` → `GroundFXObjectSettings` mit `update=`-Callbacks, die Werte in die
Modifier-Inputs schreiben. Die Socket-Zuordnung läuft über eine Konstantentabelle
(`SOCKET["angle_of_repose"] = "Socket_7"`), **niemals** über geratene Indizes. Beim Rebuild
einer Node-Group werden die Identifier neu eingelesen und gecacht.

### 5.3 Caching-Strategie

Drei bewusst getrennte Stufen:

1. **Live** — kein Cache, die Sim läuft beim Abspielen. Nur Low/Medium sinnvoll.
2. **Bake** — Geometry-Nodes-Bake pro Modifier nach `//groundfx_cache/<objekt>/`.
   Frame-Range wählbar (Szene oder eigene). UI zeigt Cache-Größe auf Platte plus „Free".
3. **Freeze** — Sim-Ergebnis eines Frames als statisches Mesh ausgeben (für Stills/Export).

Verhalten bei Änderungen: Jede Änderung eines Solver-Parameters invalidiert den Bake. Das Addon
markiert den Cache als „veraltet" (gelbe Warnung), löscht ihn aber nie ungefragt.

---

## 6. Shader-Konzept

Ein gemeinsames Gerüst, drei Ausprägungen. Alle Materialien lesen die Sim-Attribute
`gfx_comp`, `gfx_wet`, `gfx_flow`, `gfx_h` per Attribute-Node — das Shading reagiert damit
direkt auf die Physik.

| | Sand | Schnee | Schlamm |
|---|---|---|---|
| Base | 2-Farb-Mix + Voronoi-Körnung | fast weiß, leichte Bläue in Vertiefungen (SSS) | dunkelbraun, Farbvariation |
| Spezialeffekt | Wind-Ripples entlang `gfx_flow` | Sparkle (hochfrequentes Voronoi, nur im Specular) | nasser Glanz, Pfützen in Senken |
| `gfx_comp` steuert | Spur dunkler und glatter | verdichtet = grauer, weniger Sparkle | Spur glänzender, glatter |
| `gfx_wet` steuert | dunkler, Roughness ↓, Kohäsion ↑ | Verlust des Sparkles, Richtung Firn | Viskosität, Reflexion |
| Micro-Displacement | Körnung, Bump | Bump + leichtes Displacement | Bump, Risse bei niedriger `wet` |
| EEVEE-Pfad | nur Bump | Bump + SSS-Approximation | nur Bump |
| Cycles-Pfad | optional Adaptive Displacement | dito + echtes SSS | dito |

Performance-Regel: Micro-Detail primär als **Bump/Normal**, echtes Displacement nur in Cycles
und nur ab Quality = High.

---

## 7. UI/UX-Konzept

**N-Panel „GroundFX"** in der 3D-View, plus schlanker Spiegel im Physics-Properties-Tab:

```
▾ GroundFX
  [ Add Sand ] [ Add Snow ] [ Add Mud ]        ← ein Klick = fertiges Setup
  [ ⭯ Drop Tool ]                              ← modal: klicken, ziehen, Material fällt

▾ Domain  (wenn ein GroundFX-Objekt aktiv ist)
  Element:    ● Sand  ○ Snow  ○ Mud
  Preset:     [ Fine Dry Sand      ▾ ]  [ Save ] [ Reset ]
  Quality:    [ Low | Medium | High | Ultra ]
              ⓘ 128² · 16 k Verts · Zelle 3.1 cm · ~4 ms/Frame  🟢
  Domain Size / Resolution / Origin

▾ Physik
  Böschungswinkel  34°   Kohäsion 0.02   Fließrate 0.8
  Dichte 1600      Verdichtung 0.3       Nachrieseln 0.1
  Feuchtigkeit 0.0                        [Advanced ▾]

▾ Collider
  [ Als Collider markieren ] [ Entfernen ]
  ☑ Cube            Proxy: Convex        Offset 0.01
  ☑ Character       Proxy: Decimate 5 %
  [ Proxys neu erzeugen ]

▾ Cache
  Status: 🟡 veraltet (Parameter geändert)   Größe: 214 MB
  Range: [Szene ▾]  1–250
  [ Bake ] [ Bake All ] [ Free ] [ Freeze to Mesh ]

▾ Material
  [ Sand_GroundFX ▾ ]  Farbe ▮  Rauheit 0.9  Detail 1.0
```

**Drop-Tool** (der „Video-Moment"): ein modaler Operator. Der User klickt in die Szene und zieht
einen Radius auf; das Addon legt einen Emitter an, aktiviert die Sim und startet die Wiedergabe.
Material fällt sofort und reagiert auf alles, was als Collider markiert ist.

---

## 8. Kompatibilität und Risiken

| Risiko | Wahrscheinlichkeit | Auswirkung | Gegenmaßnahme |
|---|---|---|---|
| Blender-5.2-API weicht von Annahmen ab (Bake-Operatoren, Node-Identifier, Simulation-Zone-Interna) | **hoch** | mittel | Alles Versionsabhängige in `utils/compat.py`; Feature-Detection statt Versionsvergleich; früher Smoke-Test in echter 5.2 |
| Keine Blender-Installation in dieser Umgebung → kein Selbsttest | **sicher** | **hoch** | Siehe Offene Frage 2. Andernfalls: mitgelieferte headless-Testskripte, die du ausführst und deren Ausgabe du zurückspielst |
| Raycast gegen High-Poly-Collider bricht die Performance ein | hoch | hoch | Proxy-System (E4), Bounding-Box-Vorfilter |
| Masseverlust durch blur-basierte Relaxation (Material „verdunstet") | mittel | mittel | Massebilanz-Test in der QA-Suite; `conserve_mass`-Modus für High/Ultra |
| Erwartungshaltung „echter 3D-Sand" wird von 2.5D nicht erfüllt | mittel | **hoch** | Offene Frage 1 vor Codebeginn klären |
| Bake-Dateien werden sehr groß (Ultra: 262 k Verts × 250 Frames) | hoch | mittel | Cache-Größenanzeige, Attributreduktion beim Bake, Warnung ab Schwellwert |

**Mindestversion:** Ziel ist 5.2. Ein Kompatibilitätspfad zurück auf 4.5 LTS ist technisch
möglich (Simulation Zones seit 4.0, Blur Attribute seit 4.0, Bake-Node seit 4.1), kostet aber
Zeit → siehe Offene Frage 5.

---

## 9. Meilensteine

| M | Name | Inhalt | Abnahmekriterium |
|---|---|---|---|
| **M1** | Walking Skeleton | E0, E1, E2 + minimales Carve | Addon installiert sich in 5.2; „Add Sand" erzeugt ein Grid; ein bewegter Würfel hinterlässt eine sichtbare Spur |
| **M2** | Physik | E3, E4 | Material häuft sich vor dem Objekt auf, rieselt im korrekten Böschungswinkel nach, mehrere Collider funktionieren |
| **M3** | Produkt | E5, E6, E7, E8, E9 | Alle drei Elemente, ≥ 8 Presets, vier Qualitätsstufen, Bake, drei Shader, vollständiges UI |
| **M4** | Politur und Release | E10, E11 | Spray-Layer, Benchmark-Suite grün, Doku, Beispielszene, v1.0 |

Detaillierte Aufschlüsselung: siehe `BACKLOG.md`.
Offene Punkte, die vor Codebeginn zu klären sind: siehe `OPEN_QUESTIONS.md`.
