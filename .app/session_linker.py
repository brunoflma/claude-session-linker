"""
Claude Session Linker (customtkinter)
--------------------------------------
Links Claude Desktop sessions across your different Claude accounts on this
machine -- for both the "Code" tab and Cowork (Agent Mode).

Background, Code tab: Claude Desktop keeps a per-account index under each
Claude data root, usually:
  %APPDATA%\\Claude\\claude-code-sessions\\<accountUUID>\\<workspaceUUID>\\local_*.json
Each index file only holds metadata (title, cwd, model, ...) plus a
"cliSessionId" pointer to the real transcript, which lives account-agnostic
at:
  %USERPROFILE%\\.claude\\projects\\<cwd-hash>\\<cliSessionId>.jsonl

Background, Cowork: Desktop keeps an equivalent per-account index under the
same Claude data roots, usually:
  %APPDATA%\\Claude\\local-agent-mode-sessions\\<accountUUID>\\<workspaceUUID>\\local_*.json
but unlike Code, there is no account-agnostic transcript elsewhere -- the
conversation (audit.jsonl), uploads, and command outputs live inside a
same-named local_*\\ folder right next to the index file. Linking a Cowork
session therefore copies that whole folder too, not just the index.

Because each index is partitioned per account but Code's transcript is not,
a session created while logged into Account A is invisible in Desktop's
sidebar while you are logged into Account B -- even though the underlying
conversation still exists on disk. Cowork sessions are fully self-contained
per account, so the same visibility problem applies even more literally.

This tool:
  1. Shows every indexed session (Code or Cowork, pick with the toggle)
     across every account found on this machine.
  2. Copies ("links") a session into another account's folder, so it shows
     up in that account's sidebar too. Code links clone the transcript to a
     new cliSessionId; Cowork links copy the same-named data folder.

Safety:
  - Link actions never delete or move anything -- only copy.
  - Remove actions delete only the selected account's local session files,
    always after creating a backup.
  - Every Code link action zips a timestamped backup of the whole
    claude-code-sessions folder into .app\\backups\\ before writing.
  - Every Cowork link action zips a timestamped backup of just the target
    workspace folder before writing (Cowork data can run into hundreds of
    MB, so backing up the whole tree on every link would be too slow).
  - This storage format is undocumented/internal to Claude Desktop and may
    change in a future version. Fully quit Desktop (system tray, not just
    the window) before linking, and restart it afterwards to see changes.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

# Must run before any Tk window is created: without an explicit App User
# Model ID, Windows groups this process under pythonw.exe's own identity and
# shows Python's icon in the taskbar instead of ours, even though the window
# itself has the right icon set via iconbitmap().
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Claude.SessionLinker")
    except Exception:
        pass

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
ICON_PATH = APP_DIR / "icon.ico"
ICON_PNG = APP_DIR / "icon.png"
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ERR_LOG = LOG_DIR / "session-linker-error.log"
BACKUPS_DIR = APP_DIR / "backups"
BACKUPS_DIR.mkdir(exist_ok=True)
LABELS_FILE = APP_DIR / "account_labels.json"
LINKS_FILE = APP_DIR / "session_links.json"
LINKED_FROM_ACCOUNT_KEY = "_sessionLinkerLinkedFromAccount"
LINKED_AT_KEY = "_sessionLinkerLinkedAt"
ORIGIN_ACCOUNT_KEY = "_sessionLinkerOriginAccount"
LINKED_SOURCE_CLI_SESSION_ID_KEY = "_sessionLinkerSourceCliSessionId"

_PY = Path(sys.executable).parent
_TCL = _PY / "tcl"
if _TCL.exists():
    os.environ.setdefault("TCL_LIBRARY", str(_TCL / "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", str(_TCL / "tk8.6"))


def _log(message):
    try:
        with ERR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("green")
except Exception as exc:
    _log(f"customtkinter import failed: {exc}\n{traceback.format_exc()}")
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Dependências do Claude Session Linker ausentes.\n\n"
            f"Erro: {exc}\n\n"
            "Execute novamente:\n"
            "    00 - Setup Claude Session Linker.vbs",
            "Claude Session Linker - dependências ausentes",
            0x10,  # MB_ICONERROR
        )
    except Exception:
        pass
    raise

# ---------------------------------------------------------------------------
# Palette -- shared with Claude Profiles / Cowork VM Manager for a
# consistent look across all three tools.
# ---------------------------------------------------------------------------
BG = "#0B0D10"
SURF = "#15181D"
SURF2 = "#1B2027"
SURF3 = "#242A33"
TXT = "#F4EFE3"
TXT2 = "#C8BDAE"
TXT3 = "#8F9BA8"
BRD = "#343A42"
BLUE = "#4FB7C5"
BLUE_H = "#3B9CAA"
GREEN = "#78B87A"
GREEN_H = "#5F9F64"
RED = "#E26D5A"
RED_H = "#BF5747"
YELLOW = "#E2B457"
ORANGE = "#D98A4A"
PAPER = "#F4EFE7"
PAPER2 = "#FCF9F3"
PAPER3 = "#EFE6D8"
INK = "#202226"
INK2 = "#5F5C55"
INK3 = "#8B8174"
LINE = "#DED4C5"
AMBER = "#C47A1F"
AMBER_H = "#A76519"
WARN_BG = "#40220D"
TRACE_BG = "#EAF4EC"
TRACE_BORDER = "#7BAA80"
TRACE_TEXT = "#24422F"
BADGE_GREEN_BG = "#2F7D46"
BADGE_BLUE_BG = "#2F6582"
BADGE_TEXT = "#FFFFFF"
SP = 16
WIN_TITLE = "Claude Session Linker"
def _load_app_version() -> str:
    # Single source of truth: .app/VERSION. Every version label (this footer,
    # the setup window badge, the setup.ps1 message) reads from that one file
    # so a release only ever changes one number.
    try:
        return (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


APP_VERSION = _load_app_version()
DEV_CREDIT = "Desenvolvido por Bruno Ferreira"

# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------
APPDATA = Path(os.environ["APPDATA"])
LOCALAPPDATA = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else None
CLAUDE_DIR_ENV = "CLAUDE_SESSION_LINKER_CLAUDE_DIR"


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    unique = []
    for path in paths:
        key = str(path).rstrip("\\/").casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def is_claude_data_dir(path: Path) -> bool:
    return path.is_dir() and any(
        (path / child).exists()
        for child in ("config.json", "claude-code-sessions", "local-agent-mode-sessions")
    )


def claude_dir_activity_time(path: Path) -> float:
    probes = [
        path / "config.json",
        path / "claude-code-sessions",
        path / "local-agent-mode-sessions",
        path,
    ]
    mtimes = []
    for probe in probes:
        try:
            if probe.exists():
                mtimes.append(probe.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def discover_claude_dirs(appdata: Path, localappdata: Path | None = None) -> list[Path]:
    candidates = [appdata / "Claude"]
    if localappdata is not None:
        candidates.extend([localappdata / "Claude-3p", localappdata / "Claude"])
        try:
            candidates.extend(sorted(localappdata.glob("Claude*")))
        except OSError:
            pass
        try:
            candidates.extend(
                package / "LocalCache" / "Roaming" / "Claude"
                for package in sorted((localappdata / "Packages").glob("Claude_*"))
            )
        except OSError:
            pass
    valid = [path for path in _unique_paths(candidates) if is_claude_data_dir(path)]
    valid.sort(key=claude_dir_activity_time, reverse=True)
    return valid


def resolve_claude_dir(
    appdata: Path,
    localappdata: Path | None = None,
    explicit_dir: str | os.PathLike | None = None,
) -> Path:
    return resolve_claude_dirs(appdata, localappdata, explicit_dir)[0]


def resolve_claude_dirs(
    appdata: Path,
    localappdata: Path | None = None,
    explicit_dir: str | os.PathLike | None = None,
) -> list[Path]:
    if explicit_dir:
        return [Path(explicit_dir).expanduser()]
    candidates = discover_claude_dirs(appdata, localappdata)
    return candidates if candidates else [appdata / "Claude"]


CLAUDE_DIRS = resolve_claude_dirs(APPDATA, LOCALAPPDATA, os.environ.get(CLAUDE_DIR_ENV))
CLAUDE_DIR = CLAUDE_DIRS[0]
SESSIONS_DIR = CLAUDE_DIR / "claude-code-sessions"
COWORK_SESSIONS_DIR = CLAUDE_DIR / "local-agent-mode-sessions"
CONFIG_JSON = CLAUDE_DIR / "config.json"


def load_labels() -> dict:
    if LABELS_FILE.exists():
        try:
            return json.loads(LABELS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_labels(labels: dict) -> None:
    LABELS_FILE.write_text(json.dumps(labels, indent=2, ensure_ascii=False), encoding="utf-8")


def _link_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except Exception:
        return str(path)


def load_link_registry() -> dict:
    if LINKS_FILE.exists():
        try:
            return json.loads(LINKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_link_registry(registry: dict) -> None:
    LINKS_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def record_link_metadata(
    dest_path: Path,
    source_account_id: str,
    origin_account_id: str | None = None,
    source_cli_session_id: str | None = None,
) -> None:
    registry = load_link_registry()
    metadata = {
        LINKED_FROM_ACCOUNT_KEY: source_account_id,
        ORIGIN_ACCOUNT_KEY: origin_account_id or source_account_id,
        LINKED_AT_KEY: datetime.now().isoformat(timespec="seconds"),
    }
    if source_cli_session_id:
        metadata[LINKED_SOURCE_CLI_SESSION_ID_KEY] = source_cli_session_id
    registry[_link_key(dest_path)] = metadata
    save_link_registry(registry)


def get_link_metadata(path: Path) -> dict:
    return load_link_registry().get(_link_key(path), {})


def source_origin_account(session: dict) -> str:
    return session.get("originAccount") or session.get("linkedFromAccount") or session.get("accountId", "")


def get_active_account_uuid():
    for claude_dir in CLAUDE_DIRS:
        config_json = claude_dir / "config.json"
        if not config_json.exists():
            continue
        try:
            data = json.loads(config_json.read_text(encoding="utf-8"))
            account_uuid = data.get("lastKnownAccountUuid")
            if account_uuid:
                return account_uuid
        except Exception:
            continue
    return None


_NO_WINDOW_FLAGS = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW


def _get_system_executable(name: str) -> str:
    """Securely resolves the path to a system executable without relying on
    PATH or SystemRoot environment variables, preventing binary planting."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            length = ctypes.windll.kernel32.GetSystemDirectoryW(buf, 260)
            if length > 0:
                return os.path.join(buf[:length], name)
        except Exception:
            pass
    return os.path.join(r"C:\Windows\System32", name)


def is_desktop_running() -> bool:
    try:
        tasklist_cmd = _get_system_executable("tasklist.exe")
        out = subprocess.run(
            [tasklist_cmd, "/FI", "IMAGENAME eq Claude.exe"],
            capture_output=True, timeout=5,
            creationflags=_NO_WINDOW_FLAGS,  # avoid a console flash from pythonw.exe
        )
        # Process names are plain ASCII regardless of console codepage, so a
        # raw byte search sidesteps pt-BR tasklist header decoding issues.
        return b"claude.exe" in out.stdout.lower()
    except Exception:
        return False


def scan_sessions() -> dict:
    """{accountUUID: [ {path, sessionId, cliSessionId, cwd, title,
    lastActivityAt, isArchived, workspaceUUID}, ... ] } sorted newest first."""
    result: dict[str, list[dict]] = {}
    for claude_dir in CLAUDE_DIRS:
        sessions_dir = claude_dir / "claude-code-sessions"
        if not sessions_dir.exists():
            continue
        for account_dir in sessions_dir.iterdir():
            if not account_dir.is_dir():
                continue
            account_id = account_dir.name
            account_sessions = []
            for workspace_dir in account_dir.iterdir():
                if not workspace_dir.is_dir():
                    continue
                for f in workspace_dir.glob("local_*.json"):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    link_metadata = get_link_metadata(f)
                    account_sessions.append({
                        "path": f,
                        "data_dir": None,
                        "accountId": account_id,
                        "claudeDir": claude_dir,
                        "sessionsDir": sessions_dir,
                        "sessionId": data.get("sessionId", f.stem),
                        "cliSessionId": data.get("cliSessionId", ""),
                        "cwd": data.get("cwd", ""),
                        "title": data.get("title") or "(sem título)",
                        "lastActivityAt": data.get("lastActivityAt", 0),
                        "isArchived": data.get("isArchived", False),
                        "workspaceUUID": workspace_dir.name,
                        "linkedFromAccount": link_metadata.get(LINKED_FROM_ACCOUNT_KEY) or data.get(LINKED_FROM_ACCOUNT_KEY),
                        "originAccount": link_metadata.get(ORIGIN_ACCOUNT_KEY) or data.get(ORIGIN_ACCOUNT_KEY),
                        "linkedAt": link_metadata.get(LINKED_AT_KEY) or data.get(LINKED_AT_KEY),
                        "linkedSourceCliSessionId": link_metadata.get(LINKED_SOURCE_CLI_SESSION_ID_KEY) or data.get(LINKED_SOURCE_CLI_SESSION_ID_KEY),
                    })
            if account_sessions:
                result.setdefault(account_id, []).extend(account_sessions)
    for sessions in result.values():
        sessions.sort(key=lambda s: s["lastActivityAt"], reverse=True)
    return result


def scan_cowork_sessions() -> dict:
    """Same shape as scan_sessions(), but for Cowork (Agent Mode).

    Each index file (local_<agentUUID>.json) sits next to a same-stem
    folder (local_<agentUUID>\\) holding audit.jsonl, uploads, and command
    outputs -- Cowork keeps no account-agnostic transcript elsewhere, so
    that folder is the actual conversation data and travels with the index
    whenever a session is linked ("data_dir" below).
    """
    result: dict[str, list[dict]] = {}
    for claude_dir in CLAUDE_DIRS:
        cowork_sessions_dir = claude_dir / "local-agent-mode-sessions"
        if not cowork_sessions_dir.exists():
            continue
        for account_dir in cowork_sessions_dir.iterdir():
            if not account_dir.is_dir():
                continue
            account_id = account_dir.name
            account_sessions = []
            for workspace_dir in account_dir.iterdir():
                if not workspace_dir.is_dir():
                    continue
                for f in workspace_dir.glob("local_*.json"):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    link_metadata = get_link_metadata(f)
                    data_dir = workspace_dir / f.stem
                    account_sessions.append({
                        "path": f,
                        "data_dir": data_dir if data_dir.is_dir() else None,
                        "accountId": account_id,
                        "claudeDir": claude_dir,
                        "sessionsDir": cowork_sessions_dir,
                        "sessionId": data.get("sessionId", f.stem),
                        "cliSessionId": data.get("cliSessionId", ""),
                        "cwd": data.get("cwd", ""),
                        "title": data.get("title") or "(sem título)",
                        "lastActivityAt": data.get("lastActivityAt", 0),
                        "isArchived": data.get("isArchived", False),
                        "workspaceUUID": workspace_dir.name,
                        "linkedFromAccount": link_metadata.get(LINKED_FROM_ACCOUNT_KEY) or data.get(LINKED_FROM_ACCOUNT_KEY),
                        "originAccount": link_metadata.get(ORIGIN_ACCOUNT_KEY) or data.get(ORIGIN_ACCOUNT_KEY),
                        "linkedAt": link_metadata.get(LINKED_AT_KEY) or data.get(LINKED_AT_KEY),
                        "linkedSourceCliSessionId": link_metadata.get(LINKED_SOURCE_CLI_SESSION_ID_KEY) or data.get(LINKED_SOURCE_CLI_SESSION_ID_KEY),
                    })
            if account_sessions:
                result.setdefault(account_id, []).extend(account_sessions)
    for sessions in result.values():
        sessions.sort(key=lambda s: s["lastActivityAt"], reverse=True)
    return result


def backup_dir_tree(dir_path: Path, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = BACKUPS_DIR / f"{label}-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in dir_path.rglob("*"):
            if f.is_file() and not f.is_symlink():
                zf.write(f, f.relative_to(dir_path.parent))
    return zip_path


def backup_sessions_dir(sessions_dir: Path = SESSIONS_DIR) -> Path:
    label = "claude-code-sessions"
    if sessions_dir != SESSIONS_DIR:
        profile = sessions_dir.parent.name.replace(" ", "-")
        label = f"{profile}-claude-code-sessions"
    return backup_dir_tree(sessions_dir, label)


def find_target_workspace_dir(base_dir: Path, account_id: str):
    account_dir = base_dir / account_id
    if not account_dir.exists():
        return None
    workspace_dirs = [d for d in account_dir.iterdir() if d.is_dir()]
    if not workspace_dirs:
        return None
    workspace_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return workspace_dirs[0]


def find_target_workspace_dir_in_roots(folder_name: str, account_id: str):
    for claude_dir in CLAUDE_DIRS:
        target_ws = find_target_workspace_dir(claude_dir / folder_name, account_id)
        if target_ws is not None:
            return target_ws
    return None


def ensure_index_linked(src_path: Path, dest_path: Path, source_account_id: str, origin_account_id: str) -> bool:
    copied = not dest_path.exists()
    if copied:
        shutil.copy2(src_path, dest_path)
    record_link_metadata(dest_path, source_account_id, origin_account_id)
    return copied


def _new_cli_session_id(transcript_dir: Path) -> str:
    while True:
        cli_session_id = str(uuid.uuid4())
        if not (transcript_dir / f"{cli_session_id}.jsonl").exists():
            return cli_session_id


def _read_index_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_code_index_clone(
    src_path: Path,
    dest_path: Path,
    source_account_id: str,
    origin_account_id: str,
) -> bool:
    source_data = _read_index_json(src_path)
    data = source_data
    source_cli_session_id = source_data.get("cliSessionId") or ""
    dest_cli_session_id = ""
    if dest_path.exists():
        try:
            dest_data = _read_index_json(dest_path)
            dest_cli_session_id = dest_data.get("cliSessionId") or ""
            data = dest_data
        except Exception:
            dest_cli_session_id = ""
        if dest_cli_session_id and dest_cli_session_id != source_cli_session_id:
            record_link_metadata(dest_path, source_account_id, origin_account_id, source_cli_session_id)
            return False

    if source_cli_session_id:
        transcript_path = find_transcript_path(source_cli_session_id)
        if transcript_path and transcript_path.exists():
            cloned_cli_session_id = _new_cli_session_id(transcript_path.parent)
            shutil.copy2(transcript_path, transcript_path.with_name(f"{cloned_cli_session_id}.jsonl"))
            data["cliSessionId"] = cloned_cli_session_id

    copied = not dest_path.exists()
    dest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    record_link_metadata(dest_path, source_account_id, origin_account_id, source_cli_session_id)
    return copied


def copy_index_with_link_metadata(src_path: Path, dest_path: Path, source_account_id: str, origin_account_id: str | None = None) -> None:
    shutil.copy2(src_path, dest_path)
    record_link_metadata(dest_path, source_account_id, origin_account_id or source_account_id)


def claude_project_dir_name(path: Path | str) -> str:
    # Claude Desktop encodes a project folder by replacing EACH non-alphanumeric
    # character with a dash -- it does not collapse runs, so `C:\` -> `C--`.
    # Using `+` here (collapsing) produced `C-...`, which never matched the real
    # folder, so the Cowork link rename was silently skipped and Claude reported
    # "No conversation found with session ID: ...".
    return re.sub(r"[^A-Za-z0-9]", "-", str(path)).strip("-")


def _replace_text_in_tree(root: Path, replacements: dict[str, str]) -> None:
    replacements = {old: new for old, new in replacements.items() if old and old != new}
    if not root.is_dir() or not replacements:
        return
    text_suffixes = {".json", ".jsonl", ".md", ".txt", ".yml", ".yaml", ".toml", ".lock", ""}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in text_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def normalize_cowork_session_copy(
    src_path: Path,
    dest_path: Path,
    src_data_dir: Path | None,
    dest_data_dir: Path | None,
    source_account_id: str,
    origin_account_id: str,
) -> None:
    data = _read_index_json(src_path)
    if dest_data_dir:
        data["cwd"] = str(dest_data_dir / "outputs")
    for key in ("error", "errorAt", "errorCategory", "errorVersion"):
        data.pop(key, None)
    dest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    record_link_metadata(dest_path, source_account_id, origin_account_id)

    if not src_data_dir or not dest_data_dir or not dest_data_dir.is_dir():
        return

    src_outputs = src_data_dir / "outputs"
    dest_outputs = dest_data_dir / "outputs"
    src_project_name = claude_project_dir_name(src_outputs)
    dest_project_name = claude_project_dir_name(dest_outputs)
    projects_dir = dest_data_dir / ".claude" / "projects"
    old_project = projects_dir / src_project_name
    new_project = projects_dir / dest_project_name
    if old_project.exists() and old_project != new_project:
        if new_project.exists():
            shutil.copytree(old_project, new_project, dirs_exist_ok=True)
            shutil.rmtree(old_project)
        else:
            old_project.rename(new_project)

    replacements = {
        str(src_data_dir): str(dest_data_dir),
        str(src_outputs): str(dest_outputs),
        src_project_name: dest_project_name,
    }
    _replace_text_in_tree(dest_data_dir, replacements)


def remove_link_metadata(path: Path) -> None:
    registry = load_link_registry()
    key = _link_key(path)
    if key in registry:
        del registry[key]
        save_link_registry(registry)


def _sessions_dir_for_session(session: dict, fallback_folder_name: str) -> Path:
    sessions_dir = session.get("sessionsDir")
    if sessions_dir:
        return Path(sessions_dir)
    path = Path(session["path"])
    try:
        return path.parents[2]
    except IndexError:
        return path.parent.parent.parent / fallback_folder_name


def _is_safe_cowork_data_dir(index_path: Path, data_dir: Path) -> bool:
    try:
        return data_dir.parent.resolve() == index_path.parent.resolve() and data_dir.name == index_path.stem
    except OSError:
        return False


def remove_session_from_account(session: dict, mode: str):
    index_path = Path(session["path"])
    if not index_path.exists():
        return False, "Essa sessão já não existe mais nesta conta."

    try:
        if mode == "cowork":
            data_dir = session.get("data_dir")
            data_dir = Path(data_dir) if data_dir else index_path.with_suffix("")
            if data_dir.exists() and not _is_safe_cowork_data_dir(index_path, data_dir):
                return False, "Remoção cancelada: pasta de dados Cowork inesperada."
            backup_path = backup_dir_tree(index_path.parent, "cowork-workspace")
            if data_dir.is_dir():
                shutil.rmtree(data_dir)
            index_path.unlink()
            remove_link_metadata(index_path)
        else:
            sessions_dir = _sessions_dir_for_session(session, "claude-code-sessions")
            backup_path = backup_sessions_dir(sessions_dir)
            index_path.unlink()
            remove_link_metadata(index_path)
    except Exception as e:
        backup_info = f" (backup salvo em {backup_path.name})" if "backup_path" in locals() else ""
        return False, f"Falha ao remover sessão{backup_info}: {e}"

    if mode == "cowork":
        removed = "Sessão removida desta conta."
    else:
        removed = "Sessão removida desta conta. Transcript compartilhado preservado."
    return True, f"{removed}\nBackup salvo em backups\\{backup_path.name}."


def link_session_to_account(session: dict, target_account_id: str):
    target_ws = find_target_workspace_dir_in_roots("claude-code-sessions", target_account_id)
    if target_ws is None:
        return False, (
            "Essa conta ainda não tem uma pasta de workspace em "
            "claude-code-sessions. Abra a aba Code pelo menos uma vez "
            "logado nela (qualquer projeto) para criá-la, depois tente de novo."
        )

    dest_path = target_ws / session["path"].name
    try:
        if dest_path.exists():
            backup_path = backup_sessions_dir(target_ws.parent.parent)
            write_code_index_clone(session["path"], dest_path, session.get("accountId", ""), source_origin_account(session))
            return True, (
                "Vínculo atualizado para esta conta.\n\n"
                "A sessão já existia aqui; agora o Session Linker registrou a troca de volta, "
                "manteve a origem original visível na lista e preservou conversas Code independentes."
            )

        backup_path = backup_sessions_dir(target_ws.parent.parent)
        write_code_index_clone(session["path"], dest_path, session.get("accountId", ""), source_origin_account(session))
    except Exception as e:
        backup_info = f" (backup salvo em {backup_path.name})" if "backup_path" in locals() else ""
        return False, f"Falha ao vincular{backup_info}: {e}"

    return True, (
        f"Vinculado. Backup salvo em backups\\{backup_path.name}.\n\n"
        "Feche o Claude Desktop completamente (bandeja do sistema) e abra de "
        "novo, logado na conta de destino, para ver a sessão na sidebar."
    )


def link_cowork_session_to_account(session: dict, target_account_id: str):
    target_ws = find_target_workspace_dir_in_roots("local-agent-mode-sessions", target_account_id)
    if target_ws is None:
        return False, (
            "Essa conta ainda não tem uma pasta de workspace em "
            "local-agent-mode-sessions. Abra o Cowork pelo menos uma vez "
            "logado nela para criá-la, depois tente de novo."
        )

    dest_path = target_ws / session["path"].name
    dest_data_dir = target_ws / session["data_dir"].name if session.get("data_dir") else None
    dest_already_exists = dest_path.exists() and (not dest_data_dir or dest_data_dir.exists())
    if dest_already_exists:
        try:
            backup_path = backup_dir_tree(target_ws, "cowork-workspace")
            normalize_cowork_session_copy(
                session["path"],
                dest_path,
                Path(session["data_dir"]) if session.get("data_dir") else None,
                dest_data_dir,
                session.get("accountId", ""),
                source_origin_account(session),
            )
            return True, (
                "Vínculo atualizado para esta conta.\n\n"
                f"A sessão já existia aqui; backup salvo em backups\\{backup_path.name}. "
                "O Session Linker reparou o caminho interno do Cowork e manteve a origem original visível na lista."
            )
        except Exception as e:
            return False, f"Falha ao atualizar vínculo: {e}"

    # Scoped backup: only the destination workspace folder, not the whole
    # local-agent-mode-sessions tree -- Cowork data (outputs/, uploads/) can
    # run into hundreds of MB, unlike Code's lightweight index-only folders.
    backup_path = backup_dir_tree(target_ws, "cowork-workspace")
    try:
        if session.get("data_dir") and session["data_dir"].is_dir():
            # ignore_dangling_symlinks: session output folders can contain
            # tool install artifacts (e.g. npm's node_modules/.bin) with
            # symlinks that no longer resolve -- that shouldn't abort an
            # otherwise successful copy of the actual conversation data.
            shutil.copytree(
                session["data_dir"], dest_data_dir,
                symlinks=True, ignore_dangling_symlinks=True,
            )
        normalize_cowork_session_copy(
            session["path"],
            dest_path,
            Path(session["data_dir"]) if session.get("data_dir") else None,
            dest_data_dir,
            session.get("accountId", ""),
            source_origin_account(session),
        )
    except Exception as e:
        return False, f"Falha ao copiar (backup salvo em {backup_path.name}): {e}"

    return True, (
        f"Vinculado. Backup salvo em backups\\{backup_path.name}.\n\n"
        "Feche o Claude Desktop completamente (bandeja do sistema) e abra de "
        "novo, logado na conta de destino, para ver a sessão do Cowork."
    )


def assign_default_label(account_id: str, labels: dict) -> str:
    """Short, stable placeholder ("Conta 1", "Conta 2", ...) until the user
    renames it themselves via the edit (pencil) button.

    We deliberately don't try to guess a name from project folders or
    session titles -- that produced long, awkward labels that were harder
    to read than just asking the user, who already knows which account is
    which far better than any heuristic could. We also never touch
    Desktop's encrypted OAuth cache to recover a real email; that's
    credential material, out of scope for a local labeling convenience.

    The number is assigned once and persisted in labels (as "Conta N"),
    so it doesn't shift around between runs even before the user renames it.
    """
    used_numbers = set()
    for v in labels.values():
        if isinstance(v, str) and v.startswith("Conta ") and v[6:].isdigit():
            used_numbers.add(int(v[6:]))
    n = 1
    while n in used_numbers:
        n += 1
    label = f"Conta {n}"
    labels[account_id] = label
    save_labels(labels)
    return label


def fmt_ts(ms: int) -> str:
    if not ms:
        return "--"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "--"


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_transcript_path(cli_session_id: str):
    """Locate the real `.jsonl` transcript for a cliSessionId, regardless of
    which project-folder hash it lives under -- session ids are UUIDs, so a
    filename match is unambiguous without needing to reproduce Claude
    Code's cwd-to-folder-name hashing scheme."""
    if not cli_session_id or not CLAUDE_PROJECTS_DIR.exists():
        return None
    matches = list(CLAUDE_PROJECTS_DIR.rglob(f"{cli_session_id}.jsonl"))
    return matches[0] if matches else None


def parse_iso_ts(ts):
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def read_session_progress(session: dict, mode: str) -> dict:
    """Reads the actual conversation file -- the single source of truth --
    rather than trusting Desktop's per-account index metadata, which can go
    stale. Returns message count and the last recorded event's timestamp.

    Code sessions share one account-agnostic transcript (found via
    cliSessionId under ~/.claude/projects/). Cowork sessions keep their own
    audit.jsonl inside the session's data_dir, with the equivalent
    "_audit_timestamp" field instead of Code's "timestamp".
    """
    if mode == "cowork":
        data_dir = session.get("data_dir")
        if not data_dir or not data_dir.is_dir():
            return {"found": False}
        path = data_dir / "audit.jsonl"
        ts_key = "_audit_timestamp"
    else:
        path = find_transcript_path(session["cliSessionId"])
        ts_key = "timestamp"

    if path is None or not path.exists():
        return {"found": False}
    message_count = 0
    last_ts_raw = None
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("type") in ("user", "assistant"):
                    message_count += 1
                ts = entry.get(ts_key)
                if ts:
                    last_ts_raw = ts
    except Exception:
        return {"found": False}
    return {
        "found": True,
        "path": path,
        "message_count": message_count,
        "last_timestamp": parse_iso_ts(last_ts_raw),
        "mtime": path.stat().st_mtime,
    }


def conversation_file_available(session: dict, mode: str | None = None) -> bool:
    if mode is None:
        return True
    if mode == "cowork":
        data_dir = session.get("data_dir")
        return bool(data_dir and data_dir.is_dir() and (data_dir / "audit.jsonl").exists())
    return find_transcript_path(session.get("cliSessionId", "")) is not None


def conversation_file_identity(session: dict, mode: str | None = None):
    if mode == "cowork":
        data_dir = session.get("data_dir")
        if not data_dir:
            return None
        path = Path(data_dir) / "audit.jsonl"
    elif mode == "code":
        path = find_transcript_path(session.get("cliSessionId", ""))
    else:
        return None
    if path is None or not path.exists():
        return None
    try:
        return path.resolve()
    except OSError:
        return path


def sessions_are_comparable(left_session: dict, right_session: dict, mode: str | None = None) -> bool:
    left_identity = conversation_file_identity(left_session, mode)
    right_identity = conversation_file_identity(right_session, mode)
    return not (left_identity is not None and left_identity == right_identity)


def is_direct_linked_counterpart(
    source_account_id: str,
    source_session: dict,
    account_id: str,
    session: dict,
    mode: str | None = None,
) -> bool:
    if account_id == source_account_id:
        return False

    source_cli_id = source_session.get("cliSessionId")
    session_cli_id = session.get("cliSessionId")
    if mode == "code":
        return (
            session.get("linkedFromAccount") == source_account_id
            and session.get("linkedSourceCliSessionId") == source_cli_id
        ) or (
            source_session.get("linkedFromAccount") == account_id
            and source_session.get("linkedSourceCliSessionId") == session_cli_id
        )

    return bool(source_cli_id and session_cli_id and session_cli_id == source_cli_id)


def find_possible_duplicates(sessions_by_account: dict, mode: str | None = None) -> dict:
    """Groups sessions by normalized cwd across ALL accounts. Returns
    {cwd: [(account_id, session), ...]} only for cwds where 2+ DIFFERENT
    accounts each have a session with a DIFFERENT cliSessionId -- i.e. two
    genuinely independent conversations about the same project, not just a
    linked copy (which always shares one cliSessionId and can never
    diverge, so it's excluded here on purpose).
    """
    by_cwd: dict[str, list[tuple[str, dict]]] = {}
    for account_id, sessions in sessions_by_account.items():
        for s in sessions:
            cwd = (s.get("cwd") or "").rstrip("\\/").lower()
            if not cwd:
                continue
            if not conversation_file_available(s, mode):
                continue
            by_cwd.setdefault(cwd, []).append((account_id, s))

    duplicates = {}
    for cwd, entries in by_cwd.items():
        accounts_involved = {a for a, _ in entries}
        cli_ids_involved = {s["cliSessionId"] for _, s in entries}
        if len(accounts_involved) >= 2 and len(cli_ids_involved) >= 2:
            duplicates[cwd] = entries
    return duplicates


def find_linked_session_groups(sessions_by_account: dict) -> dict:
    by_cli: dict[str, list[tuple[str, dict]]] = {}
    for account_id, sessions in sessions_by_account.items():
        for session in sessions:
            cli_id = session.get("cliSessionId")
            if cli_id:
                by_cli.setdefault(cli_id, []).append((account_id, session))

    return {
        cli_id: entries
        for cli_id, entries in by_cli.items()
        if len({account_id for account_id, _ in entries}) >= 2
    }


def build_compare_candidates(
    sessions_by_account: dict,
    source_account_id: str,
    source_session: dict,
    mode: str | None = None,
) -> list[tuple[str, dict]]:
    source_path = source_session.get("path")
    candidates = []
    for account_id, sessions in sessions_by_account.items():
        for session in sessions:
            same_record = account_id == source_account_id and session.get("path") == source_path
            if same_record:
                continue
            candidates.append((account_id, session))

    def sort_key(item):
        account_id, session = item
        linked_copy = is_direct_linked_counterpart(source_account_id, source_session, account_id, session, mode)
        return (0 if linked_copy else 1, -session.get("lastActivityAt", 0))

    candidates.sort(key=sort_key)
    return candidates


def linked_compare_targets(
    candidates: list[tuple[str, dict]],
    source_account_id: str,
    source_session: dict,
    mode: str | None = None,
) -> list[tuple[str, dict]]:
    return [
        (account_id, session)
        for account_id, session in candidates
        if is_direct_linked_counterpart(source_account_id, source_session, account_id, session, mode)
        and sessions_are_comparable(source_session, session, mode)
    ]


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class SessionLinkerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title(WIN_TITLE)
        self.configure(fg_color=BG)
        self.resizable(True, True)
        self._icon_photo = None
        self._icon_photos = []
        if ICON_PATH.exists():
            try:
                self.iconbitmap(default=str(ICON_PATH))
            except Exception:
                try:
                    self.iconbitmap(str(ICON_PATH))
                except Exception:
                    pass
        if not sys.platform.startswith("win"):
            try:
                from PIL import Image as _PILImage, ImageTk as _ImageTk
                src = str(ICON_PATH if ICON_PATH.exists() else ICON_PNG)
                for sz in (16, 24, 32, 48, 64, 128, 256):
                    frame = _PILImage.open(src).convert("RGBA").resize((sz, sz), _PILImage.LANCZOS)
                    self._icon_photos.append(_ImageTk.PhotoImage(frame))
                if self._icon_photos:
                    self.iconphoto(True, *self._icon_photos)
            except Exception:
                pass

        self.labels = load_labels()
        self.sessions_by_account: dict[str, list[dict]] = {}
        self.duplicates: dict = {}
        self.link_groups: dict[str, list[tuple[str, dict]]] = {}
        self.session_mode = "code"  # "code" | "cowork"
        self.selected_account = None  # None = "all accounts"
        self.selected_session = None
        self._session_cards = []
        self._account_tiles = []
        self._mode_btns = {}
        self._tooltip = {"win": None, "after_id": None, "widget": None}
        self._refresh_generation = 0
        self.bind("<Leave>", lambda _event=None: self._hide_tooltip(), add="+")
        self.bind("<Configure>", lambda _event=None: self._hide_tooltip(), add="+")
        self.bind("<MouseWheel>", lambda _event=None: self._hide_tooltip(), add="+")

        self._compact_layout = self.winfo_screenwidth() < 1000 or self.winfo_screenheight() < 700
        self._build()
        self._render_loading()
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_w = min(1120, max(640, screen_w - 48))
        target_h = min(760, max(480, screen_h - 72))
        self.geometry(f"{target_w}x{target_h}")
        self.minsize(min(720, target_w), min(480, target_h))
        self._center(target_w, target_h)
        self.after(0, self._show_main_window)
        self.after(180, self._show_main_window)
        # Paint first, then load data a beat later -- scanning the session
        # index + checking tasklist would otherwise delay the very first
        # frame, which reads as "the app is frozen".
        self.after(30, self.refresh)

    def _show_main_window(self):
        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            # Briefly topmost so a double-clicked launcher cannot leave the
            # freshly mapped Tk window hidden behind the file explorer.
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass

    def _center(self, w, h):
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = min(w, max(480, sw - 32))
            h = min(h, max(360, sh - 48))
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 3)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    # -- layout ---------------------------------------------------------

    def _build(self):
        self._f_hero = ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        self._f_h = ctk.CTkFont(family="Segoe UI", size=21, weight="bold")
        self._f_s = ctk.CTkFont(family="Segoe UI", size=13)
        self._f_b = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self._f_x = ctk.CTkFont(family="Segoe UI", size=11)
        self._f_mono = ctk.CTkFont(family="Consolas", size=11)

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, fg_color=PAPER, corner_radius=0)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=0)
        shell.grid_columnconfigure(1, weight=1)

        # --- Sidebar (dark) -------------------------------------------
        sidebar_w = 230 if self._compact_layout else 300
        sidebar = ctk.CTkFrame(shell, fg_color=BG, corner_radius=0, width=sidebar_w)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        side = ctk.CTkScrollableFrame(sidebar, fg_color="transparent", scrollbar_button_color=BRD)
        side.pack(fill="both", expand=True, padx=22, pady=22)

        ctk.CTkLabel(side, text=WIN_TITLE, font=self._f_h, text_color=TXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            side, text="Alterne sessões do Code e do Cowork entre suas contas Claude.",
            font=self._f_x, text_color=TXT2, anchor="w", justify="left", wraplength=180 if self._compact_layout else 250,
        ).pack(anchor="w", pady=(2, 0))

        mode_row = ctk.CTkFrame(side, fg_color=SURF, corner_radius=8)
        mode_row.pack(fill="x", pady=(18, 0))
        mode_row.grid_columnconfigure(0, weight=1)
        mode_row.grid_columnconfigure(1, weight=1)
        self._make_mode_button(mode_row, "code", "💻 Code", 0)
        self._make_mode_button(mode_row, "cowork", "🌐 Cowork", 1)

        active_header = ctk.CTkFrame(side, fg_color="transparent")
        active_header.pack(fill="x", pady=(26, 10))
        ctk.CTkLabel(active_header, text="CONTAS DETECTADAS", font=self._f_x, text_color=TXT3).pack(side="left")

        self._accounts_list = ctk.CTkFrame(side, fg_color="transparent")
        self._accounts_list.pack(fill="x")

        self._desktop_warning = ctk.CTkLabel(
            side, text="", font=self._f_x, text_color=YELLOW, anchor="w", height=22,
            justify="left", wraplength=340,
        )
        self._desktop_warning.pack(anchor="w", pady=(12, 0), fill="x")

        ctk.CTkButton(
            side, text="↻ Atualizar", height=32, fg_color=SURF, hover_color=SURF2,
            text_color=TXT2, border_width=1, border_color=BRD, font=self._f_x,
            command=self.refresh,
        ).pack(anchor="w", pady=(8, 0), fill="x")

        # --- Main (light) -----------------------------------------------
        main = ctk.CTkFrame(shell, fg_color=PAPER, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 14))
        header.grid_columnconfigure(0, weight=1)
        head_text = ctk.CTkFrame(header, fg_color="transparent")
        head_text.grid(row=0, column=0, sticky="w")
        self._filter_title = ctk.CTkLabel(head_text, text="Todas as sessões", font=self._f_hero, text_color=INK, anchor="w")
        self._filter_title.pack(anchor="w")
        self._filter_subtitle = ctk.CTkLabel(
            head_text, text="", font=self._f_s, text_color=INK2, anchor="w",
        )
        self._filter_subtitle.pack(anchor="w", pady=(2, 0))

        self._scroll = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 22))
        self._scroll.grid_columnconfigure(0, weight=1)

        # --- Footer (full width, version bottom-left, credit bottom-right) --
        footer = ctk.CTkFrame(self, fg_color=SURF, corner_radius=0, height=28, border_width=0)
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_propagate(False)
        ctk.CTkLabel(
            footer, text=f"v{APP_VERSION}", font=self._f_x, text_color=TXT3,
        ).pack(side="left", padx=16, pady=4)
        ctk.CTkLabel(
            footer, text=DEV_CREDIT, font=self._f_x, text_color=TXT3,
        ).pack(side="right", padx=16, pady=4)

    # -- data / rendering -------------------------------------------------

    def refresh(self):
        # File scanning + the tasklist check both do blocking I/O; run them
        # off the UI thread so the window stays responsive while loading.
        mode = self.session_mode
        self._refresh_generation += 1
        generation = self._refresh_generation

        def worker():
            active_account = get_active_account_uuid()
            sessions_by_account = scan_cowork_sessions() if mode == "cowork" else scan_sessions()
            running = is_desktop_running()
            self.after(0, lambda: self._apply_refresh(generation, mode, active_account, sessions_by_account, running))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_refresh(self, generation, mode, active_account, sessions_by_account, running):
        if generation != self._refresh_generation or mode != self.session_mode:
            return
        self.active_account = active_account
        self.sessions_by_account = sessions_by_account
        self.duplicates = find_possible_duplicates(sessions_by_account, mode)
        self.link_groups = find_linked_session_groups(sessions_by_account)
        self._desktop_warning.configure(
            text="⚠ Feche o Claude Desktop antes de vincular." if running else ""
        )
        self._render_accounts()
        self._render_sessions()

    def _render_loading(self):
        self._desktop_warning.configure(text="")
        for w in self._accounts_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self._accounts_list, text="Carregando contas…", font=self._f_x,
            text_color=TXT3, anchor="w",
        ).pack(anchor="w", pady=(4, 0), fill="x")
        self._filter_subtitle.configure(text="Lendo sessões locais…")
        for w in self._scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self._scroll, text="Carregando sessões…", font=self._f_s,
            text_color=INK2, anchor="w",
        ).pack(anchor="w", pady=20)

    def _make_mode_button(self, parent, key, label, col):
        is_active = self.session_mode == key
        btn = ctk.CTkButton(
            parent, text=label, height=34, corner_radius=6,
            font=self._f_b if is_active else self._f_s,
            fg_color=SURF2 if is_active else "transparent",
            hover_color=SURF2, text_color=TXT if is_active else TXT3,
            command=lambda: self._set_mode(key),
        )
        btn.grid(row=0, column=col, sticky="ew", padx=3, pady=3)
        self._mode_btns[key] = btn
        return btn

    def _set_mode(self, mode):
        if mode == self.session_mode:
            return
        self.session_mode = mode
        self.selected_account = None
        for key, btn in self._mode_btns.items():
            is_active = key == mode
            btn.configure(
                font=self._f_b if is_active else self._f_s,
                fg_color=SURF2 if is_active else "transparent",
                text_color=TXT if is_active else TXT3,
            )
        self.refresh()

    def _account_label(self, account_id):
        if account_id in self.labels:
            return self.labels[account_id]
        return assign_default_label(account_id, self.labels)

    @staticmethod
    def _plural_sessions(count):
        return f"{count} sessão" if count == 1 else f"{count} sessões"

    @staticmethod
    def _plural_other_accounts(count):
        return f"{count} outra conta" if count == 1 else f"{count} outras contas"

    def _link_badges(self, account_id, session):
        origin = session.get("originAccount")
        linked_from = session.get("linkedFromAccount")
        badges = []
        if origin:
            badges.append((f"Origem: {self._account_label(origin)}", "origin"))
        if linked_from and linked_from != account_id:
            badges.append((f"Veio de: {self._account_label(linked_from)}", "link"))
        if badges:
            return badges

        entries = self.link_groups.get(session.get("cliSessionId"), [])
        other_accounts = sorted({a for a, _ in entries if a != account_id})
        if other_accounts:
            names = ", ".join(self._account_label(a) for a in other_accounts[:3])
            if len(other_accounts) > 3:
                names += f" +{len(other_accounts) - 3}"
            return [
                (f"Origem provável: {self._account_label(account_id)}", "origin"),
                (f"Também vinculada em: {names}", "link"),
            ]
        return []

    def _render_accounts(self):
        self._hide_tooltip()
        for w in self._accounts_list.winfo_children():
            w.destroy()
        self._account_tiles = []

        all_btn = ctk.CTkButton(
            self._accounts_list, text="Todas as contas", anchor="w", height=34,
            corner_radius=6, font=self._f_b if self.selected_account is None else self._f_s,
            fg_color=SURF2 if self.selected_account is None else "transparent",
            hover_color=SURF2, text_color=TXT,
            command=lambda: self._select_account(None),
        )
        all_btn.pack(fill="x", pady=(0, 4))

        for account_id in sorted(self.sessions_by_account.keys()):
            n = len(self.sessions_by_account[account_id])
            is_active = account_id == self.active_account
            is_selected = account_id == self.selected_account
            label = self._account_label(account_id)
            status_bits = []
            if is_active:
                status_bits.append("ativa agora")
            status_bits.append(self._plural_sessions(n))
            subtitle = "  ·  ".join(status_bits)

            row = ctk.CTkFrame(
                self._accounts_list, fg_color=SURF2 if is_selected else "transparent", corner_radius=6,
            )
            row.pack(fill="x", pady=(0, 4))
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=0)

            # Two deliberate rows -- bold name, small muted meta line below
            # it -- read as a designed block instead of the earlier version,
            # where a single wrapped label looked like broken text.
            btn = ctk.CTkButton(
                row, text=label, anchor="w", height=44,
                corner_radius=6, font=self._f_b,
                fg_color="transparent", hover_color=SURF2,
                text_color=GREEN if is_active else TXT,
                command=lambda a=account_id: self._select_account(a),
            )
            btn.grid(row=0, column=0, sticky="ew", padx=(10, 0), pady=(6, 0))
            meta = ctk.CTkLabel(
                row, text=subtitle, font=self._f_x,
                text_color=GREEN if is_active else TXT3, anchor="w",
            )
            meta.grid(row=1, column=0, sticky="ew", padx=(10, 0), pady=(0, 8))
            meta.bind("<Button-1>", lambda _e, a=account_id: self._select_account(a))

            edit_btn = ctk.CTkButton(
                row, text="✎", width=34, height=34, corner_radius=6,
                fg_color=SURF2, hover_color=SURF3, text_color=TXT2,
                border_width=1, border_color=BRD,
                font=self._f_x, command=lambda a=account_id: self._rename_account(a),
            )
            edit_btn.grid(row=0, column=1, rowspan=2, sticky="n", padx=(8, 8), pady=8)
            self._add_tooltip(edit_btn, "Renomear conta")

    def _select_account(self, account_id):
        self.selected_account = account_id
        self._render_accounts()
        self._render_sessions()

    def _render_sessions(self):
        self._hide_tooltip()
        for w in self._scroll.winfo_children():
            w.destroy()

        self._filter_subtitle.configure(
            text=(
                "Clique em uma sessão do Cowork para vincular a outra conta ou comparar o progresso."
                if self.session_mode == "cowork" else
                "Clique em uma sessão do Code para vincular a outra conta ou comparar o progresso."
            )
        )

        if self.selected_account is None:
            self._filter_title.configure(text="Todas as sessões")
            items = []
            for account_id, sessions in self.sessions_by_account.items():
                for s in sessions:
                    items.append((account_id, s))
            items.sort(key=lambda t: t[1]["lastActivityAt"], reverse=True)
        else:
            self._filter_title.configure(text=self._account_label(self.selected_account))
            items = [(self.selected_account, s) for s in self.sessions_by_account.get(self.selected_account, [])]

        if not items:
            ctk.CTkLabel(
                self._scroll, text="Nenhuma sessão encontrada.", font=self._f_s, text_color=INK2,
            ).pack(anchor="w", pady=20)
            return

        for account_id, session in items:
            self._build_session_card(account_id, session)

    def _build_session_card(self, account_id, session):
        card_mode = self.session_mode
        card = ctk.CTkFrame(self._scroll, fg_color=PAPER2, corner_radius=8, border_width=1, border_color=LINE)
        card.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        inner.grid_columnconfigure(0, weight=1)

        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top_row, text=session["title"], font=self._f_b, text_color=INK,
            anchor="w", wraplength=620, justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12))
        if self.selected_account is None:
            ctk.CTkLabel(
                top_row, text=self._account_label(account_id), font=self._f_x, text_color=INK3, anchor="e",
            ).grid(row=0, column=1, sticky="e")

        meta = f'{session["cwd"]}   ·   {fmt_ts(session["lastActivityAt"])}   ·   {session["cliSessionId"][:8]}'
        ctk.CTkLabel(
            inner, text=meta, font=self._f_mono, text_color=INK3,
            anchor="w", wraplength=760, justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        row_i = 2
        badges = self._link_badges(account_id, session)
        if badges:
            trace = ctk.CTkFrame(
                inner, fg_color=TRACE_BG, corner_radius=8,
                border_width=1, border_color=TRACE_BORDER,
            )
            trace.grid(row=row_i, column=0, sticky="ew", pady=(0, 12))
            trace.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                trace, text="Rastreamento entre contas", font=self._f_b,
                text_color=TRACE_TEXT, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))
            badge_row = ctk.CTkFrame(trace, fg_color="transparent")
            badge_row.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
            for text, kind in badges:
                bg = BADGE_GREEN_BG if kind == "origin" else BADGE_BLUE_BG
                ctk.CTkLabel(
                    badge_row, text=text, font=self._f_b, text_color=BADGE_TEXT,
                    fg_color=bg, corner_radius=6, padx=10, pady=5,
                ).pack(side="left", padx=(0, 6))
            row_i += 1

        cwd_key = (session.get("cwd") or "").rstrip("\\/").lower()
        dup_group = self.duplicates.get(cwd_key)
        if dup_group:
            others = [
                (a, s) for a, s in dup_group
                if s["cliSessionId"] != session["cliSessionId"]
            ]
            if others:
                ctk.CTkButton(
                    inner, text=f"⚠ Possível duplicata em {self._plural_other_accounts(len(set(a for a, _ in others)))} — comparar",
                    anchor="w", height=28, corner_radius=6, font=self._f_x,
                    fg_color=WARN_BG, hover_color=AMBER, text_color=AMBER, border_width=1, border_color=AMBER,
                    command=lambda a=account_id, s=session, o=others, m=card_mode: self._open_compare_dialog((a, s), o, m),
                ).grid(row=row_i, column=0, sticky="w", pady=(0, 10))
                row_i += 1

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.grid(row=row_i, column=0, sticky="ew")
        for col in range(3):
            actions.grid_columnconfigure(col, weight=1, uniform="session_actions")
        ctk.CTkButton(
            actions, text="🔗 Vincular conta", height=32, fg_color=GREEN, hover_color=GREEN_H,
            text_color=INK, font=self._f_x, corner_radius=6,
            command=lambda s=session, a=account_id, m=card_mode: self._open_link_dialog(s, a, m),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        compare_btn = ctk.CTkButton(
            actions, text="⇄ Comparar", height=32, fg_color=SURF2, hover_color=SURF3,
            text_color=TXT, font=self._f_x, corner_radius=6,
            command=lambda s=session, a=account_id, m=card_mode: self._open_compare_picker((a, s), m),
        )
        compare_btn.grid(row=0, column=1, sticky="ew", padx=6)
        remove_btn = ctk.CTkButton(
            actions, text="Remover", height=32, fg_color=RED, hover_color=RED_H,
            text_color="#FFFFFF", font=self._f_x, corner_radius=6,
            command=lambda s=session, a=account_id, m=card_mode: self._open_remove_dialog(s, a, m),
        )
        remove_btn.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self._add_tooltip(
            compare_btn,
            "Compara esta sessão com a cópia vinculada em outra conta. "
            "Se não houver vínculo direto, permite escolher outra sessão.",
        )
        self._add_tooltip(
            remove_btn,
            "Remove esta sessão apenas desta conta, com backup antes da alteração.",
        )

    # -- actions ----------------------------------------------------------

    def _open_remove_dialog(self, session, account_id, mode=None):
        mode = mode or self.session_mode
        dialog_w, dialog_h = 560, 420
        dialog = ctk.CTkToplevel(self)
        dialog.title("Remover sessão")
        dialog.configure(fg_color=BG)
        dialog.resizable(True, True)
        dialog.transient(self)
        self._center_toplevel(dialog, dialog_w, dialog_h)
        dialog.grab_set()
        if ICON_PATH.exists():
            try:
                dialog.after(150, lambda: dialog.iconbitmap(str(ICON_PATH)))
            except Exception:
                pass

        box = ctk.CTkFrame(dialog, fg_color=SURF, corner_radius=8, border_width=1, border_color=BRD)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(box, text="Remover sessão desta conta?", font=self._f_b, text_color=TXT).pack(anchor="w", padx=18, pady=(18, 6))
        ctk.CTkLabel(
            box, text=session["title"], font=self._f_s, text_color=TXT2,
            wraplength=480, justify="left",
        ).pack(anchor="w", padx=18)
        ctk.CTkLabel(
            box, text=f"Conta: {self._account_label(account_id)}", font=self._f_x, text_color=TXT3,
            wraplength=480, justify="left",
        ).pack(anchor="w", padx=18, pady=(4, 0))

        if mode == "cowork":
            detail = (
                "Será criado um backup e depois serão removidos o índice desta conta "
                "e a pasta local de dados do Cowork para esta sessão."
            )
        else:
            detail = (
                "Será criado um backup e depois será removido só o índice desta conta. "
                "O transcript compartilhado do Code não será apagado."
            )
        ctk.CTkLabel(
            box, text=detail, font=self._f_x, text_color=TXT2,
            wraplength=500, justify="left",
        ).pack(anchor="w", padx=18, pady=(16, 0))

        warning = ctk.CTkFrame(box, fg_color="#311A18", corner_radius=6, border_width=1, border_color=RED)
        warning.pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(
            warning, text="Feche o Claude Desktop antes de remover para evitar que ele recrie ou sobrescreva arquivos.",
            font=self._f_x, text_color="#FFB3A8", anchor="w", justify="left", wraplength=470,
        ).pack(anchor="w", padx=12, pady=10, fill="x")

        status = ctk.CTkLabel(box, text="", font=self._f_x, text_color=TXT2, anchor="w", justify="left", wraplength=500)
        status.pack(anchor="w", padx=18, pady=(10, 0), fill="x")

        def do_remove():
            if is_desktop_running():
                status.configure(text="Claude Desktop está aberto. Feche pela bandeja do sistema e clique novamente para confirmar.", text_color=YELLOW)
                if not getattr(dialog, "_confirmed_running", False):
                    dialog._confirmed_running = True
                    return
            remove_btn.configure(state="disabled")
            cancel_btn.configure(state="disabled")
            status.configure(text="Removendo e criando backup...", text_color=TXT2)

            def worker():
                ok, msg = remove_session_from_account(session, mode)

                def apply():
                    if not dialog.winfo_exists():
                        return
                    status.configure(text=msg, text_color=GREEN if ok else RED)
                    if ok:
                        dialog._remove_completed = True
                        warning.pack_forget()
                        remove_btn.pack_forget()
                        cancel_btn.configure(text="Fechar", state="normal", fg_color=GREEN, hover_color=GREEN_H, text_color=INK, width=144)
                        cancel_btn.pack_forget()
                        cancel_btn.pack(side="right", pady=8)
                        self.refresh()
                    else:
                        remove_btn.configure(state="normal")
                        cancel_btn.configure(state="normal")

                self.after(0, apply)

            threading.Thread(target=worker, daemon=True).start()

        def close_dialog():
            dialog.destroy()
            if getattr(dialog, "_remove_completed", False):
                self.refresh()

        actions = self._dialog_actions(box)
        actions.pack(fill="x", padx=18, pady=(6, 18))
        cancel_btn = self._dialog_button(actions, "Cancelar", close_dialog, "secondary", "left")
        remove_btn = self._dialog_button(actions, "Remover", do_remove, "danger", "right")

    def _open_link_dialog(self, session, source_account_id, mode=None):
        mode = mode or self.session_mode
        others = [a for a in self.sessions_by_account.keys() if a != source_account_id]
        if not others:
            self._toast("Ainda não há outra conta detectada neste computador.")
            return

        dialog_w = 700
        dialog_h = min(700, 430 + 52 * len(others))
        dialog = ctk.CTkToplevel(self)
        dialog.title("Vincular sessão")
        dialog.configure(fg_color=BG)
        dialog.resizable(True, True)
        dialog.transient(self)
        # Center over the main window instead of the OS default position --
        # an off-center Toplevel visually collides with the session list
        # behind it, which read as "messy" overlapping content.
        self._center_toplevel(dialog, dialog_w, dialog_h)
        dialog.grab_set()
        if ICON_PATH.exists():
            try:
                dialog.after(150, lambda: dialog.iconbitmap(str(ICON_PATH)))
            except Exception:
                pass

        box = ctk.CTkFrame(dialog, fg_color=SURF, corner_radius=8, border_width=1, border_color=BRD)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(box, text=session["title"], font=self._f_b, text_color=TXT, wraplength=620, justify="left").pack(anchor="w", padx=18, pady=(18, 6))
        ctk.CTkLabel(
            box, text=f'De: {self._account_label(source_account_id)}', font=self._f_x, text_color=TXT3,
        ).pack(anchor="w", padx=18)
        ctk.CTkLabel(box, text="Vincular esta sessão à conta:", font=self._f_s, text_color=TXT2).pack(anchor="w", padx=18, pady=(18, 8))

        def display_name(a):
            tag = " · ativa agora" if a == self.active_account else ""
            return f"{self._account_label(a)}{tag}"

        # A short list of clickable rows reads far more clearly than a
        # dropdown here -- there are rarely more than 2-3 target accounts,
        # and it matches the same row style used in the sidebar.
        selected = {"id": others[0]}
        target_rows = ctk.CTkFrame(box, fg_color="transparent")
        target_rows.pack(padx=18, pady=(0, 10), fill="x")
        row_buttons: dict[str, "ctk.CTkButton"] = {}

        def select_target(account_id):
            selected["id"] = account_id
            for aid, b in row_buttons.items():
                b.configure(
                    fg_color=SURF2 if aid == account_id else "transparent",
                    text_color=GREEN if aid == account_id else TXT,
                )

        for a in others:
            b = ctk.CTkButton(
                target_rows, text=display_name(a), anchor="w", height=38, corner_radius=6,
                font=self._f_s, fg_color="transparent", hover_color=SURF3, text_color=TXT,
                border_width=1, border_color=BRD,
                command=lambda a=a: select_target(a),
            )
            b.pack(fill="x", pady=(0, 6))
            row_buttons[a] = b
        select_target(others[0])

        status_box = ctk.CTkFrame(box, fg_color=SURF2, corner_radius=6, border_width=1, border_color=BRD)
        status = ctk.CTkLabel(
            status_box, text="", font=self._f_x, text_color=TXT2,
            anchor="w", justify="left", wraplength=600,
        )
        status.pack(anchor="w", padx=12, pady=10, fill="x")
        status_visible = {"value": False}

        def show_status(text, text_color=TXT2, bg=SURF2, border=BRD):
            if not status_visible["value"]:
                status_box.pack(fill="x", padx=18, pady=(0, 14))
                status_visible["value"] = True
            status_box.configure(fg_color=bg, border_color=border)
            status.configure(text=text, text_color=text_color)

        def do_link():
            target_id = selected["id"]
            if not target_id:
                return
            if is_desktop_running():
                show_status(
                    "⚠ Claude Desktop está aberto. Feche pela bandeja do sistema antes de continuar, "
                    "ou clique de novo para prosseguir mesmo assim.",
                    YELLOW,
                    WARN_BG,
                    AMBER,
                )
                if not getattr(dialog, "_confirmed_running", False):
                    dialog._confirmed_running = True
                    return

            # Cowork sessions can carry MBs of uploads/outputs, so the copy
            # runs off the UI thread -- Code sessions are tiny JSON files
            # and finish before the "Vinculando…" state is even noticeable.
            show_status("Vinculando…", TXT2, SURF2, BRD)
            link_btn.configure(state="disabled")

            def worker():
                if mode == "cowork":
                    ok, msg = link_cowork_session_to_account(session, target_id)
                else:
                    ok, msg = link_session_to_account(session, target_id)

                def apply():
                    if not dialog.winfo_exists():
                        return
                    show_status(
                        msg,
                        GREEN if ok else RED,
                        "#102018" if ok else "#311A18",
                        GREEN if ok else RED,
                    )
                    if ok:
                        dialog._link_completed = True
                        for button in row_buttons.values():
                            button.configure(state="disabled")
                        link_btn.pack_forget()
                        close_btn.configure(
                            text="Fechar",
                            fg_color=GREEN,
                            hover_color=GREEN_H,
                            text_color=INK,
                            width=144,
                        )
                        close_btn.pack_forget()
                        close_btn.pack(side="right", pady=8)
                        self.refresh()
                    else:
                        link_btn.configure(state="normal")

                self.after(0, apply)

            threading.Thread(target=worker, daemon=True).start()

        def close_dialog():
            dialog.destroy()
            if getattr(dialog, "_link_completed", False):
                self.refresh()

        actions = self._dialog_actions(box)
        actions.pack(side="bottom", fill="x", padx=18, pady=(4, 18))
        close_btn = self._dialog_button(actions, "Cancelar", close_dialog, "secondary", "left")
        link_btn = self._dialog_button(actions, "Vincular", do_link, "primary", "right")

    # -- comparison ---------------------------------------------------------

    def _open_compare_picker(self, source, mode=None):
        """Generic entry point: let the user pick ANY other session (any
        account, any project) to compare against."""
        mode = mode or self.session_mode
        source_account_id, source_session = source
        candidates = [
            (account_id, session)
            for account_id, session in build_compare_candidates(
                self.sessions_by_account,
                source_account_id,
                source_session,
                mode,
            )
            if sessions_are_comparable(source_session, session, mode)
        ]
        if not candidates:
            self._toast("Não há outra sessão independente para comparar ainda.")
            return
        linked_targets = linked_compare_targets(candidates, source_account_id, source_session, mode)
        if len(linked_targets) == 1:
            self._show_comparison(source, linked_targets[0], mode)
            return
        if len(linked_targets) > 1:
            self._show_candidate_picker(source, linked_targets, mode)
            return
        self._show_candidate_picker(source, candidates, mode)

    def _open_compare_dialog(self, source, others, mode=None):
        """Entry point from the duplicate-detection badge: `others` is
        already narrowed to sessions sharing this session's cwd."""
        mode = mode or self.session_mode
        _, source_session = source
        others = [
            (account_id, session)
            for account_id, session in others
            if sessions_are_comparable(source_session, session, mode)
        ]
        if not others:
            self._toast("Não há outra sessão independente para comparar ainda.")
            return
        if len(others) > 1:
            self._show_candidate_picker(source, others, mode)
        else:
            self._show_comparison(source, others[0], mode)

    def _show_candidate_picker(self, source, candidates, mode):
        _, source_session = source
        dialog_w = 520
        dialog_h = min(580, 180 + 54 * min(len(candidates), 8))
        dialog = ctk.CTkToplevel(self)
        dialog.title("Comparar sessão")
        dialog.configure(fg_color=BG)
        dialog.resizable(True, True)
        dialog.transient(self)
        self._center_toplevel(dialog, dialog_w, dialog_h)
        dialog.grab_set()
        if ICON_PATH.exists():
            try:
                dialog.after(150, lambda: dialog.iconbitmap(str(ICON_PATH)))
            except Exception:
                pass

        box = ctk.CTkFrame(dialog, fg_color=SURF, corner_radius=8, border_width=1, border_color=BRD)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(
            box, text=f'Comparar "{source_session["title"]}" com:', font=self._f_b,
            text_color=TXT, wraplength=460, justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 10))

        scroll = ctk.CTkScrollableFrame(box, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        source_account_id, source_session = source
        for a, s in candidates[:50]:
            title = self._clip(s["title"], 58)
            linked = a != source_account_id and s.get("cliSessionId") == source_session.get("cliSessionId")
            prefix = "Vinculada  ·  " if linked else ""
            meta = self._clip(f'{prefix}{self._account_label(a)}  ·  {s["cwd"]}', 72)
            ctk.CTkButton(
                scroll, text=f"{title}\n{meta}", anchor="w", height=48, corner_radius=6, font=self._f_x,
                fg_color="transparent", hover_color=SURF3, text_color=TXT,
                border_width=1, border_color=BRD,
                command=lambda a=a, s=s, m=mode: (dialog.destroy(), self._show_comparison(source, (a, s), m)),
            ).pack(fill="x", pady=(0, 6))

        actions = self._dialog_actions(box)
        actions.pack(fill="x", padx=16, pady=(0, 16))
        self._dialog_button(actions, "Cancelar", dialog.destroy, "secondary", "right")

    def _show_comparison(self, source, target, mode=None):
        mode = mode or self.session_mode
        dialog_w, dialog_h = 640, 380
        dialog = ctk.CTkToplevel(self)
        dialog.title("Comparação de sessões")
        dialog.configure(fg_color=BG)
        dialog.resizable(True, True)
        dialog.transient(self)
        self._center_toplevel(dialog, dialog_w, dialog_h)
        dialog.grab_set()
        if ICON_PATH.exists():
            try:
                dialog.after(150, lambda: dialog.iconbitmap(str(ICON_PATH)))
            except Exception:
                pass

        box = ctk.CTkFrame(dialog, fg_color=SURF, corner_radius=8, border_width=1, border_color=BRD)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(box, text="Comparando sessões", font=self._f_b, text_color=TXT).pack(anchor="w", padx=16, pady=(16, 2))
        status = ctk.CTkLabel(box, text="Lendo os arquivos de conversa (fonte real, não o índice do Desktop)...", font=self._f_x, text_color=TXT3)
        status.pack(anchor="w", padx=16, pady=(0, 10))

        cols = ctk.CTkFrame(box, fg_color="transparent")
        cols.pack(fill="x", padx=16)
        cols.grid_columnconfigure(0, weight=1)
        cols.grid_columnconfigure(1, weight=1)

        def make_column(col, account_id, session):
            c = ctk.CTkFrame(cols, fg_color=SURF2, corner_radius=8, border_width=1, border_color=BRD)
            c.grid(row=0, column=col, sticky="nsew", padx=(0, 8) if col == 0 else (8, 0))
            is_active = account_id == self.active_account
            ctk.CTkLabel(
                c, text=self._account_label(account_id), font=self._f_b,
                text_color=GREEN if is_active else TXT,
            ).pack(anchor="w", padx=14, pady=(14, 2))
            ctk.CTkLabel(
                c, text=session["title"], font=self._f_x, text_color=TXT2,
                wraplength=250, justify="left",
            ).pack(anchor="w", padx=14)
            stats_label = ctk.CTkLabel(
                c, text="Carregando…", font=self._f_x, text_color=TXT3,
                justify="left", anchor="w",
            )
            stats_label.pack(anchor="w", padx=14, pady=(10, 14), fill="x")
            return stats_label

        lbl_a = make_column(0, source[0], source[1])
        lbl_b = make_column(1, target[0], target[1])

        verdict = ctk.CTkLabel(box, text="", font=self._f_b, text_color=TXT, wraplength=560, justify="left")
        verdict.pack(anchor="w", padx=16, pady=(14, 6), fill="x")

        def fmt_progress(p):
            if not p.get("found"):
                return "Arquivo de conversa não encontrado neste computador."
            last = p["last_timestamp"]
            last_s = last.strftime("%d/%m/%Y %H:%M") if last else "--"
            return f'{p["message_count"]} mensagens\nÚltima atividade: {last_s}'

        def apply_results(pa, pb):
            if not dialog.winfo_exists():
                return
            status.configure(text="")
            lbl_a.configure(text=fmt_progress(pa))
            lbl_b.configure(text=fmt_progress(pb))
            a_label = self._account_label(source[0])
            b_label = self._account_label(target[0])
            if pa.get("found") and pb.get("found"):
                if pa["message_count"] == pb["message_count"]:
                    if pa["last_timestamp"] and pb["last_timestamp"] and pa["last_timestamp"] != pb["last_timestamp"]:
                        ahead = a_label if pa["last_timestamp"] > pb["last_timestamp"] else b_label
                        verdict.configure(text=f"→ Mesmo número de mensagens; {ahead} tem a atividade mais recente.", text_color=TXT)
                    else:
                        verdict.configure(text="→ Empate — mesmo número de mensagens.", text_color=TXT)
                else:
                    ahead = a_label if pa["message_count"] > pb["message_count"] else b_label
                    n = max(pa["message_count"], pb["message_count"])
                    verdict.configure(text=f"→ {ahead} está mais avançada ({n} mensagens).", text_color=GREEN)
            else:
                verdict.configure(text="Não foi possível ler um dos arquivos de conversa para comparar.", text_color=RED)

        def worker():
            pa = read_session_progress(source[1], mode)
            pb = read_session_progress(target[1], mode)
            self.after(0, lambda: apply_results(pa, pb))

        threading.Thread(target=worker, daemon=True).start()

        actions = self._dialog_actions(box)
        actions.pack(fill="x", padx=16, pady=(6, 16))
        self._dialog_button(actions, "Fechar", dialog.destroy, "secondary", "right")

    def _center_toplevel(self, dialog, w, h):
        self.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        w = min(w, max(360, sw - 48))
        h = min(h, max(300, sh - 72))
        dialog.minsize(min(360, w), min(300, h))
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        x = min(max(x, 0), max(sw - w - 8, 0))
        y = min(max(y, 0), max(sh - h - 48, 0))
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _dialog_actions(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent", height=64)
        frame.pack_propagate(False)
        return frame

    def _dialog_button(self, parent, text, command, kind="secondary", side="right"):
        if kind == "primary":
            fg, hover, color, width = GREEN, GREEN_H, INK, 136
        elif kind == "danger":
            fg, hover, color, width = RED, RED_H, "#FFFFFF", 136
        else:
            fg, hover, color, width = SURF2, SURF3, TXT2, 116
        btn = ctk.CTkButton(
            parent, text=text, width=width, height=42, fg_color=fg,
            hover_color=hover, text_color=color, font=self._f_s,
            corner_radius=6, command=command,
        )
        btn.pack(side=side, pady=8)
        return btn

    @staticmethod
    def _clip(text, limit):
        text = str(text or "")
        return text if len(text) <= limit else f"{text[: max(limit - 1, 0)]}…"

    def _rename_account(self, account_id):
        current = self._account_label(account_id)
        w, h = 420, 250
        dialog = ctk.CTkToplevel(self)
        dialog.title("Renomear conta")
        dialog.configure(fg_color=BG)
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.geometry(f"{w}x{h}")
        self._center_toplevel(dialog, w, h)
        dialog.grab_set()
        if ICON_PATH.exists():
            try:
                dialog.after(150, lambda: dialog.iconbitmap(str(ICON_PATH)))
            except Exception:
                pass

        box = ctk.CTkFrame(dialog, fg_color=SURF, corner_radius=8, border_width=1, border_color=BRD)
        box.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(box, text="Nome desta conta", font=self._f_b, text_color=TXT).pack(anchor="w", padx=16, pady=(16, 2))
        ctk.CTkLabel(
            box, text=f"Só afeta o que você vê aqui no Session Linker (ID interno: {account_id[:8]}…).",
            font=self._f_x, text_color=TXT3, anchor="w", wraplength=360, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        entry = ctk.CTkEntry(box, width=360, fg_color=SURF2, border_color=BRD, text_color=TXT, font=self._f_s)
        entry.pack(padx=16, fill="x")
        entry.insert(0, current)
        entry.select_range(0, "end")
        entry.focus_set()
        status = ctk.CTkLabel(box, text="", font=self._f_x, text_color=RED, anchor="w")
        status.pack(anchor="w", padx=16, pady=(6, 0), fill="x")

        def save_and_close(_event=None):
            new_label = entry.get().strip()
            if new_label:
                self.labels[account_id] = new_label
                save_labels(self.labels)
                dialog.destroy()
                self.refresh()
            else:
                status.configure(text="Informe um nome para salvar.")
                entry.focus_set()

        entry.bind("<Return>", save_and_close)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        actions = self._dialog_actions(box)
        actions.pack(fill="x", padx=16, pady=(14, 16), side="bottom")
        self._dialog_button(actions, "Cancelar", dialog.destroy, "secondary", "left")
        self._dialog_button(actions, "Salvar", save_and_close, "primary", "right")

    def _hide_tooltip(self):
        after_id = self._tooltip.get("after_id")
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
            self._tooltip["after_id"] = None
        win = self._tooltip.get("win")
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
            self._tooltip["win"] = None
        self._tooltip["widget"] = None

    def _add_tooltip(self, widget, text):
        def show_now():
            if not widget.winfo_exists() or self._tooltip.get("widget") is not widget:
                return
            win = ctk.CTkToplevel(self)
            win.overrideredirect(True)
            win.transient(self)
            win.configure(fg_color=SURF3)
            ctk.CTkLabel(
                win, text=text, font=self._f_x, text_color=TXT,
                justify="left", wraplength=min(420, max(180, win.winfo_screenwidth() - 48)), padx=12, pady=7,
            ).pack()
            win.update_idletasks()
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            tw = win.winfo_reqwidth()
            th = win.winfo_reqheight()
            root_x = self.winfo_rootx()
            root_y = self.winfo_rooty()
            root_right = root_x + self.winfo_width()
            root_bottom = root_y + self.winfo_height()
            widget_mid = widget.winfo_rootx() + widget.winfo_width() // 2
            left_bound = max(root_x + 8, 0)
            right_bound = min(root_right - 8, sw - 8)
            x = widget_mid - tw // 2
            x = min(max(x, left_bound), max(right_bound - tw, 0))
            below_y = widget.winfo_rooty() + widget.winfo_height() + 4
            above_y = widget.winfo_rooty() - th - 4
            y = above_y if below_y + th > min(root_bottom, sh) and above_y >= root_y else below_y
            y = min(max(y, root_y + 8), max(min(root_bottom, sh) - th - 8, 0))
            win.geometry(f"+{x}+{y}")
            self._tooltip["win"] = win

        def show(_event=None):
            self._hide_tooltip()
            self._tooltip["widget"] = widget
            self._tooltip["after_id"] = self.after(450, show_now)

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", lambda _event=None: self._hide_tooltip(), add="+")
        widget.bind("<ButtonPress>", lambda _event=None: self._hide_tooltip(), add="+")
        widget.bind("<Destroy>", lambda _event=None: self._hide_tooltip(), add="+")

    def _toast(self, text):
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color=SURF2)
        win.attributes("-topmost", True)
        ctk.CTkLabel(
            win, text=text, font=self._f_x, text_color=TXT, justify="left",
            wraplength=min(520, max(180, win.winfo_screenwidth() - 48)), padx=14, pady=10,
        ).pack()
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        tw = min(win.winfo_reqwidth(), 560)
        th = win.winfo_reqheight()
        x = self.winfo_rootx() + (self.winfo_width() - tw) // 2
        y = self.winfo_rooty() + self.winfo_height() - th - 44
        x = min(max(x, 0), max(sw - tw - 8, 0))
        y = min(max(y, 0), max(sh - th - 48, 0))
        win.geometry(f"+{x}+{y}")
        win.after(2600, win.destroy)


def main():
    try:
        app = SessionLinkerApp()
        app.mainloop()
    except Exception as exc:
        _log(f"fatal: {exc}\n{traceback.format_exc()}")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"Erro fatal no Claude Session Linker:\n\n{exc}",
                "Claude Session Linker", 0x10,
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
