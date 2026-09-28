#!/usr/bin/env bash
#
# run.sh — Bulletproof setup + launch for Vocabook.
#
#   1. Creates/activates a local Python virtual environment (.venv)
#   2. Installs PyQt6 + pdfplumber (only if missing)
#   3. Ingests assets/vocabulary_source.pdf into flashcards.db
#      (skipped automatically on repeat runs once cards already exist,
#       unless --reingest is passed)
#   4. Launches the application
#
# Usage:
#   ./run.sh                 normal launch
#   ./run.sh --reingest      force re-parsing the PDF even if the DB has data
#   ./run.sh --no-launch     set up + ingest only, don't open the app
#
set -euo pipefail

# ------------------------------------------------------------------ #
# Resolve paths relative to this script, so it works from any CWD.
# ------------------------------------------------------------------ #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
SRC_DIR="$SCRIPT_DIR/src"
DB_PATH="$SCRIPT_DIR/flashcards.db"
PDF_PATH="$SCRIPT_DIR/assets/vocabulary_source.pdf"

FORCE_REINGEST=0
LAUNCH=1
for arg in "$@"; do
    case "$arg" in
        --reingest) FORCE_REINGEST=1 ;;
        --no-launch) LAUNCH=0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

echo "=============================================="
echo " Vocabook — setup"
echo "=============================================="

# ------------------------------------------------------------------ #
# 1. Python interpreter check
# ------------------------------------------------------------------ #
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python 3 is required but was not found on PATH." >&2
    echo "Install it from https://www.python.org/downloads/ (macOS: 'brew install python3')." >&2
    exit 1
fi
echo "Using interpreter: $($PYTHON_BIN --version)"

# ------------------------------------------------------------------ #
# 2. Virtual environment
# ------------------------------------------------------------------ #
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists — reusing it."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Upgrading pip ..."
pip install --quiet --upgrade pip

echo "Installing dependencies (PyQt6, pdfplumber) ..."
pip install --quiet "PyQt6>=6.6" "pdfplumber>=0.10"

# ------------------------------------------------------------------ #
# 3. Ingest the vocabulary book into SQLite (idempotent)
# ------------------------------------------------------------------ #
NEEDS_INGEST=1
if [ -f "$DB_PATH" ] && [ "$FORCE_REINGEST" -eq 0 ]; then
    EXISTING_CARDS=$("$PYTHON_BIN" - "$DB_PATH" <<'PYEOF'
import sqlite3, sys
path = sys.argv[1]
try:
    conn = sqlite3.connect(path)
    cur = conn.execute("SELECT COUNT(*) FROM cards")
    print(cur.fetchone()[0])
except Exception:
    print(0)
PYEOF
)
    if [ "${EXISTING_CARDS:-0}" -gt 0 ]; then
        echo "Database already has $EXISTING_CARDS cards — skipping ingestion."
        echo "(Run './run.sh --reingest' to force a fresh parse.)"
        NEEDS_INGEST=0
    fi
fi

if [ "$NEEDS_INGEST" -eq 1 ]; then
    if [ ! -f "$PDF_PATH" ]; then
        echo "WARNING: '$PDF_PATH' not found — skipping ingestion." >&2
        echo "Place your vocabulary PDF at that path and re-run './run.sh --reingest'." >&2
    else
        echo "Ingesting '$PDF_PATH' into '$DB_PATH' ..."
        python "$SRC_DIR/parser.py" "$PDF_PATH" "$DB_PATH"
    fi
fi

# ------------------------------------------------------------------ #
# 4. Launch
# ------------------------------------------------------------------ #
echo "=============================================="
if [ "$LAUNCH" -eq 1 ]; then
    echo " Launching Vocabook..."
    echo "=============================================="
    python "$SRC_DIR/app.py" "$DB_PATH"
else
    echo " Setup complete (launch skipped: --no-launch)."
    echo "=============================================="
fi
