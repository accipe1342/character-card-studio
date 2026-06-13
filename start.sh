#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo ""
echo "  Character Card Studio"
echo "  ====================="
echo ""

# ── Python venv ───────────────────────────────────────────────────────────────
if [ ! -d .venv ]; then
    echo "[.] Creating Python virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# ── Python deps (only reinstall if requirements.txt changed) ──────────────────
REQ_HASH_FILE=".venv/.req_hash"
REQ_HASH=$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1 || md5 -q requirements.txt 2>/dev/null || echo "none")
if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat $REQ_HASH_FILE)" != "$REQ_HASH" ]; then
    echo "[.] Installing Python dependencies..."
    pip install -r requirements.txt -q
    echo "$REQ_HASH" > "$REQ_HASH_FILE"
else
    echo "[OK] Python dependencies up to date."
fi

# ── Node deps ─────────────────────────────────────────────────────────────────
if [ ! -d frontend/node_modules ]; then
    echo "[.] Installing frontend dependencies..."
    cd frontend && npm install --silent && cd ..
fi

# ── Copy .env if missing ──────────────────────────────────────────────────────
if [ ! -f .env ] && [ -f _env.example ]; then
    cp _env.example .env
    echo "[.] Created .env — add your API keys!"
fi

# ── Ensure data/ exists ───────────────────────────────────────────────────────
mkdir -p data

# ── Start Vite in background, opens browser automatically ────────────────────
echo "[.] Starting Vite dev server in background..."
(cd frontend && npm run dev -- --open) &
VITE_PID=$!
trap "kill $VITE_PID 2>/dev/null; exit 0" INT TERM EXIT
sleep 3

# ── Start Flask in foreground (logs visible here) ────────────────────────────
echo "[OK] Flask starting - logs will appear below."
echo "     (Press Ctrl+C to stop everything)"
echo ""
python3 backend/app.py
