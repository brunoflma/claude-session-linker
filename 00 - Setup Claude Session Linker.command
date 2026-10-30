#!/usr/bin/env bash
# Claude Session Linker - macOS setup launcher (double-clickable in Finder)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$ROOT_DIR/.app/setup.sh"
status=$?
if [ "$status" -eq 0 ]; then
  echo ""
  read -r -p "Setup concluído. Pressione Enter para abrir o aplicativo (Ctrl+C para pular)." _
  exec "$ROOT_DIR/Claude Session Linker.command"
fi
echo ""
read -r -p "O setup falhou (código $status). Pressione Enter para fechar." _
exit "$status"
