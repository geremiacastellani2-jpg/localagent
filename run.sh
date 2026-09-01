#!/usr/bin/env bash
# Avvia il Maggiordomo Locale. Crea l'ambiente virtuale la prima volta e
# sincronizza sempre le dipendenze del nucleo (così un git pull che aggiunge
# dipendenze non lascia l'ambiente a metà).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "→ Creo l'ambiente virtuale…"
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
fi

echo "→ Sincronizzo le dipendenze del nucleo…"
./.venv/bin/pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "⚠  Nessun file .env: copio da .env.example (ricordati di compilarlo)."
  cp .env.example .env
fi

echo "→ Librerie di visione in locale (oggetti/volti, funzionano offline)…"
bash scripts/fetch_vendor.sh || echo "   (la pagina userà la CDN)"

echo "ℹ  Funzioni opzionali (calendario, memoria veloce, Matrix/WhatsApp):"
echo "   ./.venv/bin/pip install -r requirements-optional.txt"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
echo "→ Maggiordomo in ascolto su http://${HOST}:${PORT}"
exec ./.venv/bin/uvicorn agent.server:app --host "$HOST" --port "$PORT"
