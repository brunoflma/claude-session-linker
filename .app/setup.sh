#!/usr/bin/env bash
# ============================================================================
# Claude Session Linker - macOS environment setup (source of truth on macOS)
# Detects Python 3.10+ with tkinter (installs python-tk via Homebrew if needed),
# (re)creates the isolated venv in .app/venv, installs dependencies, and
# validates the GUI imports. Writes a readable result to .app/logs/setup-result.txt.
# Exit codes: 0 ready | 2 Python/tkinter missing | 3 venv failed |
#             4 deps failed | 5 GUI import failed | 6 permission/file-in-use
# ============================================================================
set -u

PAUSE_ON_EXIT=0
RECREATE_VENV=0
for arg in "$@"; do
  case "$arg" in
    --pause-on-exit) PAUSE_ON_EXIT=1 ;;
    --recreate-venv) RECREATE_VENV=1 ;;
  esac
done

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/venv"
REQ="$APP_DIR/requirements.txt"
LOG_DIR="$APP_DIR/logs"
RESULT="$LOG_DIR/setup-result.txt"
MIN_MAJOR=3
MIN_MINOR=10

if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  echo "Could not create .app/logs. Move the project to a writable folder and retry."
  exit 6
fi

finish() {
  local code="$1"; local msg="$2"
  printf "STATUS=%s\n%s\n" "$code" "$msg" > "$RESULT" 2>/dev/null || \
    echo "Warning: could not write .app/logs/setup-result.txt"
  echo ""
  echo "$msg"
  if [ "$PAUSE_ON_EXIT" -eq 1 ]; then read -r -p "Press Enter to close" _; fi
  exit "$code"
}

# --- Does this interpreter meet the version floor? --------------------------
py_version_ok() {
  "$1" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= ($MIN_MAJOR,$MIN_MINOR) else 1)" 2>/dev/null
}
# --- Does this interpreter import tkinter? ----------------------------------
py_has_tk() {
  "$1" -c "import tkinter" 2>/dev/null
}

VERSION="$(cat "$APP_DIR/VERSION" 2>/dev/null || echo 0.0.0)"
echo "Claude Session Linker $VERSION - configuring environment (macOS)..."

# --- 1. Find a 3.10+ interpreter (prefer newest) ----------------------------
PYTHON=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  path="$(command -v "$cand" 2>/dev/null)" || continue
  [ -n "$path" ] || continue
  if py_version_ok "$path"; then PYTHON="$path"; break; fi
done
if [ -z "$PYTHON" ]; then
  finish 2 "Python $MIN_MAJOR.$MIN_MINOR+ not found. Install it (e.g. 'brew install python@3.13') and retry."
fi
echo "Python found: $PYTHON"

# --- 2. Ensure tkinter; install python-tk via Homebrew if missing -----------
if ! py_has_tk "$PYTHON"; then
  echo "tkinter missing for $PYTHON; attempting to install via Homebrew..."
  if ! command -v brew >/dev/null 2>&1; then
    finish 2 "tkinter is missing and Homebrew is not installed. Install Homebrew (https://brew.sh) then run 'brew install python-tk', or install Python from python.org, and retry."
  fi
  MM="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  brew install "python-tk@$MM" || brew install python-tk || true
  if ! py_has_tk "$PYTHON"; then
    finish 2 "Could not enable tkinter for $PYTHON. Try 'brew install python-tk@$MM' manually, or install Python from python.org, then retry."
  fi
fi
echo "tkinter OK"

# --- 3. (Re)create the venv -------------------------------------------------
if [ "$RECREATE_VENV" -eq 1 ] && [ -d "$VENV" ]; then
  echo "Recreating isolated venv in .app/venv ..."
  rm -rf "$VENV" || finish 6 "Could not remove .app/venv. Close the app and retry."
fi
if [ -d "$VENV" ] && [ ! -x "$VENV/bin/python" ]; then
  echo "Existing venv is incomplete; recreating..."
  rm -rf "$VENV" || finish 6 "Could not recreate .app/venv. Close open Python processes and retry."
fi
if [ ! -d "$VENV" ]; then
  "$PYTHON" -m venv "$VENV" || finish 3 "Failed to create the venv in .app/venv."
fi
VENV_PY="$VENV/bin/python"

# --- 4. Install dependencies -------------------------------------------------
"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
if ! "$VENV_PY" -m pip install -r "$REQ"; then
  finish 4 "Failed to install dependencies from requirements.txt."
fi

# --- 5. Validate GUI imports -------------------------------------------------
if ! "$VENV_PY" -c "import tkinter, customtkinter, darkdetect, PIL" 2>/dev/null; then
  finish 5 "GUI dependencies could not be imported after install."
fi

finish 0 "Setup complete. Launch with 'Claude Session Linker.command'."
