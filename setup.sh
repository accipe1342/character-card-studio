#!/usr/bin/env bash
cd "$(dirname "$0")"

echo ""
echo "  ============================================"
echo "   Character Card Studio — First Time Setup"
echo "  ============================================"
echo ""

# Colours
GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"; BOLD="\033[1m"

ok()   { echo -e "  ${GREEN}[OK]${RESET} $1"; }
warn() { echo -e "  ${YELLOW}[!]${RESET}  $1"; }
fail() { echo -e "  ${RED}[ERROR]${RESET} $1"; }
step() { echo -e "\n${BOLD}$1${RESET}"; }

# ── Check Python ──────────────────────────────────────────────────────────────
step "[1/5] Checking Python..."
PY_CMD=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        PY_VER=$($cmd --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo $PY_VER | cut -d. -f1)
        MINOR=$(echo $PY_VER | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PY_CMD=$cmd
            break
        fi
    fi
done

if [ -z "$PY_CMD" ]; then
    fail "Python 3.10+ not found."
    echo ""
    echo "  Please install Python 3.10 or later:"
    echo ""
    echo "  Mac:   https://www.python.org/downloads/"
    echo "         (or: brew install python)"
    echo ""
    echo "  Linux: sudo apt install python3 python3-venv"
    echo "         (or: sudo dnf install python3)"
    echo ""
    exit 1
fi
ok "Python $PY_VER found ($PY_CMD)"

# ── Check Node ────────────────────────────────────────────────────────────────
step "[2/5] Checking Node.js..."
if ! command -v node &>/dev/null; then
    fail "Node.js not found."
    echo ""
    echo "  Please install Node.js LTS:"
    echo ""
    echo "  Mac:   https://nodejs.org/"
    echo "         (or: brew install node)"
    echo ""
    echo "  Linux: https://nodejs.org/"
    echo "         (or: sudo apt install nodejs npm)"
    echo ""
    exit 1
fi
NODE_VER=$(node --version)
ok "Node.js $NODE_VER found"

# ── Create Python venv ────────────────────────────────────────────────────────
step "[3/5] Creating Python virtual environment..."
if [ -d .venv ]; then
    ok "Virtual environment already exists, skipping."
else
    $PY_CMD -m venv .venv
    if [ $? -ne 0 ]; then
        fail "Failed to create virtual environment."
        echo "  Try: $PY_CMD -m pip install virtualenv"
        exit 1
    fi
    ok "Virtual environment created."
fi
source .venv/bin/activate

# ── Install Python deps ───────────────────────────────────────────────────────
step "[4/5] Installing Python dependencies..."
pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    fail "Failed to install Python dependencies."
    exit 1
fi
# Save hash so start.sh skips reinstall next time
REQ_HASH=$(md5sum requirements.txt 2>/dev/null | cut -d' ' -f1 || md5 -q requirements.txt 2>/dev/null || echo "none")
echo "$REQ_HASH" > .venv/.req_hash
ok "Python dependencies installed."

# ── Install Node deps ─────────────────────────────────────────────────────────
step "[5/5] Installing frontend dependencies..."
cd frontend
npm install
if [ $? -ne 0 ]; then
    fail "Failed to install frontend dependencies."
    cd ..
    exit 1
fi
cd ..
ok "Frontend dependencies installed."

# ── Create data dir ───────────────────────────────────────────────────────────
mkdir -p data

# ── Make scripts executable ───────────────────────────────────────────────────
chmod +x start.sh

# ── Copy .env ─────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f _env.example ]; then
        cp _env.example .env
        echo ""
        warn ".env created from example — open it and add your API keys before launching."
    fi
else
    ok ".env already exists."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "  ============================================"
echo "   Setup complete!"
echo "  ============================================"
echo ""
echo "  Next steps:"
echo "    1. Open .env and add your API keys"
echo "    2. Run ./start.sh to launch the app"
echo ""
