# Algorithmen

Alle Längen in Millimetern, alle Winkel in Grad.

---

## 1. V-Nut-Geometrie

Ein V-Fräser mit Spitzenwinkel `α` erzeugt beim Eintauchen auf Tiefe `t` eine Nut der Breite

```
b = 2 · t · tan(α / 2)
```

| Winkel | Nutbreite bei 1,2 mm Tiefe |
| --- | --- |
| 60° | 1,39 mm |
| 90° | 2,40 mm |
| 120° | 4,16 mm |

Die Umkehrung `t = b / (2 · tan(α/2))` beantwortet die Frage, wie tief man für eine gewünschte Nutbreite fahren muss.

Zwei Kennwerte werden daraus laufend abgeleitet:

- **Reststärke** = Plattenstärke − maximale Frästiefe. Unter 0,5 mm wird gewarnt, bei ≤ 0 abgelehnt.
- **Überschneidung**: Ist `b` größer als der Linienabstand, überlappen sich benachbarte Nuten. Das ist für flächige Graustufenbilder oft gewollt, für getrennte Linien nicht. Die Oberfläche weist darauf hin, blockiert aber nicht.

Implementierung: `backend/app/utils/geometry.py`, `frontend/src/lib/toolCalc.ts`.

---

## 2. Tonwert zu Tiefe

### Graustufen

Luminanz nach Rec. 709 auf den Bereich 0…1 normiert:

```
L = 0,2126 · R + 0,7152 · G + 0,0722 · B
```

Kein einfacher Mittelwert der Kanäle: Grün trägt zur wahrgenommenen Helligkeit deutlich mehr bei als Blau, und das Ergebnis soll dem Seheindruck entsprechen.

### Dunkelheit

```
d = 1 − L          innerhalb der Motivmaske
d = 0              außerhalb
```

Außerhalb der Maske ist die Dunkelheit definitionsgemäß null. Damit kann dort nie geschnitten werden, unabhängig davon, welche Farbe das Ausgangsbild an dieser Stelle hatte.

### Schwelle und Tiefe

```
geschnitten  ⟺  Maske ∧ (d > tone_threshold)

z = −max_depth · d^gamma      wenn geschnitten
z = +clearance_z              sonst
```

anschließend `z ≥ −max_depth` erzwungen.

- **`tone_threshold`** (Standard 0,055) hält sehr helle Stellen ungeschnitten. Ohne Schwelle würde jedes Rauschpixel eine minimale Nut erzeugen.
- **`gamma`** (Standard 1,0) verbiegt die Kennlinie. Werte über 1 machen mittlere Tonwerte flacher und betonen nur die dunkelsten Stellen; Werte unter 1 heben mittlere Tonwerte an.

Die Schwelle wirkt auf die **rohe** Dunkelheit, das Gamma erst in der Tiefenformel. Dadurch verschiebt eine Gammaänderung nicht ungewollt die Grenze zwischen geschnitten und ungeschnitten.

Implementierung: `backend/app/services/tone_mapping.py`.

---

## 3. Motivkontur und Motivhülle

### Ausgangsmaske

Mit Alphakanal: `alpha > 24`, also unter etwa 9 % Deckkraft gilt ein Pixel als transparent.

Ohne Alphakanal: `L < background_threshold` (Standard 0,95). Das entspricht der Annahme eines hellen Hintergrunds. Bewusst **keine** KI-Freistellung — das Ergebnis soll reproduzierbar und erklärbar bleiben.

### Bereinigung

1. **Connected Components** mit 8er-Nachbarschaft.
2. Standardmäßig bleibt nur die **größte** Komponente. Alternativ (`keep_largest_component: false`) alle Komponenten oberhalb von `min_component_area_ratio × Bildfläche`, mindestens 4 Pixel.
3. **Konturglättung**: morphologisches Öffnen und Schließen mit einem 3 × 3-Ellipsenkern, danach Gauß-Weichzeichnung (σ = 0,8) mit 0,5-Schwelle.

Der letzte Schritt rundet Rastertreppen ab, ohne Löcher zu schließen oder die Topologie zu verändern. Löscht er ein sehr dünnes Motiv vollständig aus, wird die ungeglättete Maske behalten.

### Platzierung

```
nutzbare Breite  = Plattenbreite  − 2 · Plattenrand
nutzbare Höhe    = Plattenhöhe    − 2 · Plattenrand
Maßstab          = min(nutzbare Breite / Motivbreite, nutzbare Höhe / Motivhöhe)
```

Das Motiv wird auf seine Maske zugeschnitten, mit diesem Maßstab skaliert (INTER_AREA beim Verkleinern) und mittig in ein Arbeitsraster in Plattengröße gesetzt. Weder gespiegelt noch gedreht.

**Bildzeile 0 ist der obere Plattenrand.** Die Umrechnung lautet

```
x = (col + 0,5) · mm_je_pixel
y = Plattenhöhe − (row + 0,5) · mm_je_pixel
```

Das Minuszeichen dreht die Zeilenrichtung um — das ist der Wechsel von Bild- in Werkstückkoordinaten, keine Spiegelung. Ohne diesen Schritt stünde das Motiv auf dem Kopf.

Das Arbeitsraster hat standardmäßig 4 Pixel je Millimeter. Bei 2 mm Abtastabstand sind das acht Rasterpunkte je Abtastschritt — fein genug, um keine Details zu verlieren. Sehr große Platten senken die Auflösung automatisch, damit das Raster unter 30 Megapixeln bleibt.

### Hülle

Die Bahn soll der Motivkontur plus `motif_margin_mm` folgen. Umgesetzt als **euklidische Dilatation** über die Distanztransformation:

```
Abstand   = distanceTransform(¬Maske, DIST_L2)
Hülle     = Maske ∨ (Abstand ≤ motif_margin_mm · px_je_mm)
```

Ein morphologischer Kernel wäre naheliegender, verzerrt den Abstand aber je nach Kernelform — ein Rechteckkern wächst diagonal um den Faktor √2 zu weit. Die Distanztransformation liefert in alle Richtungen denselben Abstand.

Bei 5 mm Rand und 4 px/mm entspricht das exakt 20 Pixeln.

Implementierung: `backend/app/services/image_cleanup.py`, `motif_envelope.py`.

---

## 4. Motivbegrenzte Schlangenbahn

### Linienpositionen

Für vertikale Richtung: alle Spalten, in denen die Hülle vorkommt, ergeben `x_min` und `x_max`. Darin werden Positionen im Abstand `line_spacing_mm` verteilt und mittig ausgerichtet:

```
Anzahl  = ⌊(x_max − x_min) / Abstand⌋ + 1
Start   = x_min + ((x_max − x_min) − (Anzahl − 1) · Abstand) / 2
```

### Linienabschnitt

Für jede Position wird die zugehörige Spalte der Hülle betrachtet. Der **oberste** und der **unterste** Punkt begrenzen die Linie. Kommt die Hülle in dieser Spalte nicht vor, entfällt die Linie.

Dadurch läuft die Bahn nie über den rechteckigen Bildhintergrund oder die leeren Plattenbereiche. Genau das ist der Unterschied zu einer naiven Rasterung des gesamten Bildes.

### Profil

Entlang des Abschnitts:

1. Tonwerte mit `smoothing_distance_mm` glätten (Gauß, die Distanz ist als Halbwertsbreite gemeint, also σ = FWHM / 2,355).
2. Schnittflags = Maske ∧ (geglättete Dunkelheit > Schwelle). Die Verknüpfung mit der Maske verhindert, dass die Glättung den Schnitt über die Motivkontur hinausträgt.
3. Z-Werte nach der Tiefenformel, sonst Sicherheitshöhe.
4. **Beide Endpunkte auf Sicherheitshöhe** erzwingen.

### Schlangenrichtung

```
Linie 0:  oben  ──────────▶ unten
                            │  kurze Verbindung unten
Linie 1:  oben ◀────────── unten
          │  kurze Verbindung oben
Linie 2:  oben ──────────▶ unten
          …
```

Jede Linie merkt sich, an welchem Ende sie beginnt und endet (`high` oder `low`). Vor dem Verbinden wird geprüft, dass das Ende der einen Linie und der Anfang der nächsten dasselbe Ende bezeichnen. Stimmt das nicht, bricht die Erzeugung mit einer Meldung ab, statt still eine lange Diagonale über das Motiv zu legen.

### Verbindungen

- Immer auf Sicherheits-Z.
- Nur zwischen direkt benachbarten Linien.
- Immer am gemeinsamen oberen beziehungsweise unteren Ende.
- Der X-Anteil ist per Konstruktion genau ein Linienabstand.
- Der Y-Anteil folgt der Form der Hülle und ist an steilen Konturstellen am größten.

Der Prüfbericht begrenzt die längste Verbindung auf das Maximum aus dem dreifachen Linienabstand und einem Viertel der Motivausdehnung. Eine echte Rasterrückfahrt wäre so lang wie das Motiv hoch ist und fiele damit sofort auf.

Für horizontale Richtung gilt alles sinngemäß mit vertauschten Achsen: Linien mit konstantem Y, Verfahren entlang X, erste Linie von links nach rechts.

Implementierung: `backend/app/services/raster_paths.py`.

---

## 5. Vereinfachung für CATIA

Ein Arbeitsraster mit 4 px/mm erzeugt bei 185 Linien rund 163.000 Rohpunkte. Direkt exportiert wären das zehntausende Stützpunkte je Kurve — ältere CATIA-STEP-Übersetzer werden dabei extrem langsam oder scheitern.

Die Kette in dieser Reihenfolge:

### 5.1 Glättung

Gauß-Filter auf das **Tonwertprofil**, nicht auf die fertigen Z-Werte. Der Unterschied ist wesentlich: Wird erst geschwellt und dann geglättet, verschmieren die Übergänge zwischen Sicherheitshöhe und Frästiefe zu Rampen. Wird erst geglättet und dann geschwellt, bleiben sie hart, während das Rasterrauschen verschwindet.

### 5.2 Abtastung

Nur ungefähr alle `sample_distance_mm` wird ein Punkt behalten. Zusätzlich bleiben **immer** erhalten:

- der erste und der letzte Punkt,
- jeder Wechsel zwischen Sicherheitshöhe und Frästiefe (beide Seiten des Wechsels),
- der tiefste Punkt jedes zusammenhängenden Schnittabschnitts.

Ohne diese Ausnahmen würde die Abtastung genau die Merkmale treffen, auf die es ankommt.

### 5.3 Ramer-Douglas-Peucker

Auf dem Profil `(Weg, Tiefe)`:

1. Gerade zwischen erstem und letztem Punkt.
2. Punkt mit dem größten Abstand zu dieser Geraden suchen.
3. Ist der Abstand größer als die Toleranz: Punkt behalten und beide Hälften rekursiv behandeln. Sonst alle dazwischenliegenden Punkte verwerfen.

Die Umsetzung arbeitet iterativ mit einem Stapel, damit sehr lange Profile keine Rekursionsgrenze reißen. Der Abstand wird zum **Segment** gemessen, nicht zur unendlichen Geraden — bei stark gestauchten Profilen ist das stabiler.

Lange gleichmäßige Bereiche werden dadurch zu geraden Abschnitten, unbedeutende Tiefenabweichungen verschwinden, Wechsel zwischen Sicherheitshöhe und Frästiefe bleiben (ihre Abweichung ist mit über 1 mm weit über jeder Toleranz).

### 5.4 Maximale Tiefe erhalten

RDP kann den global tiefsten Punkt entfernen, wenn er nahe genug an der Verbindungsgeraden liegt. Weicht das Ergebnis dadurch um mehr als die Toleranz von der echten Tiefe ab, wird der Punkt an seiner Wegposition wieder eingefügt.

### 5.5 Stufen

| Stufe | Abtastung | Glättung | RDP-Toleranz | Ziel |
| --- | --- | --- | --- | --- |
| CATIA – stark vereinfacht | 2,0 mm | 2,0 mm | 0,18 mm | 90 % |
| CATIA – normal | 1,0 mm | 1,0 mm | 0,08 mm | 80 % |
| Fein | 0,5 mm | 0,3 mm | 0,03 mm | 50 % |

Standard ist die starke Vereinfachung. „Fein" ist nur nach ausdrücklicher Auswahl erreichbar und wird mit einem Hinweis auf die CATIA-Belastung versehen.

### 5.6 Kennzahlen

Berechnet werden Rohpunktzahl, vereinfachte Punktzahl, Reduktion in Prozent, durchschnittliche und maximale Punkte je Linie sowie eine Schätzung der STEP-Größe.

**Rohpunktzahl** ist dabei definiert als ein Punkt je Rasterpixel entlang jeder Linie — also das, was ein naiver Wandler ausgeben würde.

Bleibt die Reduktion unter 85 %, warnt der Prüfbericht und schlägt eine stärkere Vereinfachung vor. Typisch für die starke Stufe sind rund 98 bis 99 %.

Implementierung: `backend/app/services/simplify_paths.py`, `backend/app/utils/geometry.py`.

---

## 6. STEP-Struktur

### Koordinatensystem

| Element | Z |
| --- | --- |
| Sicherheitsfahrt | `+clearance_z_mm` |
| Plattenoberseite | `0` |
| Frästiefe | negativ, ≥ `−max_depth_mm` |
| Plattenunterseite | `−thickness_mm` |

X0/Y0 in der linken unteren Plattenecke.

### Aufbau

```
TopoDS_Compound
├── TopoDS_Solid  BRepPrimAPI_MakeBox(gp_Pnt(0, 0, −t), w, h, t)
└── TopoDS_Wire
    ├── Geom_BSplineCurve  Grad 1, Pole = Punkte der Rasterlinie 0
    ├── gerade Kante       Verbindung 0
    ├── Geom_BSplineCurve  Rasterlinie 1
    └── …
```

Eine B-Spline vom Grad 1 ist geometrisch exakt ein Polygonzug: die Kurve verläuft durch alle Pole, ohne Überschwingen. Sie wird aber als **eine** Entität exportiert statt als viele Einzelkanten.

Die Knoten sind `0, 1, …, n−1` mit Vielfachheiten `[2, 1, …, 1, 2]`. Deren Summe ist `n + 2 = Polzahl + Grad + 1`, wie die Definition es verlangt.

Bewusst wird **keine** einzige große B-Spline über die gesamte Bahn erzeugt. Bei zehntausenden Polen liefern ältere CATIA-STEP-Übersetzer gelegentlich einen leeren geometrischen Satz.

`BRepBuilderAPI_MakeWire` verbindet die Kanten in der richtigen Reihenfolge. Die Endpunkte fallen konstruktionsbedingt exakt zusammen — der Startpunkt jeder Verbindung ist der Endpunkt der vorherigen Linie.

Geschrieben wird mit `STEPControl_AsIs`. Der Solid landet als `manifold_solid_brep`, die Bahn als geometrischer Kurvensatz. Beide bleiben getrennt auswählbar.

---

## 7. Validierungsregeln

Nach dem Schreiben wird die Datei erneut eingelesen und geprüft.

### Bahn (unabhängig von der Datei)

| Prüfung | Kriterium |
| --- | --- |
| `bahn_vorhanden` | mindestens eine Rasterlinie |
| `verbindungsanzahl` | genau Linienzahl − 1 |
| `linienenden_auf_sicherheits_z` | erster und letzter Punkt jeder Linie auf `clearance_z` |
| `verbindungen_auf_sicherheits_z` | beide Endpunkte jeder Verbindung auf `clearance_z` |
| `verbindungen_am_gleichen_ende` | Ende der einen Linie = Anfang der nächsten |
| `schlangenrichtung_wechselt` | Richtung wechselt von Linie zu Linie |
| `keine_langen_rueckfahrten` | längste Verbindung ≤ max(3 × Linienabstand, ¼ der Motivausdehnung) |
| `maximale_tiefe_eingehalten` | Z-Minimum ≥ −`max_depth` |
| `sicherheitshoehe_ist_z_maximum` | Z-Maximum = `clearance_z` |
| `reststaerke_positiv` | Plattenstärke − maximale Tiefe > 0 |
| `bahn_innerhalb_der_platte` | alle Punkte innerhalb der Plattenabmessungen |

### Kennzahlen

| Prüfung | Kriterium |
| --- | --- |
| `punktreduktion` | mindestens 85 % |

### STEP-Datei

| Prüfung | Kriterium |
| --- | --- |
| `step_lesbar` | Datei lässt sich öffnen und liefert eine nicht leere Form |
| `referenzplatte_vorhanden` | genau ein Solid (sofern angefordert) |
| `referenzplatte_gueltig` | `BRepCheck_Analyzer` meldet gültig |
| `plattenabmessungen` | Breite, Höhe, Stärke und Lage der Oberseite auf 0,001 mm |
| `bahn_in_step_vorhanden` | freie Kanten vorhanden |
| `bahn_zusammenhaengend` | alle Kanten erreichbar, genau 2 offene Enden, keine Verzweigung |
| `anzahl_rasterlinien` | Kanten mit konstanter Positionsachse = Linienzahl |
| `anzahl_verbindungen` | übrige Kanten = Linienzahl − 1 |
| `step_z_maximum` | Z-Maximum der Bahn = Sicherheitshöhe |
| `step_z_minimum` | Z-Minimum ≥ −`max_depth` |
| `keine_spiegelung` | Bahnhülle in der Datei deckt sich mit der berechneten Bahn |
| `keine_leeren_koerper` | kein leerer geometrischer Satz |

Die Fräsbahn wird über die **freien Kanten** gefunden: Kanten ohne zugehörige Fläche. Rasterlinien halten ihre Positionsachse konstant, Verbindungen ändern sie — daran lassen sich beide Arten nach dem Wiedereinlesen sicher unterscheiden.

### Relief

| Prüfung | Kriterium |
| --- | --- |
| `stl_lesbar` | Dreiecke vorhanden |
| `stl_wasserdicht` | jede Kante gehört genau zwei Dreiecken |
| `stl_orientierung` | jede gerichtete Kante kommt genau einmal vor |
| `relief_abmessungen` | Breite und Höhe entsprechen der Platte |
| `relief_staerke` | Gesamtstärke ≤ Plattenstärke |

Die Orientierungsprüfung ist nicht redundant zur Wasserdichtheit: ein Netz kann geschlossen sein und trotzdem einzelne gegenläufig orientierte Dreiecke enthalten. Erst die gerichtete Kantenprüfung schließt das aus.

Implementierung: `backend/app/services/step_validation.py`, `stl_export.py`.
