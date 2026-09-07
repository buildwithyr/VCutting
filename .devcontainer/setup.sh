#!/usr/bin/env bash
# Einmalige Einrichtung des Codespace.
#
# Laeuft als onCreateCommand, also genau einmal beim Anlegen. Der Download von
# OpenCascade ist mit rund 400 MB der langsamste Teil und dauert ein paar
# Minuten.

set -euo pipefail

cd "$(dirname "$0")/.."

VENV="$HOME/.venv-vcutting"

echo "==> Systembibliotheken fuer OpenCascade und OpenCV"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    libgl1 \
    libglu1-mesa \
    libxrender1 \
    libxext6 \
    libsm6 \
    libgomp1

echo "==> Python-Umgebung unter $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r backend/requirements-dev.txt

echo "==> Frontend-Abhaengigkeiten"
npm --prefix frontend ci --no-audit --no-fund

echo "==> Kurzer Selbsttest"
(cd backend && "$VENV/bin/python" -c "import OCP, cv2, fastapi; print('OpenCascade, OpenCV und FastAPI sind bereit.')")

echo "==> Einrichtung abgeschlossen."
