# Architektur

## Überblick

```
┌──────────────────────────┐        multipart/form-data        ┌────────────────────────────┐
│  Frontend                │  ──────────────────────────────▶  │  Backend                   │
│  React 18 + TypeScript   │      POST /api/jobs               │  FastAPI + Pydantic        │
│  Vite                    │                                   │                            │
│                          │  ◀──────────────────────────────  │  Bildpipeline (OpenCV)     │
│  Schrittweise Oberfläche │      202 + Job-ID                 │  Geometrie (NumPy/SciPy)   │
│  Kein Login              │                                   │  STEP/STL (OpenCascade)    │
│  Keine Supabase          │  ──── GET /api/jobs/{id} ────▶    │  Vorschau (Matplotlib)     │
└──────────────────────────┘      Polling bis fertig           └────────────┬───────────────┘
                                                                            │
                                                              ┌─────────────▼──────────────┐
                                                              │  data/jobs/<uuid>/         │
                                                              │  upload.png  job.json      │
                                                              │  cleaned.png toolpath.png  │
                                                              │  model.step  model.stl     │
                                                              │  project.json report.json  │
                                                              └────────────────────────────┘
```

## Warum ein Backend statt einer reinen Browser-App

Naheliegend wäre gewesen, alles im Browser zu rechnen. Dagegen sprechen vier Punkte:

1. **OpenCascade gibt es im Browser praktisch nicht.** Eine belastbare STEP-Erzeugung mit gültigem BRep-Solid, sauberem Wire und anschließender Rückprüfung braucht OCC. Die WebAssembly-Portierungen sind groß, langsam und in ihrem Funktionsumfang eingeschränkt — gerade beim STEP-Schreiben und -Lesen.
2. **Die Rückprüfung ist Teil des Produkts.** Die Datei wird nach dem Schreiben erneut eingelesen und gegen 24 Einzelkriterien geprüft. Ohne echten STEP-Reader wäre das nicht möglich, und ohne diese Prüfung wäre die Zusage „gültige STEP-Datei" nicht belegbar.
3. **Speicher und Laufzeit.** Ein Arbeitsraster von 1600 × 1600 Pixeln plus Distanztransformation plus rund 160.000 Rohpunkte ist für einen Browser-Tab unangenehm, für Python mit NumPy eine Sache von Zehntelsekunden.
4. **Reproduzierbarkeit.** Bildverarbeitung im Browser hängt von Canvas-Implementierung, Farbprofilen und Skalierungsfiltern ab. Serverseitig ist das Ergebnis für alle Nutzer identisch.

Der Preis dafür ist ein eigener Dienst, der nicht serverless läuft. Das ist bewusst so gewählt und in der Bereitstellungsanleitung berücksichtigt.

## Komponenten

### Frontend (`frontend/`)

| Datei | Aufgabe |
| --- | --- |
| `src/App.tsx` | Zustand, Schrittnavigation, Import/Export von Projektdateien |
| `src/types/project.ts` | Typen des Projektformats, Standardwerte, Vereinfachungsstufen |
| `src/lib/toolCalc.ts` | Nutbreite, Reststärke, alle Eingabeprüfungen und Hinweise |
| `src/lib/projectFile.ts` | Import, Export, Migration, sichere Dateinamen |
| `src/lib/uploadCheck.ts` | Vorprüfung des Uploads im Browser |
| `src/api/client.ts` | HTTP-Zugriff, Übersetzung von Fehlerantworten |
| `src/hooks/useJob.ts` | Job starten und bis zum Abschluss verfolgen |
| `src/components/` | Formularfelder, Hinweise, Dropzone, die sechs Schritte |

Der Zustand liegt vollständig in `App.tsx` als ein `ProjectConfig`-Objekt. Es gibt bewusst keinen Zustandscontainer: die Anwendung hat einen einzigen Datensatz, und `useState` reicht dafür.

### Backend (`backend/app/`)

```
main.py                    FastAPI-Anwendung, CORS, Aufräumen beim Start
settings.py                Umgebungsvariablen, Auflösung des Arbeitsrasters
api/
  health.py                GET /api/health
  jobs.py                  Job- und Konfigurationsendpunkte
  deps.py                  Prozessweiter Jobspeicher
models/
  config.py                Projektformat, Vereinfachungsstufen, Migration
  job.py                   Jobstatus, Kennzahlen, Artefakte
  report.py                Prüfbericht
services/
  image_cleanup.py         Maske, kleine Inseln, Konturglättung, Zuschnitt
  tone_mapping.py          Platzierung auf der Platte, Helligkeit zu Tiefe
  motif_envelope.py        Motivkontur und Dilatation um den Motivrand
  raster_paths.py          Rasterlinien und Schlangenbahn
  simplify_paths.py        Glättung, Abtastung, Ramer-Douglas-Peucker
  step_export.py           OCC-Solid, Drahtkörper, STEP schreiben und lesen
  step_validation.py       Prüfbericht aus Bahn, Kennzahlen und Datei
  stl_export.py            Relief-Höhenkarte und wasserdichtes STL
  preview.py               Bahn-, Simulations- und Reliefvorschau
  job_runner.py            Reihenfolge der Pipeline, Fortschritt, Fehler
storage/
  job_store.py             UUID-Verzeichnisse, atomarer Status, Aufräumen
utils/
  geometry.py              Nutbreite, RDP, Polygonzuglänge
  filenames.py             sichere Dateinamen und Job-IDs
  validation.py            Uploadprüfung nach Dateiinhalt
  occ.py                   dünne Schicht über OCP (Version 7 und 8)
```

Die Trennung ist streng: `services/` kennt kein FastAPI, `api/` kennt keine Geometrie, `utils/` kennt weder das eine noch das andere. Keine Datei enthält die gesamte Logik.

## Datenfluss

```
Upload (bytes)
    │
    ▼  utils/validation.py       Inhalt, Größe, Pixelzahl prüfen
    │
    ▼  services/image_cleanup    Maske → Inseln entfernen → glätten → zuschneiden
    │                            ⇒ CleanedMotif (rgb, mask)
    │
    ▼  services/tone_mapping     skalieren, zentrieren, Raster in Plattengröße
    │                            Helligkeit → Dunkelheit → Frästiefe
    │                            ⇒ PlateRaster (mask, darkness, depth, cut)
    │
    ▼  services/motif_envelope   euklidische Dilatation um motif_margin_mm
    │                            ⇒ MotifEnvelope (mask, Konturen in mm)
    │
    ▼  services/raster_paths     Linienpositionen, Profil je Linie,
    │    + simplify_paths        Glättung → Abtastung → RDP,
    │                            Serpentine, Verbindungen auf Sicherheits-Z
    │                            ⇒ Toolpath (lines, connectors) + PathMetrics
    │
    ├─▶ services/preview         toolpath.png, simulation.png
    │
    ▼  services/step_export      Solid + Drahtkörper → Compound → STEP
    │
    ▼  services/step_validation  STEP erneut lesen, 24 Prüfungen
                                 ⇒ ValidationReport
```

Im Relief-Modus zweigt der Fluss nach `tone_mapping` ab: `stl_export.build_relief_surface` erzeugt die Höhenkarte, daraus entsteht ein geschlossenes STL, das ebenfalls erneut eingelesen und geprüft wird.

## Jobverarbeitung

```
POST /api/jobs
    │
    ├─ Konfiguration validieren       ─── Fehler ──▶ 422 mit lesbarer Meldung
    ├─ Bilddatei vollständig lesen
    ├─ Upload prüfen (Inhalt!)        ─── Fehler ──▶ 422
    ├─ Jobverzeichnis anlegen (UUID)
    ├─ Datei in das Verzeichnis schreiben   ◀── erst danach geht es weiter
    ├─ project.json schreiben
    ├─ BackgroundTask registrieren
    └─ 202 + Job
```

Zwei Punkte sind hier wichtig:

- **Der Hintergrundtask bekommt nur die Job-ID.** Ein `UploadFile` ist nach dem Ende des Requests geschlossen; es dem Task zu übergeben wäre ein sicherer Fehler. Die Bilddaten liegen deshalb vor dem Start vollständig auf der Platte.
- **Der Status wird atomar geschrieben.** `job_store.save` schreibt in eine temporäre Datei im selben Verzeichnis, ruft `fsync` und dann `os.replace`. Ein gleichzeitig lesender Request sieht nie einen halben Zustand.

Der Runner meldet nach jedem Schritt Fortschritt und Stufe (`reading_upload`, `cleanup`, `placement`, `envelope`, `toolpath`, `preview`, `step`, `validation`). Bekannte Fehlerklassen (`MotifNotFound`, `EmptyToolpath`, `StepExportError`, `StlExportError`) werden in verständliche Meldungen übersetzt; alles andere landet mit vollem Traceback im Log und als Typname plus Meldung beim Nutzer. Es gibt keine leeren `except`-Blöcke.

Für den MVP reichen `BackgroundTasks`. Bei mehreren gleichzeitigen Nutzern gehört an diese Stelle eine echte Warteschlange — der Jobspeicher ist bereits so geschnitten, dass nur `job_runner` ausgetauscht werden müsste.

## Bildpipeline

Ausführlich in [docs/algorithm.md](docs/algorithm.md). Der Kern:

1. **Ausgangsmaske.** Mit Alphakanal: `alpha > 24`. Ohne: `Luminanz < background_threshold` (Standard 0,95), also die Annahme eines hellen Hintergrunds. Keine KI-Freistellung.
2. **Komponenten.** Connected Components mit 8er-Nachbarschaft. Standardmäßig bleibt die größte Komponente; sonst alle oberhalb einer flächenrelativen Mindestgröße. Löcher innerhalb des Motivs werden nicht gefüllt.
3. **Glättung.** Morphologisches Öffnen und Schließen mit 3 × 3, danach Weichzeichnung und 0,5-Schwelle. Das rundet Rastertreppen ab, ohne die Topologie zu ändern. Verschwindet dabei alles, bleibt die ungeglättete Maske.
4. **Platzierung.** Zuschnitt auf die Maske, Skalierung in die nutzbare Fläche unter Wahrung des Seitenverhältnisses, Zentrierung. Kein Spiegeln, kein Drehen.
5. **Arbeitsraster.** Ein Bild in Plattengröße mit 4 Pixeln je Millimeter (bei sehr großen Platten automatisch gröber). Bildzeile 0 ist der obere Plattenrand; die Umrechnung `y = height_mm − (row + 0,5) × mm_px` wechselt in Werkstückkoordinaten.

## Geometriepipeline

1. **Motivhülle.** Distanztransformation des Maskenkomplements, alles innerhalb `motif_margin_mm × px_per_mm` gehört dazu. Das ist geometrisch sauber in alle Richtungen — anders als ein morphologischer Kernel, dessen Form den Abstand verzerrt.
2. **Linienpositionen.** Vom linken bis zum rechten Rand der Hülle im eingestellten Abstand, mittig im Motivbereich verteilt.
3. **Linienabschnitt.** Je Linie der oberste und unterste Punkt der Hülle. Die Linie existiert nur dazwischen — der rechteckige Bildhintergrund wird nie überfahren.
4. **Profil.** Tonwerte glätten, Schnittflags aus Maske und Schwelle, Z-Werte aus der Tiefenformel, beide Endpunkte auf Sicherheits-Z.
5. **Vereinfachung.** Abtastung im eingestellten Raster, dabei bleiben alle Wechsel zwischen Sicherheitshöhe und Frästiefe sowie der tiefste Punkt jedes Schnittabschnitts erhalten. Danach RDP. Verliert RDP dabei die maximale Tiefe um mehr als die Toleranz, wird der Punkt wieder eingefügt.
6. **Serpentine.** Linie 0 von oben nach unten, Linie 1 von unten nach oben, und so fort. Die Verbindung sitzt immer am gemeinsamen Ende beider Linien; eine Abweichung davon würde einen Abbruch auslösen statt still eine lange Diagonale zu erzeugen.

## STEP-Erzeugung

```
TopoDS_Compound
├── TopoDS_Solid   Referenzplatte, BRepPrimAPI_MakeBox
│                  6 Flächen, 12 Kanten, 8 Eckpunkte, geschlossener BRep
└── TopoDS_Wire    Fräsbahn
    ├── Edge  Rasterlinie 0     Geom_BSplineCurve, Grad 1, n Pole
    ├── Edge  Verbindung 0      gerade Kante, 2 Punkte
    ├── Edge  Rasterlinie 1     …
    └── …
```

Die bewusste Entscheidung gegen **eine** große B-Spline über die gesamte Bahn: ältere CATIA-STEP-Übersetzer erzeugen bei zehntausenden Polen gelegentlich einen leeren geometrischen Satz. Je Rasterlinie eine Kurve vom Grad 1 bleibt handhabbar und ist geometrisch exakt derselbe Polygonzug.

Grad 1 heißt: die Kurve verläuft exakt durch alle Pole, ohne Überschwingen. Die Knotenvielfachheiten sind `[2, 1, …, 1, 2]`, ihre Summe ist damit `Polzahl + Grad + 1`.

`BRepBuilderAPI_MakeWire` verbindet die Kanten in der richtigen Reihenfolge zu einem zusammenhängenden Drahtkörper. Platte und Drahtkörper liegen in einem Compound und werden mit `STEPControl_AsIs` geschrieben — dadurch bleiben sie in CATIA getrennt auswählbar.

## Prüfung nach dem Schreiben

Die Datei wird erneut eingelesen. Die Fräsbahn wird über die **freien Kanten** gefunden — Kanten ohne zugehörige Fläche. Rasterlinien halten ihre Positionsachse konstant, Verbindungen ändern sie; daran lassen sich beide Arten sicher unterscheiden und zählen. Der Zusammenhang wird über einen Graphen der Endpunkte geprüft: genau zwei offene Enden, keine Verzweigung, alle Kanten erreichbar.

Geprüft werden Lesbarkeit, Gültigkeit und Maße der Platte, Vorhandensein und Zusammenhang der Bahn, Zahl der Linien und Verbindungen, Z-Maximum und Z-Minimum, Übereinstimmung der Bahnhülle mit der berechneten Bahn (schließt Spiegelung aus) sowie das Fehlen leerer geometrischer Sätze.

## Abhängigkeiten

| Bibliothek | Wofür |
| --- | --- |
| FastAPI, Pydantic | API und Validierung |
| OpenCV (headless) | Maske, Komponenten, Distanztransformation, Skalierung |
| NumPy | Raster, Profile, Kennzahlen |
| SciPy | Gauß-Glättung der Tonwertprofile und Höhenkarten |
| Pillow | Ein- und Ausgabe von Bildern, Uploadprüfung |
| cadquery-ocp (OCP) | OpenCascade: Solid, Wire, STEP schreiben und lesen |
| numpy-stl | STL schreiben und zur Prüfung wieder lesen |
| Matplotlib | ausschließlich serverseitige Prüfvorschauen |

`utils/occ.py` kapselt den Unterschied zwischen OCP 7 und OCP 8; in Version 8 sind die NCollection-Klassen von `OCP.TColgp`/`OCP.TColStd` nach `OCP.collections` gewandert.
