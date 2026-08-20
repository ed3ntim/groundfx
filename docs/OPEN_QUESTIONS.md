# GroundFX — Offene Fragen (Phase 2)

Diese Punkte sollten vor dem ersten Code geklärt sein. **Blockierend** heißt: eine andere
Antwort führt zu einer anderen Architektur, nicht nur zu anderen Defaults.

---

## ✅ Entschieden am 2026-08-20

| Frage | Entscheidung | Konsequenz |
|---|---|---|
| **F1 Simulationsmodell** | Höhenfeld + Spray-Layer (Modell B) | E3/E4 bauen den Höhenfeld-Solver, E10 (Spray) bleibt fest im Scope für M4 |
| **F2 Interaktion** | Nur Kollision, Einweg | Solver bleibt vollständig node-basiert und bake-fähig; kein Python im Frame-Loop. Rigid-Body-Rückwirkung ist ausdrücklich nicht Teil von v1.0 |
| **F3 Referenzvideos** | Der User beschreibt sie | *Ausstehend* — ich warte auf die Beschreibung, bevor ich Preset-Defaults und Look festzurre |
| **F4 Sprache** | UI und Code Englisch, Projektdoku Deutsch | Alle `bl_label`, Property-Namen, Tooltips, Docstrings und Code-Kommentare auf Englisch; `docs/*.md` und unsere Kommunikation auf Deutsch |
| **F8 Maßstab** | Nahaufnahme, 1–3 m Domain | Default 2 × 2 m. Medium (128²) = 1,6 cm/Zelle, High = 0,8 cm. E6-S4 (Follow-Domain) auf P3 herabgestuft, dafür Detailtreue hoch priorisiert |
| **F10 Zusatzfeatures** | Reifenprofil in der Spur · Material klebt am Objekt · Fallender Schnee | Als E13, E14, E15 im Backlog, alle P1 für Release 1.0. Winderosion, Decals und Heightmap-Export bleiben P2/P3 |
| **F12 Name** | **GroundFX** | Paket `groundfx`, Operatoren `groundfx.*`, Attribute `gfx_*`, Panel-Kategorie „GroundFX" |
| **F12 Git** | Ja, Repository initialisieren | `git init` samt `.gitignore` (Cache, `__pycache__`, Build-ZIPs, Referenzvideos) und Erstcommit der Planungsdokumente |
| **F6 Versionsspanne** | Nur Blender 5.2+ | Keine Kompatibilitäts-Altlasten; jede API gegen genau 5.2 verifiziert. `compat.BLENDER_MIN = (5,2,0)` |
| **F7 Render-Engine** | Cycles priorisiert | Shader zielen auf Cycles-Endqualität (echtes Displacement, SSS, korrekte Roughness). EEVEE bleibt lauffähig als schnelle Vorschau, ohne eigenen Feinschliff. Stützt Use-Case 2 (Produktfoto) |
| **F9 Verteilung** | Später evtl. Verkauf | Von Anfang an sauber (UI/Code Englisch steht bereits), aber Politur/Doku/Beispiele/i18n erst bei konkreter Verkaufsentscheidung. Kein Mehraufwand pro Feature jetzt |

---

## 🔴 Blockierend

### F1 — Simulationsmodell und Scope ✅ *entschieden: Modell B*

Reicht ein **2.5D-Höhenfeld** (Spuren, Aufhäufen, Fließen, Bugwelle), oder brauchst du zwingend
echte 3D-Effekte (Objekt versinkt vollständig, Material fällt über eine Kante, wegfliegende
Brocken)?

Hintergrund: Blender hat keinen Granular-/MPM-Solver. 2.5D kostet 1–20 ms pro Frame, echte
3D-Granulate in Geometry Nodes kosten Sekunden pro Frame bei wenigen tausend Partikeln.

**Meine Empfehlung:** Höhenfeld als Basis, plus optionaler Spray-Partikel-Layer für den
visuellen Impact (Modell B in `PLAN.md` §2).

### F2 — Interaktionsrichtung ✅ *entschieden: Stufe 1 (nur Kollision)*

Drei Ausbaustufen, jede teurer als die vorige:

1. **Einweg (Kollision):** Objekte verformen das Material. Objekte selbst bleiben unbeeinflusst.
2. **Zweiweg light:** Das Material wirkt auf Rigid Bodies zurück — ein Rad sinkt ein, ein Auto
   wird im Schlamm langsamer, eine Kugel bleibt im Sand liegen. Umsetzung über eine Kopplung
   Höhenfeld → Rigid-Body-Collider plus Widerstandskraft. Deutlicher Mehraufwand, und ein Teil
   davon muss zwangsläufig über Python-Handler laufen (Rigid-Body-Welt und GN sind getrennt).
3. **Soft-Deformation des Objekts:** Das Objekt selbst wird vom Material verformt. Sehr teuer,
   praktisch ein eigenes Produkt.

**Meine Empfehlung:** Stufe 1 für v1.0, Stufe 2 als klar abgegrenztes Epic danach. Stufe 3 nicht.

### F3 — Zugang zu den Referenzvideos 🟠 *Beschreibung ausstehend*

In dieser Entwicklungsumgebung gibt es weder `ffmpeg` noch Python noch einen Video-Decoder — die
beiden MP4s im Projektordner kann ich **nicht** abspielen oder in Einzelbilder zerlegen.
Bilder hingegen kann ich direkt ansehen.

Optionen:

- Du exportierst ein paar aussagekräftige Frames als PNG/JPG in den Ordner (am besten:
  Ausgangszustand, Moment der Interaktion, Endzustand, sowie eine Nahaufnahme der Oberfläche).
- Du erlaubst mir, `ffmpeg` (oder Python) lokal zu installieren, dann extrahiere ich die Frames
  selbst.
- Du beschreibst kurz, was in den Videos passiert — dann arbeite ich ohne Bildreferenz.

### F4 — Sprache ✅ *entschieden: UI/Code Englisch, Doku Deutsch*

- **UI-Sprache:** Englisch (Blender-Konvention, i18n-fähig, verkaufbar) oder Deutsch?
- **Code-Kommentare und Docstrings:** Englisch oder Deutsch?
- **Projektdokumentation:** aktuell Deutsch — so beibehalten?

**Meine Empfehlung:** UI und Code auf Englisch, Projektdoku auf Deutsch. Falls das Addon später
verteilt oder verkauft werden soll, ist alles andere ein Rückschritt.

---

## 🟡 Wichtig, aber nicht blockierend

### F5 — Blender-Version und Installationspfad

Du installierst Blender gerade. Ich brauche danach:

- den genauen Installationspfad (für `blender.exe --background`),
- die genaue Version (`5.2.x`).

Damit kann ich jeden Schritt headless selbst verifizieren, statt blind zu liefern — das hebt die
Qualität deutlich.

### F6 — Versionsspanne ✅ *entschieden: nur 5.2+*

Nur Blender 5.2+, oder soll auch 4.5 LTS unterstützt werden? Letzteres ist machbar
(Simulation Zones und Blur Attribute gibt es seit 4.0), kostet aber laufend Kompatibilitätsarbeit
in jedem Feature.

**Empfehlung:** ausschließlich 5.2+, sauber und ohne Altlasten.

### F7 — Render-Engine-Priorität ✅ *entschieden: Cycles priorisiert*

EEVEE Next (Echtzeit, Games/Previz) oder Cycles (Final Frames)? Das entscheidet, wie viel
Aufwand in Displacement, SSS und Sparkle fließt.

**Empfehlung:** beide unterstützen, EEVEE als Standard priorisieren, weil das Addon auf
Interaktivität ausgelegt ist.

### F8 — Maßstab und typischer Einsatzzweck ✅ *entschieden: Nahaufnahme, 2 m Default*

Was ist der Normalfall?

- **Nahaufnahme** (1–3 m Domain): Hand fährt durch Sand, einzelne Fußabdrücke, Produktshots.
- **Charakter/Fahrzeug** (4–15 m Domain): Figur läuft durch Schnee, Auto durch Schlamm.
- **Landschaft** (50 m+): Weite Fläche, Details aus der Distanz.

Das legt die Default-Domaingröße, die Preset-Kennwerte und die Priorität von E6-S4
(Follow-Object-Domain) fest.

**Annahme, falls keine Antwort kommt:** Charakter/Fahrzeug, 8 m Domain, Quality Medium.

### F9 — Zielgruppe und Verteilung ✅ *entschieden: später evtl. Verkauf*

Nur für dich, oder als Produkt (Blender Extensions Platform, Blender Market, Gumroad)?
Das beeinflusst Lizenzwahl, Umfang der Doku, i18n, Beispieldateien und den Polish-Aufwand.

### F10 — Zusatzfeatures ✅ *entschieden: Reifenprofil, Materialanhaftung, Schneefall*

Rangfolge wäre hilfreich:

- Reifenprofil-Muster in der Spur (statt nur einer glatten Rinne)
- Material bleibt am Objekt kleben (Schlammspritzer am Auto, Schnee an Schuhen)
- Fallender Schnee in der Luft, der sich auf der Domain ansammelt
- Winderosion und Dünenbildung bei Sand
- Fußabdruck-Decals als billige Alternative ohne laufende Simulation
- Export der Höhenkarte als Textur (für Game Engines)

### F11 — Zielhardware

Für die Kalibrierung der Performance-Budgets: CPU-Kerne, RAM, GPU? Die Zahlen in `PLAN.md` §4
gehen von einem 8-Kern-Desktop aus.

### F12 — Projektorganisation ✅ *entschieden: Name GroundFX, Git ja*

- Soll ich ein **Git-Repository** initialisieren? (Der Ordner ist derzeit keins — bei einem
  Projekt dieser Größe würde ich dringend dazu raten.)
- Name des Addons: Arbeitstitel ist `GroundFX`. Alternativen: `TerraFlow`, `GroundFX`,
  `Sandbox`, oder ein eigener Vorschlag von dir. Der Name geht in Paketnamen, IDs und Property-
  Namen ein — späteres Umbenennen ist unangenehm, deshalb jetzt festlegen.
