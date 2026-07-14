#!/usr/bin/env bash
# Claude Session Linker - macOS setup launcher (double-clickable in Finder)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$ROOT_DIR/.app/setup.sh"
status=$?
if [ "$status" -eq 0 ]; then
  echo ""
  read -r -p "Setup done. Press Enter to launch the app (Ctrl+C to skip)." _
  exec "$ROOT_DIR/Claude Session Linker.command"
fi
echo ""
read -r -p "Setup failed (exit $status). Press Enter to close." _
exit "$status"
