# Beispiele

## Projektdateien

| Datei | Zweck |
| --- | --- |
| `beispiel-projekt.json` | V-Cutting auf einer Platte 400 × 400 × 3 mm, T246 bei 90°, Linienabstand 2,5 mm |
| `beispiel-relief.json` | Relief auf einer Platte 200 × 150 × 6 mm, 3 mm Reliefhöhe über 2 mm Basis |

Beide lassen sich in der Oberfläche über *Projekt importieren* laden.

Im Beispielprojekt ist der Linienabstand bewusst auf 2,5 mm gesetzt: bei 90° und 1,2 mm Tiefe beträgt die Nutbreite 2,4 mm, die Nuten stoßen also aneinander, ohne sich stark zu überschneiden. Mit dem Standardabstand von 2 mm überlappen sie.

## Testmotiv erzeugen

Es liegen keine fremden Beispielbilder im Repository. Ein passendes Testmotiv entsteht auf Zuruf:

```bash
python examples/testmotiv_erzeugen.py testmotiv.png
```

Das Ergebnis ist ein transparentes PNG mit eindeutiger Orientierung:

- ein **dunkles** Quadrat oben links wird am tiefsten gefräst,
- ein **helles** Quadrat unten rechts bleibt ungeschnitten,
- ein Helligkeitsverlauf von links nach rechts zeigt die Tiefenabstufung.

Steht das Ergebnis auf dem Kopf oder ist es gespiegelt, fällt das sofort auf.

## Kompletter Durchlauf ohne Oberfläche

```bash
# Backend starten
cd backend && uvicorn app.main:app --port 8000 &

# Motiv erzeugen
python examples/testmotiv_erzeugen.py /tmp/testmotiv.png

# Job anlegen
JOB=$(curl -sS -X POST http://localhost:8000/api/jobs \
  -F "image=@/tmp/testmotiv.png" \
  -F "config=<examples/beispiel-projekt.json" \
  | python -c "import sys, json; print(json.load(sys.stdin)['job_id'])")

# Status abfragen
curl -sS "http://localhost:8000/api/jobs/$JOB" | python -m json.tool

# Prüfbericht ansehen
curl -sS "http://localhost:8000/api/jobs/$JOB/report" | python -m json.tool

# Dateien holen
curl -sS -o modell.step "http://localhost:8000/api/jobs/$JOB/download/step"
curl -sS -o bahn.png    "http://localhost:8000/api/jobs/$JOB/preview/toolpath"
```
