# STEP-Dateien in CATIA verwenden

> Die erzeugte Datei enthält reine Geometrie. Sie ist **kein geprüftes Maschinenprogramm**. Vor dem Fräsen ist eine Simulation in CATIA beziehungsweise im NC-Postprozessor zwingend erforderlich.

---

## Was in der Datei steht

```
Compound
├── Solid  Referenzplatte
│          exakte Plattenabmessungen, geschlossener BRep
│          6 Flächen, 12 Kanten, 8 Eckpunkte — alle auswählbar
└── Wire   Fräsbahn
           je Rasterlinie eine Kurve vom Grad 1
           dazwischen kurze gerade Verbindungen
           ein durchgehender Zug von Anfang bis Ende
```

Beide Elemente liegen in einer Datei, bleiben aber getrennt auswählbar.

## Koordinatensystem

| Element | Z-Wert |
| --- | --- |
| Sicherheitsfahrt | `+1 mm` (einstellbar) |
| Plattenoberseite | `0` |
| Frästiefe | negativ, höchstens die eingestellte maximale Tiefe |
| Plattenunterseite | `−Plattenstärke` |

X0/Y0 liegt in der **linken unteren Ecke** der Platte. Die Einheit ist Millimeter.

## STEP öffnen

1. *Datei → Öffnen*, die `.step`-Datei auswählen.
2. Falls nach der Einheit gefragt wird: **Millimeter**.
3. Im Strukturbaum erscheinen der Plattenkörper und der Linienzug als getrennte Einträge.

Erscheint nur ein leerer Eintrag oder gar nichts, siehe [Mögliche Probleme](#mögliche-probleme-mit-älteren-step-übersetzern).

## Referenzplatte verwenden

Der Quader dient als Bezug, nicht als Rohteil im Sinne der Fertigung. Sinnvolle Verwendungen:

- **Oberseite als Bezugsebene.** Sie liegt exakt auf Z = 0 und definiert damit die Werkstücknull-Ebene.
- **Linke untere Kante als Nullpunkt.** Der Eckpunkt bei (0, 0, 0) ist der Ursprung des gesamten Modells.
- **Seitenflächen zum Ausrichten** des Spannmittels oder zum Ableiten von Anschlägen.
- **Maßkontrolle**: Ein Messen der Platte muss exakt die eingestellten Werte liefern. Der Prüfbericht bestätigt das bereits automatisch, eine Sichtprüfung schadet trotzdem nicht.

Wird die Platte nicht gebraucht, lässt sie sich im Projekt über `output.include_reference_plate: false` abschalten.

## Drahtkörper auswählen

Der Linienzug ist die eigentliche Nutzlast.

1. Im Strukturbaum den Eintrag der Bahn auswählen — nicht den Solid.
2. Prüfen, dass es sich um **einen** zusammenhängenden Zug handelt und nicht um lose Einzelkurven. In den Eigenschaften sollte ein durchgehender Wire erscheinen.
3. Die Bahn beginnt am ersten Punkt der ersten Rasterlinie und endet am letzten Punkt der letzten. Beide liegen auf Sicherheitshöhe.

## Führungselemente übernehmen

Für eine Bearbeitung in der Fertigungsumgebung:

1. Werkstücknull auf den Ursprung legen (linke untere Plattenecke, Oberseite).
2. Den Drahtkörper als **Führungselement** beziehungsweise Leitkurve einer Bahnoperation zuweisen.
3. Als Werkzeug einen V-Nutfräser mit dem im Projekt eingestellten Winkel anlegen. Die Werkzeugnummer aus der Projektdatei (Standard T246) ist dafür der Anhaltspunkt.
4. **Keine Werkzeugkorrektur quer zur Bahn.** Die Bahn ist bereits die Mittellinie der Nut; eine Radiuskorrektur würde sie verschieben.
5. Sicherstellen, dass die Z-Werte der Bahn übernommen und nicht durch eine feste Zustelltiefe ersetzt werden. Genau diese Z-Werte tragen das Bild.

Vorschübe, Drehzahlen und Kühlung werden bewusst **nicht** vorgegeben. Diese Werte hängen vom Material, vom Werkzeug und von der Maschine ab.

## Vor dem Fräsen

1. **Simulation fahren.** Materialabtrag simulieren und das Ergebnis mit der Vorschau der Anwendung vergleichen.
2. **Z-Grenzen prüfen.** Kein Punkt der Bahn darf tiefer liegen als die freigegebene maximale Tiefe. Der Prüfbericht enthält das gemessene Z-Minimum.
3. **Leerfahrten prüfen.** Alle Verbindungen müssen auf Sicherheitshöhe liegen. Auch das steht im Prüfbericht.
4. **Reststärke prüfen.** Plattenstärke minus maximale Frästiefe. Unter 0,5 mm wird die Platte kritisch.
5. **Probefräsung** auf Restmaterial, bevor das eigentliche Werkstück eingespannt wird.

## Mögliche Probleme mit älteren STEP-Übersetzern

### Leerer geometrischer Satz

**Symptom:** Die Datei öffnet sich, der Baum zeigt einen Eintrag, aber nichts ist sichtbar oder auswählbar.

**Ursache:** Ältere STEP-Übersetzer stolpern über einzelne B-Splines mit zehntausenden Polen und liefern dann eine leere Menge.

**Vorbeugung:** Diese Anwendung erzeugt bewusst **nie** eine einzige große B-Spline. Je Rasterlinie entsteht eine handhabbare Kurve vom Grad 1. Tritt das Problem dennoch auf, hilft eine stärkere Vereinfachung oder ein größerer Linienabstand — beides senkt die Zahl der Pole je Kurve.

### Sehr langer Import

**Symptom:** CATIA rechnet minutenlang oder friert scheinbar ein.

**Ursache:** Zu viele Stützpunkte insgesamt.

**Abhilfe:**

| Maßnahme | Wirkung |
| --- | --- |
| Vereinfachungsstufe „CATIA – stark vereinfacht" | Standard, rund 98 % weniger Punkte |
| Linienabstand erhöhen (2 → 3 mm) | rund ein Drittel weniger Linien |
| Motivrand verkleinern | kürzere Linien an den Rändern |
| Motiv kleiner platzieren | weniger Linien insgesamt |

Die Oberfläche zeigt vor dem Export die Punktzahlen und eine Schätzung der Dateigröße. Als Richtwert: unter etwa 5.000 Stützpunkten importiert CATIA zügig.

### Bahn erscheint als viele Einzelkurven

**Symptom:** Statt eines Zuges liegen hunderte getrennte Kurven im Baum.

**Ursache:** Manche Übersetzer lösen den Wire beim Import in seine Kanten auf.

**Bewertung:** Geometrisch ist das gleichwertig — die Kanten liegen weiterhin in der richtigen Reihenfolge und teilen sich ihre Endpunkte exakt. Für eine Bahnoperation lassen sie sich in CATIA wieder zu einem Zug verbinden. Der Prüfbericht bestätigt vorab, dass die Datei einen durchgehenden Zug mit genau zwei offenen Enden enthält.

### Falsche Einheit

**Symptom:** Die Platte ist um den Faktor 25,4 zu groß oder zu klein.

**Ursache:** Der Import wurde auf Zoll gestellt.

**Abhilfe:** Import wiederholen und Millimeter wählen. Die Datei selbst gibt Millimeter an.

## Empfehlung

Für den Regelfall:

- Vereinfachungsstufe **„CATIA – stark vereinfacht"** beibehalten.
- Referenzplatte mit exportieren, sie kostet fast nichts und erleichtert das Ausrichten erheblich.
- Den **Prüfbericht** vor dem Import ansehen. Er beantwortet die Fragen „ist die Datei lesbar", „stimmen die Maße", „ist die Bahn zusammenhängend" und „wird die Tiefe eingehalten" bereits automatisch.
- Bei Problemen zuerst die Punktzahlen prüfen, nicht die Datei neu erzeugen.

## Was diese Anwendung nicht erzeugt

- **Keine .hop- oder .hopx-Dateien.** Diese Formate sind NC-Hops- und postprozessorspezifisch. Ohne belastbares Referenzformat wird hier nichts vorgetäuscht.
- **Keinen NC-Code.** Kein G-Code, keine APT-Quelle, keine Maschinensätze.
- **Keine Technologiedaten.** Keine Vorschübe, Drehzahlen, Zustellungen oder Kühlmitteleinstellungen.
- **Kein facettiertes STEP aus einem Relief.** Ein fein trianguliertes Relief als STEP zu exportieren würde enormen Speicher benötigen. Für Relief gilt STL, für V-Cutting STEP.
