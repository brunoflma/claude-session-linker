#!/usr/bin/env bash
# Claude Session Linker - macOS launcher (double-clickable in Finder)
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/.app"
VENV_PY="$APP_DIR/venv/bin/python"
GUI="$APP_DIR/session_linker.py"

if [ ! -x "$VENV_PY" ]; then
  echo "Python environment not found."
  echo "Double-click '00 - Setup Claude Session Linker.command' first to create it."
  read -r -p "Press Enter to close" _
  exit 1
fi
if [ ! -f "$GUI" ]; then
  echo "GUI not found at: $GUI"
  read -r -p "Press Enter to close" _
  exit 1
fi
exec "$VENV_PY" "$GUI"
