#!/usr/bin/env bash
# ============================================================================
# Claude Session Linker - macOS environment setup (source of truth on macOS)
# Detects Python 3.11+ with tkinter (installs python-tk via Homebrew if needed),
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
MIN_MINOR=11

if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  echo "Não foi possível criar .app/logs. Mova o projeto para uma pasta gravável e tente de novo."
  if [ "$PAUSE_ON_EXIT" -eq 1 ]; then read -r -p "Pressione Enter para fechar" _; fi
  exit 6
fi

finish() {
  local code="$1"; local msg="$2"
  printf "STATUS=%s\n%s\n" "$code" "$msg" > "$RESULT" 2>/dev/null || \
    echo "Aviso: não foi possível gravar .app/logs/setup-result.txt"
  echo ""
  echo "$msg"
  if [ "$PAUSE_ON_EXIT" -eq 1 ]; then read -r -p "Pressione Enter para fechar" _; fi
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
echo "Claude Session Linker $VERSION - configurando ambiente (macOS)..."

# --- 1. Find a 3.11+ interpreter (prefer newest) ----------------------------
PYTHON=""
for cand in python3.15 python3.14 python3.13 python3.12 python3.11 python3; do
  path="$(command -v "$cand" 2>/dev/null)" || continue
  [ -n "$path" ] || continue
  if py_version_ok "$path"; then PYTHON="$path"; break; fi
done
if [ -z "$PYTHON" ]; then
  finish 2 "Python $MIN_MAJOR.$MIN_MINOR+ não encontrado. Instale-o (por exemplo, 'brew install python@3.13' ou pelo python.org) e tente de novo."
fi
echo "Python encontrado: $PYTHON"

# --- 2. Ensure tkinter; install python-tk via Homebrew if missing -----------
if ! py_has_tk "$PYTHON"; then
  echo "tkinter ausente em $PYTHON; tentando instalar pelo Homebrew..."
  if ! command -v brew >/dev/null 2>&1; then
    finish 2 "tkinter ausente e Homebrew não instalado. Instale o Homebrew (https://brew.sh) e rode 'brew install python-tk', ou instale o Python pelo python.org, e tente de novo."
  fi
  MM="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  brew install "python-tk@$MM" || brew install python-tk || true
  if ! py_has_tk "$PYTHON"; then
    finish 2 "Não foi possível habilitar o tkinter em $PYTHON. Rode 'brew install python-tk@$MM' manualmente ou instale o Python pelo python.org e tente de novo."
  fi
fi
echo "tkinter OK"

# --- 3a. An existing venv built on an older/removed Python is rebuilt -------
if [ -x "$VENV/bin/python" ] && ! py_version_ok "$VENV/bin/python"; then
  echo "O venv existente usa um Python anterior ao $MIN_MAJOR.$MIN_MINOR; recriando..."
  RECREATE_VENV=1
fi

# --- 3. (Re)create the venv -------------------------------------------------
if [ "$RECREATE_VENV" -eq 1 ] && [ -d "$VENV" ]; then
  echo "Recriando o venv isolado em .app/venv ..."
  rm -rf "$VENV" || finish 6 "Não foi possível remover .app/venv. Feche o aplicativo e tente de novo."
fi
if [ -d "$VENV" ] && [ ! -x "$VENV/bin/python" ]; then
  echo "O venv existente está incompleto; recriando..."
  rm -rf "$VENV" || finish 6 "Não foi possível recriar .app/venv. Feche processos Python abertos e tente de novo."
fi
if [ ! -d "$VENV" ]; then
  echo "Criando venv isolado em .app/venv ..."
  "$PYTHON" -m venv "$VENV" || finish 3 "Falha ao criar o venv em .app/venv."
fi
VENV_PY="$VENV/bin/python"
if [ ! -x "$VENV_PY" ]; then
  finish 3 "O venv foi criado, mas o interpretador em .app/venv não funciona."
fi

# --- 4. Install dependencies -------------------------------------------------
echo "Instalando dependencias..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
if ! "$VENV_PY" -m pip install -r "$REQ"; then
  finish 4 "Falha ao instalar as dependências de requirements.txt. Verifique a conexão e tente de novo."
fi

# --- 5. Validate GUI imports -------------------------------------------------
echo "Verificando import da GUI..."
if ! "$VENV_PY" -c "import tkinter, customtkinter, darkdetect, PIL" 2>/dev/null; then
  finish 5 "As dependências foram instaladas, mas a interface não pôde ser importada."
fi

finish 0 "Ambiente pronto. Abra com 'Claude Session Linker.command'."
