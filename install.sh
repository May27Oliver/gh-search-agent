#!/usr/bin/env bash
#
# One-shot installer for gh-search-agent.
#
# What it does:
#   1. Verify Python >= 3.10
#   2. Create a fresh .venv (use --clean to rebuild)
#   3. Upgrade pip
#   4. Install project with dev extras (pip install -e '.[dev]')
#   5. Copy .env.example -> .env if .env does not exist
#
# Usage:
#   ./install.sh               # install (keep existing .venv if present)
#   ./install.sh --clean       # remove existing .venv and rebuild
#   ./install.sh --no-dev      # install without dev extras
#   ./install.sh -h | --help   # show help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
CLEAN=0
INSTALL_EXTRAS="[dev]"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MIN_PY_MAJOR=3
MIN_PY_MINOR=10

# --- colored logging ------------------------------------------------------
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_INFO=$'\033[1;34m'
  C_OK=$'\033[1;32m'
  C_WARN=$'\033[1;33m'
  C_ERR=$'\033[1;31m'
else
  C_RESET=""; C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""
fi

info()  { printf "%s[info]%s %s\n"  "$C_INFO" "$C_RESET" "$*"; }
ok()    { printf "%s[ ok ]%s %s\n"  "$C_OK"   "$C_RESET" "$*"; }
warn()  { printf "%s[warn]%s %s\n"  "$C_WARN" "$C_RESET" "$*"; }
fail()  { printf "%s[fail]%s %s\n"  "$C_ERR"  "$C_RESET" "$*" >&2; exit 1; }

usage() {
  sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# --- parse args -----------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)   CLEAN=1; shift ;;
    --no-dev)  INSTALL_EXTRAS=""; shift ;;
    -h|--help) usage ;;
    *) fail "unknown argument: $1 (use --help)" ;;
  esac
done

# --- check python ---------------------------------------------------------
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  fail "$PYTHON_BIN not found. Install Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR} or set PYTHON_BIN=/path/to/python3"
fi

PY_VERSION=$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_OK=$("$PYTHON_BIN" - <<EOF
import sys
need = (${MIN_PY_MAJOR}, ${MIN_PY_MINOR})
print("yes" if sys.version_info[:2] >= need else "no")
EOF
)
if [[ "$PY_OK" != "yes" ]]; then
  fail "Python $PY_VERSION detected, need >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}"
fi
ok "using $PYTHON_BIN (Python $PY_VERSION)"

# --- venv -----------------------------------------------------------------
if [[ $CLEAN -eq 1 && -d "$VENV_DIR" ]]; then
  info "removing existing $VENV_DIR (--clean)"
  rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
  info "creating virtual environment in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
else
  info "reusing existing $VENV_DIR (pass --clean to rebuild)"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
ok "activated $VENV_DIR"

# --- install --------------------------------------------------------------
info "upgrading pip"
python -m pip install --upgrade pip >/dev/null

TARGET=".${INSTALL_EXTRAS}"  # e.g. .[dev] or .
info "installing project (pip install -e '$TARGET')"
python -m pip install -e "$TARGET"
ok "dependencies installed"

# --- .env bootstrap -------------------------------------------------------
if [[ -f ".env" ]]; then
  info ".env already exists, leaving it untouched"
elif [[ -f ".env.example" ]]; then
  cp .env.example .env
  ok "created .env from .env.example (remember to fill OPENAI_API_KEY and GITHUB_TOKEN)"
else
  warn ".env.example not found — skipping .env bootstrap"
fi

# --- smoke check ----------------------------------------------------------
if command -v gh-search >/dev/null 2>&1; then
  ok "gh-search CLI is on PATH"
else
  warn "gh-search not on PATH inside venv (this is unusual — check install output above)"
fi

cat <<EOF

${C_OK}Install complete.${C_RESET}

Next steps:
  1. source ${VENV_DIR}/bin/activate
  2. Edit .env and set OPENAI_API_KEY / GITHUB_TOKEN
  3. gh-search check
  4. gh-search query "find the top 5 Python repositories about AI sorted by stars descending"

EOF
