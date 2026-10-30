#!/usr/bin/env bash
# Claude Session Linker - macOS launcher (double-clickable in Finder)
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/.app"
VENV_PY="$APP_DIR/venv/bin/python"
GUI="$APP_DIR/session_linker.py"

if [ ! -x "$VENV_PY" ]; then
  echo "Ambiente Python não encontrado."
  echo "Dê duplo clique em '00 - Setup Claude Session Linker.command' para criá-lo."
  read -r -p "Pressione Enter para fechar" _
  exit 1
fi
if [ ! -f "$GUI" ]; then
  echo "Interface não encontrada em: $GUI"
  read -r -p "Pressione Enter para fechar" _
  exit 1
fi
exec "$VENV_PY" "$GUI"
