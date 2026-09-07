#!/usr/bin/env bash
# Startet Backend und Frontend im Hintergrund.
#
# Laeuft als postAttachCommand, also bei jedem Oeffnen des Codespace und auch
# nach dem Aufwachen aus dem Ruhezustand. Ist ein Dienst bereits erreichbar,
# wird er nicht doppelt gestartet.

set -euo pipefail

cd "$(dirname "$0")/.."

VENV="$HOME/.venv-vcutting"
BACKEND_LOG=/tmp/vcutting-backend.log
FRONTEND_LOG=/tmp/vcutting-frontend.log

if [ ! -x "$VENV/bin/uvicorn" ]; then
    echo "Die Einrichtung ist unvollstaendig. Bitte einmal ausfuehren:"
    echo "    bash .devcontainer/setup.sh"
    exit 1
fi

is_up() {
    curl --silent --fail --max-time 2 "http://127.0.0.1:$1" > /dev/null 2>&1
}

if is_up 8000/api/health; then
    echo "Backend laeuft bereits."
else
    echo "==> Backend startet auf Port 8000"
    # stdin ebenfalls umlenken: sonst haelt der Hintergrundprozess die
    # Konsole des Aufrufers offen und das Skript scheint zu haengen.
    (cd backend && nohup "$VENV/bin/uvicorn" app.main:app \
        --host 0.0.0.0 --port 8000 < /dev/null > "$BACKEND_LOG" 2>&1 &)
fi

if is_up 5173; then
    echo "Frontend laeuft bereits."
else
    echo "==> Frontend startet auf Port 5173"
    (cd frontend && nohup npm run dev -- --host 0.0.0.0 --port 5173 \
        < /dev/null > "$FRONTEND_LOG" 2>&1 &)
fi

# Auf das Backend warten, damit die Oberflaeche beim ersten Aufruf nicht in
# einen Verbindungsfehler laeuft.
echo -n "==> Warte auf das Backend "
for _ in $(seq 1 60); do
    if is_up 8000/api/health; then
        echo " bereit."
        break
    fi
    echo -n "."
    sleep 1
done

if ! is_up 8000/api/health; then
    echo
    echo "Das Backend hat nicht geantwortet. Protokoll:"
    tail -n 30 "$BACKEND_LOG" || true
    exit 1
fi

echo
echo "------------------------------------------------------------------"
echo "Alles laeuft."
echo

# In einem Codespace ist die oeffentliche Adresse aus zwei Variablen
# zusammensetzbar. Sie hier auszugeben erspart die Suche im Ports-Reiter,
# was besonders auf kleinen Bildschirmen hilft.
if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
    echo "  Oberflaeche oeffnen (antippen):"
    echo
    echo "    https://${CODESPACE_NAME}-5173.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
    echo
    echo "  Falls die Adresse nicht anklickbar ist: Reiter \"Ports\""
    echo "  beziehungsweise \"Anschluesse\", dann Port 5173."
else
    echo "  Oberflaeche oeffnen: http://localhost:5173"
fi

cat <<'HINWEIS'

  Protokolle:
      tail -f /tmp/vcutting-frontend.log
      tail -f /tmp/vcutting-backend.log

  Neu starten:
      bash .devcontainer/start.sh
------------------------------------------------------------------
HINWEIS
