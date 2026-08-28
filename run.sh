#!/usr/bin/env bash
# Avvia il Maggiordomo Locale. Crea l'ambiente virtuale la prima volta.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "→ Creo l'ambiente virtuale…"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi

if [ ! -f ".env" ]; then
  echo "⚠  Nessun file .env: copio da .env.example (ricordati di compilarlo)."
  cp .env.example .env
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
echo "→ Maggiordomo in ascolto su http://${HOST}:${PORT}"
exec ./.venv/bin/uvicorn agent.server:app --host "$HOST" --port "$PORT"
