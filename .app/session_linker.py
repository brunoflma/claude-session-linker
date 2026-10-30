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
from __future__ import annotations

import json
import os
import ntpath
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
import zlib
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
def _secure_rmtree(path: Path) -> None:
    if path.is_symlink():
        raise OSError(f"Refusing to remove a symlinked directory: {path}")
    # Python's shutil.rmtree uses fd-based safe deletion internally on systems that support it.
    # We still check for symlinks explicitly because rmtree can follow them on older systems.
    shutil.rmtree(path)


def _secure_mkdir(path: Path, parents: bool = False) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise OSError(f"Refusing to use non-directory or symlinked path: {path}")
    path.mkdir(parents=parents, exist_ok=True, mode=0o700)
    if os.name == "posix":
        try:
            # Secure against TOCTOU symlink hijacking: open the directory ensuring it is not a symlink,
            # then chmod via the file descriptor.
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                os.chmod(fd, 0o700)
            finally:
                os.close(fd)
        except Exception as e:
            raise OSError(f"Failed to securely chmod directory {path}: {e}")

LOG_DIR = APP_DIR / "logs"
_secure_mkdir(LOG_DIR, parents=True)
ERR_LOG = LOG_DIR / "session-linker-error.log"
BACKUPS_DIR = APP_DIR / "backups"
_secure_mkdir(BACKUPS_DIR)
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


LOG_MAX_BYTES = 5 * 1024 * 1024


def _log(message):
    """Append one line to the error log, rotating it to `.1` past 5 MB.

    The previous version copied the entire log into a temp file on every
    call (up to 5 MB of I/O per line). Appending keeps it O(1) while staying
    safe against a planted symlink: O_NOFOLLOW where the OS has it, plus an
    identity check (fstat of the open handle vs lstat of the path) that also
    covers Windows, where O_NOFOLLOW does not exist.
    """
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n".encode("utf-8", "replace")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(ERR_LOG, flags, 0o600)
    except OSError:
        return
    rotate = False
    try:
        opened, on_disk = os.fstat(fd), os.lstat(ERR_LOG)
        if stat.S_ISLNK(on_disk.st_mode) or (opened.st_ino, opened.st_dev) != (on_disk.st_ino, on_disk.st_dev):
            return
        os.write(fd, line)
        rotate = opened.st_size + len(line) > LOG_MAX_BYTES
    except OSError:
        return
    finally:
        os.close(fd)
    if rotate:
        try:
            os.replace(ERR_LOG, ERR_LOG.with_name(ERR_LOG.name + ".1"))
        except OSError:
            pass

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("light")
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
# Palette -- dark navigation rail, warm paper workspace, one accent color.
# Every widget passes explicit colors, so the look does not depend on the
# system light/dark setting or on customtkinter's bundled themes.
# ---------------------------------------------------------------------------
# Navigation rail (dark)
RAIL = "#16181C"
RAIL2 = "#1F2228"
RAIL3 = "#2A2E36"
RAIL_LINE = "#30353E"
RAIL_TXT = "#F3EFE8"
RAIL_TXT2 = "#B4AEA4"
RAIL_TXT3 = "#7F8790"
# Workspace (light)
PAPER = "#F5F2EC"
CARD = "#FFFFFF"
CARD_HOVER = "#FBF9F5"
LINE = "#E4DDD1"
LINE2 = "#D4CBBC"
INK = "#1E1F22"
INK2 = "#57534C"
INK3 = "#8A8378"
# Accent and states
ACCENT = "#C15F3C"
ACCENT_H = "#A64F31"
ACCENT_SOFT = "#F8E9E2"
OK = "#2E7D4F"
OK_BG = "#E6F2EA"
OK_LINE = "#A9D2B7"
WARN = "#8A5508"
WARN_BG = "#FCF1DC"
WARN_LINE = "#EBC77F"
DANGER = "#B3362B"
DANGER_H = "#952B22"
DANGER_BG = "#FBE8E5"
DANGER_LINE = "#EDB1A8"
INFO = "#2B5D84"
INFO_BG = "#E5EEF6"
INFO_LINE = "#B3CCE2"
LIVE = "#5FBF7F"
WHITE = "#FFFFFF"
AVATAR_COLORS = ("#C15F3C", "#3E7CB1", "#4E9A6B", "#8A63B8", "#C28A2E", "#3B8F8F", "#B5517D")
TONES = {
    "neutral": (INK2, PAPER, LINE),
    "info": (INFO, INFO_BG, INFO_LINE),
    "ok": (OK, OK_BG, OK_LINE),
    "warn": (WARN, WARN_BG, WARN_LINE),
    "danger": (DANGER, DANGER_BG, DANGER_LINE),
    "accent": (ACCENT, ACCENT_SOFT, "#EBC3B3"),
}
PAGE_SIZE = 40
if sys.platform.startswith("win"):
    UI_FONT, MONO_FONT = "Segoe UI", "Consolas"
elif sys.platform == "darwin":
    UI_FONT, MONO_FONT = "Helvetica Neue", "Menlo"
else:
    UI_FONT, MONO_FONT = "DejaVu Sans", "DejaVu Sans Mono"
WIN_TITLE = "Claude Session Linker"
def _load_app_version() -> str:
    # Single source of truth: .app/VERSION. Every version label (this footer,
    # the setup window badge, the setup.ps1 message) reads from that one file
    # so a release only ever changes one number.
    try:
        version_file = Path(__file__).resolve().parent / "VERSION"
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


APP_VERSION = _load_app_version()
DEV_CREDIT = "Desenvolvido por Bruno Ferreira"

# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------
_PLATFORM = os.environ.get("CLAUDE_SESSION_LINKER_PLATFORM", sys.platform)
APPDATA = Path(os.environ["APPDATA"]) if os.environ.get("APPDATA") else None
LOCALAPPDATA = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else None
CLAUDE_DIR_ENV = "CLAUDE_SESSION_LINKER_CLAUDE_DIR"
MACOS_BASE_ENV = "CLAUDE_SESSION_LINKER_MACOS_BASE"  # test hook for the App Support base


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
    return not path.is_symlink() and path.is_dir() and any(
        not (path / child).is_symlink() and (path / child).exists()
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
            if not probe.is_symlink() and probe.exists():
                mtimes.append(probe.stat(follow_symlinks=False).st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def _macos_app_support(macos_base: Path | None = None) -> Path:
    if macos_base is not None:
        return macos_base
    env_base = os.environ.get(MACOS_BASE_ENV)
    if env_base:
        return Path(env_base).expanduser()
    return Path.home() / "Library" / "Application Support"


def discover_claude_dirs(
    appdata: Path | None = None,
    localappdata: Path | None = None,
    *,
    platform: str = _PLATFORM,
    macos_base: Path | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    if platform.startswith("win"):
        if appdata is not None:
            candidates.append(appdata / "Claude")
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
    elif platform == "darwin":
        base = _macos_app_support(macos_base)
        candidates.append(base / "Claude")
        try:
            candidates.extend(sorted(base.glob("Claude*")))
        except OSError:
            pass
    valid = [path for path in _unique_paths(candidates) if is_claude_data_dir(path)]
    valid.sort(key=claude_dir_activity_time, reverse=True)
    return valid


def resolve_claude_dir(
    appdata: Path | None,
    localappdata: Path | None = None,
    explicit_dir: str | os.PathLike | None = None,
    *,
    platform: str = _PLATFORM,
    macos_base: Path | None = None,
) -> Path:
    return resolve_claude_dirs(
        appdata, localappdata, explicit_dir, platform=platform, macos_base=macos_base
    )[0]


def resolve_claude_dirs(
    appdata: Path | None,
    localappdata: Path | None = None,
    explicit_dir: str | os.PathLike | None = None,
    *,
    platform: str = _PLATFORM,
    macos_base: Path | None = None,
) -> list[Path]:
    if explicit_dir:
        return [Path(explicit_dir).expanduser()]
    candidates = discover_claude_dirs(appdata, localappdata, platform=platform, macos_base=macos_base)
    if candidates:
        return candidates
    if platform.startswith("win") and appdata is not None:
        return [appdata / "Claude"]
    if platform == "darwin":
        return [_macos_app_support(macos_base) / "Claude"]
    raise RuntimeError(f"Unsupported platform: {platform}")


CLAUDE_DIRS = resolve_claude_dirs(APPDATA, LOCALAPPDATA, os.environ.get(CLAUDE_DIR_ENV))
CLAUDE_DIR = CLAUDE_DIRS[0]
SESSIONS_DIR = CLAUDE_DIR / "claude-code-sessions"
COWORK_SESSIONS_DIR = CLAUDE_DIR / "local-agent-mode-sessions"
CONFIG_JSON = CLAUDE_DIR / "config.json"


def load_labels() -> dict:
    if not LABELS_FILE.is_symlink() and LABELS_FILE.is_file():
        try:
            with _secure_open_read(LABELS_FILE, "r", encoding="utf-8") as f:
                if os.fstat(f.fileno()).st_size > 5 * 1024 * 1024:  # Security: 5MB limit
                    return {}
                return json.load(f)
        except Exception:
            return {}
    return {}



def _secure_open_read(path: Path | str, mode: str = "r", encoding: str | None = None):
    if ".." in Path(path).parts:
        raise ValueError("Invalid file path")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= getattr(os, "O_NOFOLLOW")
    fd = os.open(path, flags)
    return os.fdopen(fd, mode, encoding=encoding)


def _secure_write_text(path: Path, content: str) -> None:
    if ".." in path.parts:
        raise Exception("Invalid file path")

    # Write to a secure temporary file first, then atomically replace the target
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # Inherit os.replace's atomic guarantees
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.chmod(tmp_path, 0o600)
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def _secure_move_dir(src: Path, dest: Path) -> None:
    if src.is_symlink() or dest.is_symlink():
        raise OSError("Refusing to move or copy involving a symlinked directory")
    src_stat = src.stat(follow_symlinks=False)
    if not stat.S_ISDIR(src_stat.st_mode):
        raise OSError("Source is not a directory")

    if dest.exists() and src != dest:
        shutil.copytree(
            src, dest,
            symlinks=True, ignore_dangling_symlinks=True, dirs_exist_ok=True,
            copy_function=_secure_copy,
        )
        try:
            if src.stat(follow_symlinks=False).st_ino != src_stat.st_ino or src.is_symlink():
                _secure_rmtree(dest)
                raise OSError("Source directory was hijacked into a symlink during copytree")
        except FileNotFoundError:
            if dest.exists():
                _secure_rmtree(dest)
            raise OSError("Source directory disappeared during copytree")
        _secure_rmtree(src)
    elif src != dest:
        src.rename(dest)
        try:
            if dest.stat(follow_symlinks=False).st_ino != src_stat.st_ino or dest.is_symlink():
                if dest.is_symlink() or not dest.is_dir():
                    dest.unlink()
                else:
                    _secure_rmtree(dest)
                raise OSError("Source directory was hijacked into a symlink before renaming")
        except FileNotFoundError:
            if dest.exists():
                if dest.is_symlink() or not dest.is_dir():
                    dest.unlink()
                else:
                    _secure_rmtree(dest)
            raise OSError("Destination directory disappeared after renaming")

def _secure_copy(src: Path | str, dest: Path | str) -> None:
    src_path = Path(src)
    dest_path = Path(dest)
    if ".." in src_path.parts or ".." in dest_path.parts:
        raise Exception("Invalid file path")
    if src_path.is_symlink() or dest_path.is_symlink():
        raise OSError("Refusing to copy involving a symlink")

    # Write to a secure temporary file first, then atomically replace the target
    fd, tmp_path = tempfile.mkstemp(dir=str(dest_path.parent))
    try:
        with os.fdopen(fd, "wb") as f_dst, _secure_open_read(src_path, "rb") as f_src:
            shutil.copyfileobj(f_src, f_dst)
        shutil.copystat(src_path, tmp_path, follow_symlinks=False)
        # Inherit os.replace's atomic guarantees
        os.replace(tmp_path, dest_path)
    except Exception:
        try:
            os.chmod(tmp_path, 0o600)
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_labels(labels: dict) -> None:
    if LABELS_FILE.is_symlink():
        raise OSError(f"Refusing to overwrite a symlinked labels file: {LABELS_FILE}")
    _secure_write_text(LABELS_FILE, json.dumps(labels, indent=2, ensure_ascii=False))


_LINK_KEY_CACHE = {}

def _link_key(path: Path) -> str:
    # Bolt Optimization: Prevent O(N) disk I/O bottlenecks when calling path.resolve()
    # repeatedly on session files during scanning by globally caching the full resolution
    # of the path. This preserves exact symlink resolution behavior while avoiding disk hits.
    key = str(path)
    if key not in _LINK_KEY_CACHE:
        try:
            _LINK_KEY_CACHE[key] = str(path.resolve())
        except Exception:
            _LINK_KEY_CACHE[key] = key
    return _LINK_KEY_CACHE[key]


def load_link_registry() -> dict:
    if not LINKS_FILE.is_symlink() and LINKS_FILE.is_file():
        try:
            with _secure_open_read(LINKS_FILE, "r", encoding="utf-8") as f:
                if os.fstat(f.fileno()).st_size > 5 * 1024 * 1024:  # Security: 5MB limit
                    return {}
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_link_registry(registry: dict) -> None:
    if LINKS_FILE.is_symlink():
        raise OSError(f"Refusing to overwrite a symlinked links file: {LINKS_FILE}")
    _secure_write_text(LINKS_FILE, json.dumps(registry, indent=2, ensure_ascii=False))


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
        if config_json.is_symlink() or not config_json.is_file():
            continue
        try:
            with _secure_open_read(config_json, "r", encoding="utf-8") as f:
                if os.fstat(f.fileno()).st_size > 5 * 1024 * 1024:  # Security: 5MB limit
                    continue
                data = json.load(f)
            account_uuid = data.get("lastKnownAccountUuid")
            if account_uuid:
                return account_uuid
        except Exception:
            continue
    return None


_NO_WINDOW_FLAGS = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW


def _get_system_executable(name: str, platform: str = _PLATFORM) -> str:
    """Securely resolves the path to a system executable without relying on
    PATH or SystemRoot environment variables, preventing binary planting."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
        raise ValueError(f"Expected a system executable basename: {name}")
    if platform.startswith("win"):
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            length = ctypes.windll.kernel32.GetSystemDirectoryW(buf, 260)
            if length > 0:
                base_dir = buf[:length]
                return ntpath.join(base_dir, name)
        except Exception:
            pass

        return ntpath.join(r"C:\Windows\System32", name)

    for directory in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        candidate = posixpath.join(directory, name)
        if os.path.exists(candidate):
            return candidate

    # Fail closed on systems without the expected binary instead of consulting
    # a user-controlled PATH (the subprocess call will safely fail).
    return posixpath.join("/usr/bin", name)


def is_desktop_running(platform: str = _PLATFORM) -> bool:
    try:
        if platform.startswith("win"):
            tasklist_cmd = _get_system_executable("tasklist.exe", platform)
            out = subprocess.run(
                [tasklist_cmd, "/FI", "IMAGENAME eq Claude.exe"],
                capture_output=True, timeout=5,
                creationflags=_NO_WINDOW_FLAGS,  # avoid a console flash from pythonw.exe
                shell=False,
            )
            # Process names are plain ASCII regardless of console codepage, so a
            # raw byte search sidesteps pt-BR tasklist header decoding issues.
            return b"claude.exe" in out.stdout.lower()
        if platform != "darwin":
            return False
        # macOS: match the Desktop app bundle, NOT the lowercase `claude`
        # Claude Code CLI. pgrep -f is case-sensitive, so the capitalized
        # `Claude.app/.../Claude` pattern excludes the CLI's `claude.app/.../claude`.
        pgrep_cmd = _get_system_executable("pgrep", platform)
        out = subprocess.run(
            [pgrep_cmd, "-f", "Claude[.]app/Contents/MacOS/Claude($|[[:space:]])"],
            capture_output=True, timeout=5,
            shell=False,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        return False


def _scandir_or_empty(path) -> list:
    # A single folder without read permission (or removed mid-scan) used to
    # raise out of the background scan and leave the window stuck loading.
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def _coerce_ms(value) -> int:
    """Desktop stores lastActivityAt as epoch milliseconds, but a hand-edited
    or future index could carry a string or ISO date; anything unusable sorts
    as 0 instead of breaking the whole scan with a TypeError."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else 0
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            return max(int(float(text)), 0)
        except ValueError:
            parsed = parse_iso_ts(text)
            if parsed is not None:
                try:
                    return int(parsed.timestamp() * 1000)
                except (OverflowError, OSError, ValueError):
                    return 0
    return 0


def _coerce_title(value) -> str:
    text = str(value).strip() if value not in (None, "") else ""
    return text or "(sem título)"


ACCOUNT_ID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def scan_account_ids(folder_names=("claude-code-sessions", "local-agent-mode-sessions")) -> set[str]:
    """Accounts that already have at least one workspace folder, even without
    sessions. They are valid link targets: without this, an account that only
    opened the Code/Cowork tab once never appeared as a destination. Only
    UUID-shaped names count, so helper folders such as `skills-plugin` stay out."""
    accounts: set[str] = set()
    for claude_dir in CLAUDE_DIRS:
        for folder_name in folder_names:
            base = claude_dir / folder_name
            if base.is_symlink() or not base.is_dir():
                continue
            for account_entry in _scandir_or_empty(base):
                if (
                    account_entry.name in accounts
                    or not ACCOUNT_ID_RE.match(account_entry.name)
                    or account_entry.is_symlink()
                    or not account_entry.is_dir(follow_symlinks=False)
                ):
                    continue
                if any(
                    not ws.is_symlink() and ws.is_dir(follow_symlinks=False)
                    for ws in _scandir_or_empty(account_entry.path)
                ):
                    accounts.add(account_entry.name)
    return accounts


def _scan_index_tree(folder_name: str, with_data_dir: bool) -> dict:
    """{accountUUID: [session, ...]} for one index tree across every Claude
    root, newest first. Each session is a dict with path, data_dir,
    accountId, claudeDir, sessionsDir, sessionId, cliSessionId, cwd, title,
    lastActivityAt, isArchived, workspaceUUID and the link metadata keys.

    Directory entries come from a single scandir per folder, so companion
    data folders are matched by name without extra stat calls, and the link
    registry is loaded once per scan instead of once per session.
    """
    result: dict[str, list[dict]] = {}
    link_registry = load_link_registry()
    for claude_dir in CLAUDE_DIRS:
        sessions_dir = claude_dir / folder_name
        if sessions_dir.is_symlink() or not sessions_dir.is_dir():
            continue
        for account_entry in _scandir_or_empty(sessions_dir):
            if account_entry.is_symlink() or not account_entry.is_dir(follow_symlinks=False):
                continue
            account_id = account_entry.name
            account_sessions = []
            for workspace_entry in _scandir_or_empty(account_entry.path):
                if workspace_entry.is_symlink() or not workspace_entry.is_dir(follow_symlinks=False):
                    continue
                json_files = []
                data_dir_names = set()
                for file_entry in _scandir_or_empty(workspace_entry.path):
                    if file_entry.is_symlink():
                        continue
                    if file_entry.is_file(follow_symlinks=False):
                        if file_entry.name.startswith("local_") and file_entry.name.endswith(".json"):
                            json_files.append(file_entry)
                    elif with_data_dir and file_entry.is_dir(follow_symlinks=False):
                        data_dir_names.add(file_entry.name)

                workspace_dir = Path(workspace_entry.path)
                for file_entry in json_files:
                    try:
                        with _secure_open_read(file_entry.path, "rb") as f_in:
                            if os.fstat(f_in.fileno()).st_size > 5 * 1024 * 1024:  # Security: 5MB limit
                                continue
                            data = json.load(f_in)
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue

                    f = workspace_dir / file_entry.name
                    link_metadata = link_registry.get(_link_key(f), {}) if link_registry else {}
                    stem = file_entry.name[:-5]
                    account_sessions.append({
                        "path": f,
                        "data_dir": workspace_dir / stem if stem in data_dir_names else None,
                        "accountId": account_id,
                        "claudeDir": claude_dir,
                        "sessionsDir": sessions_dir,
                        "sessionId": data.get("sessionId", stem),
                        "cliSessionId": str(data.get("cliSessionId") or ""),
                        "cwd": str(data.get("cwd") or ""),
                        "title": _coerce_title(data.get("title")),
                        "lastActivityAt": _coerce_ms(data.get("lastActivityAt")),
                        "isArchived": bool(data.get("isArchived", False)),
                        "workspaceUUID": workspace_entry.name,
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


def scan_sessions() -> dict:
    """Code tab sessions. Transcripts live account-agnostic under
    ~/.claude/projects, so data_dir is always None here."""
    return _scan_index_tree("claude-code-sessions", with_data_dir=False)


def scan_cowork_sessions() -> dict:
    """Cowork (Agent Mode) sessions. Each index file (local_<id>.json) sits
    next to a same-stem folder holding audit.jsonl, uploads and outputs --
    Cowork keeps no account-agnostic transcript, so that folder ("data_dir")
    is the conversation itself and travels with the index when linking."""
    return _scan_index_tree("local-agent-mode-sessions", with_data_dir=True)


def backup_dir_tree(dir_path: Path, label: str) -> Path:
    if dir_path.is_symlink():
        raise OSError("Refusing to backup a symlinked directory")
    dir_stat = dir_path.stat(follow_symlinks=False)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Security: sanitize label to prevent path traversal if account/profile name is malicious
    safe_label = re.sub(r"[^A-Za-z0-9\-\s]", "-", label).strip("-")
    zip_path = BACKUPS_DIR / f"{safe_label}-{stamp}.zip"

    # Security: create file securely preventing TOCTOU leaks
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= getattr(os, "O_NOFOLLOW")
    fd = os.open(zip_path, flags, 0o600)
    with os.fdopen(fd, "wb") as f:
        with zipfile.ZipFile(f, "x", zipfile.ZIP_DEFLATED) as zf:
            for target_f in _safe_walk_files(dir_path):
                zf.write(target_f, target_f.relative_to(dir_path.parent))

    try:
        if dir_path.stat(follow_symlinks=False).st_ino != dir_stat.st_ino or dir_path.is_symlink():
            if zip_path.exists():
                zip_path.unlink()
            raise OSError("Directory was hijacked into a symlink during backup")
    except FileNotFoundError:
        if zip_path.exists():
            zip_path.unlink()
        raise OSError("Directory disappeared during backup")

    return zip_path


def backup_sessions_dir(sessions_dir: Path = SESSIONS_DIR) -> Path:
    label = "claude-code-sessions"
    if sessions_dir != SESSIONS_DIR:
        profile = sessions_dir.parent.name.replace(" ", "-")
        label = f"{profile}-claude-code-sessions"
    return backup_dir_tree(sessions_dir, label)


def find_target_workspace_dir(base_dir: Path, account_id: str):
    account_dir = base_dir / account_id
    if account_dir.is_symlink() or not account_dir.exists():
        return None
    # Bolt Optimization: Maintain os.DirEntry objects to use their cached .stat()
    # avoiding redundant O(N) disk I/O syscalls during sorting compared to Path(d.path).stat()
    workspace_dirs = [
        d for d in os.scandir(account_dir)
        if not d.is_symlink() and d.is_dir(follow_symlinks=False)
    ]
    if not workspace_dirs:
        return None
    workspace_dirs.sort(key=lambda d: d.stat(follow_symlinks=False).st_mtime, reverse=True)
    return Path(workspace_dirs[0].path)


def find_target_workspace_dir_in_roots(folder_name: str, account_id: str):
    for claude_dir in CLAUDE_DIRS:
        target_ws = find_target_workspace_dir(claude_dir / folder_name, account_id)
        if target_ws is not None:
            return target_ws
    return None


def ensure_index_linked(src_path: Path, dest_path: Path, source_account_id: str, origin_account_id: str) -> bool:
    if src_path.is_symlink() or dest_path.is_symlink():
        raise OSError("Refusing to copy a symlinked session index")
    copied = not dest_path.exists()
    if copied:
        _secure_copy(src_path, dest_path)
    record_link_metadata(dest_path, source_account_id, origin_account_id)
    return copied


def _new_cli_session_id(transcript_dir: Path) -> str:
    while True:
        cli_session_id = str(uuid.uuid4())
        target = transcript_dir / f"{cli_session_id}.jsonl"
        if not target.is_symlink() and not target.exists():
            return cli_session_id


def _read_index_json(path: Path) -> dict:
    if path.is_symlink():
        raise OSError(f"Refusing to read a symlinked session index: {path}")
    with _secure_open_read(path, "r", encoding="utf-8") as f:
        if os.fstat(f.fileno()).st_size > 5 * 1024 * 1024:  # Security: 5MB limit
            raise OSError(f"Refusing to read an unusually large session index: {path}")
        return json.load(f)


def write_code_index_clone(
    src_path: Path,
    dest_path: Path,
    source_account_id: str,
    origin_account_id: str,
) -> bool:
    if dest_path.is_symlink():
        raise OSError(f"Refusing to overwrite a symlinked session index: {dest_path}")
    source_data = _read_index_json(src_path)
    data = source_data
    source_cli_session_id = source_data.get("cliSessionId") or ""
    dest_cli_session_id = ""
    if not dest_path.is_symlink() and dest_path.exists():
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
        if transcript_path and not transcript_path.is_symlink() and transcript_path.exists():
            cloned_cli_session_id = _new_cli_session_id(transcript_path.parent)
            cloned_transcript_path = transcript_path.with_name(f"{cloned_cli_session_id}.jsonl")
            if cloned_transcript_path.is_symlink():
                raise OSError("Refusing to copy a symlinked transcript")
            _secure_copy(transcript_path, cloned_transcript_path)
            invalidate_transcript_cache()
            data["cliSessionId"] = cloned_cli_session_id

    copied = not dest_path.exists()
    _secure_write_text(dest_path, json.dumps(data, indent=2, ensure_ascii=False))
    record_link_metadata(dest_path, source_account_id, origin_account_id, source_cli_session_id)
    return copied


def copy_index_with_link_metadata(src_path: Path, dest_path: Path, source_account_id: str, origin_account_id: str | None = None) -> None:
    if src_path.is_symlink() or dest_path.is_symlink():
        raise OSError("Refusing to copy a symlinked session index")
    _secure_copy(src_path, dest_path)
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
    if root.is_symlink() or not root.is_dir() or not replacements:
        return
    text_suffixes = {".json", ".jsonl", ".md", ".txt", ".yml", ".yaml", ".toml", ".lock", ""}
    for path in _safe_walk_files(root):
        if path.suffix.lower() not in text_suffixes:
            continue
        try:
            with _secure_open_read(path, "r", encoding="utf-8") as f:
                if os.fstat(f.fileno()).st_size > 25 * 1024 * 1024:  # Security: 25MB limit
                    continue
                text = f.read()
        except Exception:
            continue
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            _secure_write_text(path, updated)


def normalize_cowork_session_copy(
    src_path: Path,
    dest_path: Path,
    src_data_dir: Path | None,
    dest_data_dir: Path | None,
    source_account_id: str,
    origin_account_id: str,
) -> None:
    if dest_path.is_symlink():
        raise OSError(f"Refusing to overwrite a symlinked session index: {dest_path}")
    data = _read_index_json(src_path)
    if dest_data_dir:
        data["cwd"] = str(dest_data_dir / "outputs")
    for key in ("error", "errorAt", "errorCategory", "errorVersion"):
        data.pop(key, None)
    _secure_write_text(dest_path, json.dumps(data, indent=2, ensure_ascii=False))
    record_link_metadata(dest_path, source_account_id, origin_account_id)

    if not src_data_dir or not dest_data_dir or dest_data_dir.is_symlink() or not dest_data_dir.is_dir():
        return

    src_outputs = src_data_dir / "outputs"
    dest_outputs = dest_data_dir / "outputs"
    src_project_name = claude_project_dir_name(src_outputs)
    dest_project_name = claude_project_dir_name(dest_outputs)
    projects_dir = dest_data_dir / ".claude" / "projects"
    old_project = projects_dir / src_project_name
    new_project = projects_dir / dest_project_name
    if old_project.is_symlink() or new_project.is_symlink():
        raise OSError("Refusing to move or copy a symlinked project directory")
    if old_project.exists() and old_project != new_project:
        _secure_move_dir(old_project, new_project)

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


def _safe_walk_files(path: Path):
    if path.is_symlink():
        return
    if path.is_dir():
        try:
            with os.scandir(path) as it:
                for entry in it:
                    child = Path(entry.path)
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        yield from _safe_walk_files(child)
                    elif entry.is_file(follow_symlinks=False):
                        yield child
        except OSError:
            pass
    elif path.is_file():
        yield path


def _is_safe_cowork_data_dir(index_path: Path, data_dir: Path) -> bool:
    try:
        return data_dir.parent.resolve() == index_path.parent.resolve() and data_dir.name == index_path.stem
    except OSError:
        return False


def remove_session_from_account(session: dict, mode: str):
    index_path = Path(session["path"])
    if index_path.is_symlink():
        return False, "Remoção cancelada: o índice da sessão é um symlink."
    if not index_path.exists():
        return False, "Essa sessão já não existe mais nesta conta."

    try:
        if mode == "cowork":
            data_dir = session.get("data_dir")
            data_dir = Path(data_dir) if data_dir else index_path.with_suffix("")
            if data_dir.is_symlink():
                return False, "Remoção cancelada: pasta de dados Cowork é um symlink."
            if data_dir.exists() and not _is_safe_cowork_data_dir(index_path, data_dir):
                return False, "Remoção cancelada: pasta de dados Cowork inesperada."
            backup_path = backup_dir_tree(index_path.parent, "cowork-workspace")
            if not data_dir.is_symlink() and data_dir.is_dir():
                _secure_rmtree(data_dir)
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
    return True, f"{removed}\nBackup salvo em backups/{backup_path.name}."


def link_session_to_account(session: dict, target_account_id: str):
    target_ws = find_target_workspace_dir_in_roots("claude-code-sessions", target_account_id)
    if target_ws is None:
        return False, (
            "Essa conta ainda não tem uma pasta de workspace em "
            "claude-code-sessions. Abra a aba Code pelo menos uma vez "
            "logado nela (qualquer projeto) para criá-la, depois tente de novo."
        )

    dest_path = target_ws / session["path"].name

    if session["path"].is_symlink() or dest_path.is_symlink():
        return False, "Falha ao vincular: arquivo de índice é um symlink."

    try:
        if dest_path.exists():
            backup_path = backup_sessions_dir(target_ws.parent.parent)
            dest_cli_before = ""
            try:
                dest_cli_before = _read_index_json(dest_path).get("cliSessionId") or ""
            except Exception:
                pass
            write_code_index_clone(session["path"], dest_path, session.get("accountId", ""), source_origin_account(session))
            source_cli = session.get("cliSessionId") or ""
            if dest_cli_before and dest_cli_before != source_cli:
                return True, (
                    "Esta conta já tem uma cópia independente desta sessão.\n\n"
                    "Nada foi sobrescrito: a conversa da conta de destino foi preservada e o vínculo "
                    f"de origem foi registrado. Backup salvo em backups/{backup_path.name}."
                )
            return True, (
                "Vínculo atualizado para esta conta.\n\n"
                "A cópia antiga, que compartilhava o mesmo transcript, passou a ter uma conversa "
                f"Code independente. Backup salvo em backups/{backup_path.name}."
            )

        backup_path = backup_sessions_dir(target_ws.parent.parent)
        write_code_index_clone(session["path"], dest_path, session.get("accountId", ""), source_origin_account(session))
    except Exception as e:
        backup_info = f" (backup salvo em {backup_path.name})" if "backup_path" in locals() else ""
        return False, f"Falha ao vincular{backup_info}: {e}"

    return True, (
        f"Vinculado. Backup salvo em backups/{backup_path.name}.\n\n"
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

    if session["path"].is_symlink() or dest_path.is_symlink():
        return False, "Falha ao vincular: arquivo de índice é um symlink."
    if session.get("data_dir") and session["data_dir"].is_symlink():
        return False, "Falha ao copiar: diretório de origem é um symlink."
    if dest_data_dir and dest_data_dir.is_symlink():
        return False, "Falha ao copiar: diretório de destino é um symlink."

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
                f"A sessão já existia aqui; backup salvo em backups/{backup_path.name}. "
                "O Session Linker reparou o caminho interno do Cowork e manteve a origem original visível na lista."
            )
        except Exception as e:
            return False, f"Falha ao atualizar vínculo: {e}"

    # Scoped backup: only the destination workspace folder, not the whole
    # local-agent-mode-sessions tree -- Cowork data (outputs/, uploads/) can
    # run into hundreds of MB, unlike Code's lightweight index-only folders.
    try:
        backup_path = backup_dir_tree(target_ws, "cowork-workspace")
    except Exception as e:
        return False, f"Falha ao criar o backup antes de copiar: {e}"
    try:
        if session.get("data_dir") and not session["data_dir"].is_symlink() and session["data_dir"].is_dir():
            src_stat = session["data_dir"].stat(follow_symlinks=False)
            # ignore_dangling_symlinks: session output folders can contain
            # tool install artifacts (e.g. npm's node_modules/.bin) with
            # symlinks that no longer resolve -- that shouldn't abort an
            # otherwise successful copy of the actual conversation data.
            # dirs_exist_ok: a data folder left behind by an interrupted copy
            # (index missing) is completed instead of failing with
            # FileExistsError; the workspace backup above already holds it.
            shutil.copytree(
                session["data_dir"], dest_data_dir,
                symlinks=True, ignore_dangling_symlinks=True, dirs_exist_ok=True,
                copy_function=_secure_copy,
            )
            try:
                if session["data_dir"].stat(follow_symlinks=False).st_ino != src_stat.st_ino or session["data_dir"].is_symlink():
                    _secure_rmtree(dest_data_dir)
                    raise OSError("Source directory was hijacked into a symlink during copytree")
            except FileNotFoundError:
                if dest_data_dir.exists():
                    _secure_rmtree(dest_data_dir)
                raise OSError("Source directory disappeared during copytree")
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
        f"Vinculado. Backup salvo em backups/{backup_path.name}.\n\n"
        "Feche o Claude Desktop completamente (bandeja do sistema) e abra de "
        "novo, logado na conta de destino, para ver a sessão do Cowork."
    )


def ensure_default_labels(account_ids, labels: dict) -> None:
    """Give every unnamed account its "Conta N" label with one file write
    (calling assign_default_label per account wrote the file N times)."""
    missing = sorted(a for a in account_ids if a not in labels)
    if not missing:
        return
    used = {
        int(v[6:]) for v in labels.values()
        if isinstance(v, str) and v.startswith("Conta ") and v[6:].isdigit()
    }
    n = 1
    for account_id in missing:
        while n in used:
            n += 1
        labels[account_id] = f"Conta {n}"
        used.add(n)
    try:
        save_labels(labels)
    except Exception as exc:
        _log(f"could not persist default labels: {exc}")


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
    try:
        save_labels(labels)
    except Exception as exc:
        # Read-only folder or locked file: keep the label for this run.
        _log(f"could not persist default label: {exc}")
    return label


def fmt_ts(ms: int) -> str:
    if not ms:
        return "--"
    try:
        return datetime.fromtimestamp(ms / 1000).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "--"


def fmt_relative(ms: int, now: datetime | None = None) -> str:
    if not ms:
        return "sem data"
    try:
        then = datetime.fromtimestamp(ms / 1000)
    except Exception:
        return "sem data"
    now = now or datetime.now()
    seconds = (now - then).total_seconds()
    if seconds < 0:
        return then.strftime("%d/%m/%Y")
    if seconds < 60:
        return "agora"
    if seconds < 3600:
        return f"há {int(seconds // 60)} min"
    days = (now.date() - then.date()).days
    if days == 0:
        return f"há {int(seconds // 3600)} h"
    if days == 1:
        return "ontem"
    if days < 7:
        return f"há {days} dias"
    if then.year == now.year:
        return then.strftime("%d/%m")
    return then.strftime("%d/%m/%Y")


def project_name(cwd: str) -> str:
    parts = [part for part in re.split(r"[\\/]+", str(cwd or "")) if part]
    return parts[-1] if parts else ""


def session_matches(session: dict, query: str, account_label: str = "") -> bool:
    query = (query or "").strip().casefold()
    if not query:
        return True
    haystack = " ".join(
        str(session.get(key) or "") for key in ("title", "cwd", "cliSessionId", "sessionId")
    ) + " " + account_label
    return all(term in haystack.casefold() for term in query.split())


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

_TRANSCRIPT_CACHE = None
_TRANSCRIPT_CACHE_TIME = 0.0


def invalidate_transcript_cache() -> None:
    # A freshly cloned transcript must be visible to the very next lookup
    # (e.g. the refresh right after linking), not only after the 2 s TTL.
    global _TRANSCRIPT_CACHE, _TRANSCRIPT_CACHE_TIME
    _TRANSCRIPT_CACHE = None
    _TRANSCRIPT_CACHE_TIME = 0.0


def find_transcript_path(cli_session_id: str):
    """Locate the real `.jsonl` transcript for a cliSessionId, regardless of
    which project-folder hash it lives under -- session ids are UUIDs, so a
    filename match is unambiguous without needing to reproduce Claude
    Code's cwd-to-folder-name hashing scheme."""
    if not cli_session_id or CLAUDE_PROJECTS_DIR.is_symlink() or not CLAUDE_PROJECTS_DIR.exists():
        return None
    # Security: Ensure cli_session_id is just a UUID/alphanumeric to prevent
    # path traversal or glob injection if a local_*.json was modified maliciously.
    if not re.match(r"^[A-Za-z0-9\-]+$", cli_session_id):
        return None
    # Bolt Optimization: Cache the glob results for a short period to prevent
    # O(N) disk I/O scans when querying the status of many sessions in a loop.
    # Prevent O(N) Path object instantiations by using direct os.scandir for
    # the known, shallow project directory structure (~/.claude/projects/<hash>/<uuid>.jsonl).
    global _TRANSCRIPT_CACHE, _TRANSCRIPT_CACHE_TIME
    now = time.time()
    if _TRANSCRIPT_CACHE is None or now - _TRANSCRIPT_CACHE_TIME > 2.0:
        _TRANSCRIPT_CACHE = {}
        if not CLAUDE_PROJECTS_DIR.is_symlink() and CLAUDE_PROJECTS_DIR.is_dir():
            try:
                with os.scandir(CLAUDE_PROJECTS_DIR) as root_it:
                    for proj_dir in root_it:
                        if proj_dir.is_symlink() or not proj_dir.is_dir(follow_symlinks=False):
                            continue
                        try:
                            with os.scandir(proj_dir.path) as proj_it:
                                for f in proj_it:
                                    if f.name.endswith(".jsonl") and not f.is_symlink() and f.is_file(follow_symlinks=False):
                                        _TRANSCRIPT_CACHE[f.name[:-6]] = Path(f.path)
                        except OSError:
                            pass
            except OSError:
                pass
        _TRANSCRIPT_CACHE_TIME = now

    return _TRANSCRIPT_CACHE.get(cli_session_id)


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
        if not data_dir or data_dir.is_symlink() or not data_dir.is_dir():
            return {"found": False}
        path = data_dir / "audit.jsonl"
        ts_key = "_audit_timestamp"
    else:
        path = find_transcript_path(session["cliSessionId"])
        ts_key = "timestamp"

    if path is None or path.is_symlink() or not path.is_file():
        return {"found": False}

    message_count = 0
    last_ts_raw = None
    try:
        # Security: limit processing of unbounded transcript lines to prevent DoS (OOM/CPU exhaustion)
        with _secure_open_read(path, "r", encoding="utf-8") as f:
            if os.fstat(f.fileno()).st_size > 50 * 1024 * 1024:  # Security: 50MB limit to prevent DoS (OOM)
                return {"found": False}
            for line in f:
                # Security: prevent OOM/CPU exhaustion by ignoring unusually long lines (e.g. minified/malicious data)
                if len(line) > 1024 * 1024:  # 1MB limit
                    continue

                # Bolt Optimization: Fast-path substring check to prevent O(N) CPU bottleneck
                # from full JSON parsing on irrelevant lines in large transcripts.
                has_type = '"user"' in line or '"assistant"' in line
                has_ts = ts_key in line
                if not has_type and not has_ts:
                    continue

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
        "mtime": path.stat(follow_symlinks=False).st_mtime,
    }


def conversation_file_available(session: dict, mode: str | None = None) -> bool:
    if mode is None:
        return True
    if mode == "cowork":
        data_dir = session.get("data_dir")
        return bool(data_dir and not data_dir.is_symlink() and data_dir.is_dir() and not (data_dir / "audit.jsonl").is_symlink() and (data_dir / "audit.jsonl").exists())
    return find_transcript_path(session.get("cliSessionId", "")) is not None


_IDENTITY_RESOLVE_CACHE = {}


def conversation_file_identity(session: dict, mode: str | None = None):
    if mode == "cowork":
        data_dir = session.get("data_dir")
        if not data_dir:
            return None
        data_dir_path = Path(data_dir)
        if data_dir_path.is_symlink() or not data_dir_path.is_dir():
            return None
        path = data_dir_path / "audit.jsonl"
    elif mode == "code":
        path = find_transcript_path(session.get("cliSessionId", ""))
    else:
        return None
    if path is None or path.is_symlink() or not path.exists():
        return None

    # Bolt Optimization: Prevent O(N) disk I/O bottlenecks when verifying
    # sessions_are_comparable in loops (e.g. build_compare_candidates) by
    # globally caching the path resolution. This avoids strict symlink
    # resolution syscalls for every path segment on repeated checks.
    key = str(path)
    if key not in _IDENTITY_RESOLVE_CACHE:
        try:
            _IDENTITY_RESOLVE_CACHE[key] = path.resolve()
        except OSError:
            _IDENTITY_RESOLVE_CACHE[key] = path

    return _IDENTITY_RESOLVE_CACHE[key]


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
            by_cwd.setdefault(cwd, []).append((account_id, s))

    duplicates = {}
    for cwd, entries in by_cwd.items():
        if len(entries) < 2:
            continue
        accounts_involved = {a for a, _ in entries}
        if len(accounts_involved) < 2:
            continue
        cli_ids_involved = {s.get("cliSessionId") for _, s in entries if s.get("cliSessionId")}
        if len(cli_ids_involved) < 2:
            continue

        # Bolt Optimization: Delay expensive disk I/O validation checks until we've
        # confirmed multiple independent sessions actually share this cwd.
        valid_entries = []
        for account_id, s in entries:
            if conversation_file_available(s, mode):
                valid_entries.append((account_id, s))

        if len(valid_entries) < 2:
            continue
        valid_accounts = {a for a, _ in valid_entries}
        valid_cli_ids = {s.get("cliSessionId") for _, s in valid_entries if s.get("cliSessionId")}

        if len(valid_accounts) >= 2 and len(valid_cli_ids) >= 2:
            duplicates[cwd] = valid_entries
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

def open_folder(path: Path, platform: str = _PLATFORM) -> None:
    if path.is_symlink() or not path.is_dir():
        raise OSError(f"Pasta indisponível: {path}")
    if platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif platform == "darwin":
        subprocess.run([_get_system_executable("open", platform), str(path)], check=False, timeout=10, shell=False)
    else:
        raise OSError("Abrir pastas só é suportado no Windows e no macOS.")


def avatar_color(account_id: str | None) -> str:
    if not account_id:
        return RAIL3
    return AVATAR_COLORS[zlib.crc32(account_id.encode("utf-8")) % len(AVATAR_COLORS)]


def avatar_initial(label: str) -> str:
    # Up to two initials: "Bruno Ferreira" -> "BF", default "Conta 2" -> "C2".
    words = [w for w in re.split(r"[^\w]+", str(label or "")) if w]
    if not words:
        return "?"
    return "".join(word[0] for word in words[:2]).upper()


class StatusBox(ctk.CTkFrame):
    """Inline message inside a dialog; hidden until the first show()."""

    def __init__(self, parent, font, wraplength=500, **pack_opts):
        super().__init__(parent, fg_color=PAPER, corner_radius=8, border_width=1, border_color=LINE)
        self._pack_opts = pack_opts
        self._label = ctk.CTkLabel(self, text="", font=font, text_color=INK2, anchor="w", justify="left", wraplength=wraplength)
        self._label.pack(anchor="w", fill="x", padx=12, pady=10)
        self._visible = False

    def show(self, text, tone="neutral"):
        fg, bg, line = TONES.get(tone, TONES["neutral"])
        self.configure(fg_color=bg, border_color=line)
        self._label.configure(text=text, text_color=fg)
        if not self._visible:
            self.pack(**self._pack_opts)
            self._visible = True

    def hide(self):
        if self._visible:
            self.pack_forget()
            self._visible = False


class SessionLinkerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title(WIN_TITLE)
        self.configure(fg_color=PAPER)
        self.resizable(True, True)
        self._icon_photos = []
        self._brand_image = None
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
        try:
            if ICON_PNG.exists():
                from PIL import Image as _PILImage
                self._brand_image = ctk.CTkImage(_PILImage.open(str(ICON_PNG)).convert("RGBA"), size=(34, 34))
        except Exception:
            self._brand_image = None

        self.labels = load_labels()
        self.sessions_by_account: dict[str, list[dict]] = {}
        self.known_accounts: set[str] = set()
        self.duplicates: dict = {}
        self.link_groups: dict[str, list[tuple[str, dict]]] = {}
        self.session_mode = "code"  # "code" | "cowork"
        self.selected_account = None  # None = "all accounts"
        self.active_account = None
        self.desktop_running = False
        self.search_query = ""
        self.visible_limit = PAGE_SIZE
        self._load_error = None
        self._loaded = False
        self._refreshing = False
        self._search_after = None
        self._resize_after = None
        self._tooltip = {"win": None, "after_id": None, "widget": None}
        self._refresh_generation = 0
        self.bind("<Leave>", lambda _event=None: self._hide_tooltip(), add="+")
        self.bind("<Configure>", lambda _event=None: self._hide_tooltip(), add="+")
        self.bind("<MouseWheel>", lambda _event=None: self._hide_tooltip(), add="+")

        self._compact_layout = self.winfo_screenwidth() < 1100 or self.winfo_screenheight() < 700
        self._build()
        self._bind_shortcuts()
        self._render_loading()
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_w = min(1180, max(640, screen_w - 48))
        target_h = min(780, max(480, screen_h - 72))
        self.geometry(f"{target_w}x{target_h}")
        self.minsize(min(760, target_w), min(500, target_h))
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
        self._f_hero = ctk.CTkFont(family=UI_FONT, size=22, weight="bold")
        self._f_h = ctk.CTkFont(family=UI_FONT, size=15, weight="bold")
        self._f_b = ctk.CTkFont(family=UI_FONT, size=13, weight="bold")
        self._f_s = ctk.CTkFont(family=UI_FONT, size=13)
        self._f_x = ctk.CTkFont(family=UI_FONT, size=12)
        self._f_xs = ctk.CTkFont(family=UI_FONT, size=11)
        self._f_label = ctk.CTkFont(family=UI_FONT, size=10, weight="bold")
        self._f_big = ctk.CTkFont(family=UI_FONT, size=28, weight="bold")
        self._f_mono = ctk.CTkFont(family=MONO_FONT, size=11)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # --- Navigation rail (dark) -----------------------------------
        rail_w = 248 if self._compact_layout else 280
        rail = ctk.CTkFrame(self, fg_color=RAIL, corner_radius=0, width=rail_w)
        rail.grid(row=0, column=0, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(3, weight=1)

        brand = ctk.CTkFrame(rail, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 18))
        if self._brand_image is not None:
            ctk.CTkLabel(brand, text="", image=self._brand_image, width=34).pack(side="left", padx=(0, 10))
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", fill="x")
        ctk.CTkLabel(brand_text, text="Session Linker", font=self._f_h, text_color=RAIL_TXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            brand_text, text="Sessões entre contas do Claude", font=self._f_xs,
            text_color=RAIL_TXT3, anchor="w",
        ).pack(anchor="w")

        mode_box = ctk.CTkFrame(rail, fg_color="transparent")
        mode_box.grid(row=1, column=0, sticky="ew", padx=20)
        ctk.CTkLabel(mode_box, text="TIPO DE SESSÃO", font=self._f_label, text_color=RAIL_TXT3, anchor="w").pack(anchor="w", pady=(0, 6))
        self._mode_switch = ctk.CTkSegmentedButton(
            mode_box, values=["Code", "Cowork"], command=self._on_mode_switch,
            height=34, corner_radius=8, font=self._f_b,
            fg_color=RAIL2, selected_color=ACCENT, selected_hover_color=ACCENT_H,
            unselected_color=RAIL2, unselected_hover_color=RAIL3,
            text_color=RAIL_TXT, text_color_disabled=RAIL_TXT3,
        )
        self._mode_switch.set("Code")
        self._mode_switch.pack(fill="x")

        accounts_head = ctk.CTkFrame(rail, fg_color="transparent")
        accounts_head.grid(row=2, column=0, sticky="ew", padx=20, pady=(24, 6))
        ctk.CTkLabel(accounts_head, text="CONTAS", font=self._f_label, text_color=RAIL_TXT3).pack(side="left")
        self._accounts_count = ctk.CTkLabel(accounts_head, text="", font=self._f_xs, text_color=RAIL_TXT3)
        self._accounts_count.pack(side="right")

        self._accounts_list = ctk.CTkScrollableFrame(
            rail, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=RAIL2, scrollbar_button_hover_color=RAIL3,
        )
        self._accounts_list.grid(row=3, column=0, sticky="nsew", padx=(12, 6))

        rail_bottom = ctk.CTkFrame(rail, fg_color="transparent")
        rail_bottom.grid(row=4, column=0, sticky="ew", padx=20, pady=(10, 18))
        self._refresh_btn = self._button(rail_bottom, "↻  Atualizar lista", self.refresh, "rail", height=34)
        self._refresh_btn.pack(fill="x")
        self._add_tooltip(self._refresh_btn, "Lê de novo as sessões locais (F5).")
        backups_btn = self._button(rail_bottom, "Abrir pasta de backups", self._open_backups, "rail-ghost", height=30)
        backups_btn.pack(fill="x", pady=(6, 0))
        self._add_tooltip(backups_btn, "Cada vínculo ou remoção cria um backup ZIP nesta pasta antes de alterar arquivos.")
        ctk.CTkLabel(
            rail_bottom, text=f"Versão {APP_VERSION}\n{DEV_CREDIT}", font=self._f_xs,
            text_color=RAIL_TXT3, anchor="w", justify="left",
        ).pack(anchor="w", pady=(12, 0))

        # --- Workspace (light) -----------------------------------------
        main = ctk.CTkFrame(self, fg_color=PAPER, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 0))
        self._filter_title = ctk.CTkLabel(header, text="Todas as sessões", font=self._f_hero, text_color=INK, anchor="w")
        self._filter_title.pack(anchor="w")
        self._filter_subtitle = ctk.CTkLabel(header, text="", font=self._f_s, text_color=INK2, anchor="w")
        self._filter_subtitle.pack(anchor="w", pady=(2, 0))

        toolbar = ctk.CTkFrame(main, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=28, pady=(16, 0))
        toolbar.grid_columnconfigure(0, weight=1)
        search_box = ctk.CTkFrame(toolbar, fg_color=CARD, corner_radius=8, border_width=1, border_color=LINE2)
        search_box.grid(row=0, column=0, sticky="ew")
        search_box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(search_box, text="⌕", font=self._f_h, text_color=INK3, width=20).grid(row=0, column=0, padx=(12, 0))
        # No textvariable: CTkEntry hides its placeholder when one is bound.
        self._search_entry = ctk.CTkEntry(
            search_box, height=36, border_width=0,
            fg_color=CARD, text_color=INK, font=self._f_s,
            placeholder_text="Buscar por título, pasta do projeto, conta ou ID", placeholder_text_color=INK3,
        )
        self._search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 4), pady=2)
        self._search_clear = ctk.CTkButton(
            search_box, text="✕", width=28, height=28, corner_radius=6, cursor="hand2",
            fg_color="transparent", hover_color=PAPER, text_color=INK3, font=self._f_x,
            command=self._clear_search,
        )
        self._search_entry.bind("<KeyRelease>", lambda _e: self._on_search_changed(), add="+")

        self._archived_var = ctk.BooleanVar(value=True)
        archived = ctk.CTkCheckBox(
            toolbar, text="Incluir arquivadas", variable=self._archived_var, command=self._on_filter_changed,
            font=self._f_x, text_color=INK2, checkbox_width=18, checkbox_height=18, corner_radius=5,
            border_width=2, border_color=LINE2, fg_color=ACCENT, hover_color=ACCENT_H, checkmark_color=WHITE,
            cursor="hand2",
        )
        archived.grid(row=0, column=1, padx=(16, 0))

        self._banner = ctk.CTkFrame(main, fg_color=WARN_BG, corner_radius=8, border_width=1, border_color=WARN_LINE)
        self._banner.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self._banner,
            text="O Claude Desktop está aberto. Feche-o completamente (também pela bandeja ou pelo menu) "
                 "antes de vincular ou remover sessões; reabra-o depois para ver as mudanças.",
            font=self._f_x, text_color=WARN, anchor="w", justify="left", wraplength=620,
        ).grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=10)
        self._button(self._banner, "Verificar de novo", self.refresh, "warn", height=30).grid(row=0, column=1, padx=(0, 10), pady=8)

        self._scroll = ctk.CTkScrollableFrame(
            main, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=LINE2, scrollbar_button_hover_color=INK3,
        )
        self._scroll.grid(row=3, column=0, sticky="nsew", padx=(22, 8), pady=(14, 12))
        self._scroll.grid_columnconfigure(0, weight=1)
        self._scroll.bind("<Configure>", self._on_list_resized, add="+")

    def _bind_shortcuts(self):
        self.bind("<F5>", lambda _e: self.refresh())
        self.bind("<Control-f>", lambda _e: self._focus_search())
        self.bind("<Command-f>", lambda _e: self._focus_search())
        self._search_entry.bind("<Escape>", lambda _e: self._clear_search())

    def _focus_search(self):
        self._search_entry.focus_set()
        return "break"

    # -- generic widgets ----------------------------------------------------

    def _button(self, parent, text, command, kind="secondary", width=0, height=34):
        styles = {
            "primary": dict(fg_color=ACCENT, hover_color=ACCENT_H, text_color=WHITE, border_width=0),
            "secondary": dict(fg_color=CARD, hover_color=PAPER, text_color=INK, border_width=1, border_color=LINE2),
            "danger": dict(fg_color=DANGER, hover_color=DANGER_H, text_color=WHITE, border_width=0),
            "danger-ghost": dict(fg_color="transparent", hover_color=DANGER_BG, text_color=DANGER, border_width=0),
            "warn": dict(fg_color=WARN_BG, hover_color=WARN_LINE, text_color=WARN, border_width=1, border_color=WARN_LINE),
            "rail": dict(fg_color=RAIL2, hover_color=RAIL3, text_color=RAIL_TXT, border_width=1, border_color=RAIL_LINE),
            "rail-ghost": dict(fg_color="transparent", hover_color=RAIL2, text_color=RAIL_TXT2, border_width=0),
        }
        btn = ctk.CTkButton(
            parent, text=text, command=command, width=width, height=height, corner_radius=8,
            font=self._f_b if kind in ("primary", "danger") else self._f_x, cursor="hand2",
            **styles[kind],
        )
        return btn

    def _chip(self, parent, text, tone="neutral"):
        fg, bg, _line = TONES.get(tone, TONES["neutral"])
        return ctk.CTkLabel(
            parent, text=text, font=self._f_xs, text_color=fg, fg_color=bg,
            corner_radius=6, height=22, padx=8,
        )

    def _make_dialog(self, title, w, h):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.configure(fg_color=PAPER)
        dialog.resizable(True, True)
        dialog.transient(self)
        self._center_toplevel(dialog, w, h)
        self._grab(dialog)
        if ICON_PATH.exists() and sys.platform.startswith("win"):
            try:
                dialog.after(150, lambda: dialog.iconbitmap(str(ICON_PATH)))
            except Exception:
                pass
        box = ctk.CTkFrame(dialog, fg_color=CARD, corner_radius=12, border_width=1, border_color=LINE)
        box.pack(fill="both", expand=True, padx=14, pady=14)
        box.wrap = max(260, w - 110)  # text width inside the 22 px dialog gutters
        return dialog, box

    def _grab(self, dialog, attempt=0):
        # grab_set fails on a Toplevel that is not mapped yet on some window
        # managers; retry briefly instead of leaving the dialog non-modal.
        try:
            if dialog.winfo_exists():
                dialog.grab_set()
        except Exception:
            if attempt < 10:
                dialog.after(50, lambda: self._grab(dialog, attempt + 1))

    def _dialog_header(self, box, title, subtitle=None):
        ctk.CTkLabel(box, text=title, font=self._f_h, text_color=INK, anchor="w", justify="left", wraplength=box.wrap).pack(anchor="w", padx=22, pady=(20, 2))
        if subtitle:
            ctk.CTkLabel(box, text=subtitle, font=self._f_x, text_color=INK2, anchor="w", justify="left", wraplength=box.wrap).pack(anchor="w", padx=22)

    def _dialog_actions(self, box):
        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=22, pady=(8, 20))
        return actions

    def _center_toplevel(self, dialog, w, h):
        self.update_idletasks()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        w = min(w, max(360, sw - 48))
        h = min(h, max(300, sh - 72))
        dialog.minsize(min(380, w), min(300, h))
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        x = min(max(x, 0), max(sw - w - 8, 0))
        y = min(max(y, 0), max(sh - h - 48, 0))
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _run_background(self, work, done):
        """Run blocking file I/O off the UI thread. Any exception is logged
        and handed to `done`, so a failure can never leave a dialog stuck on
        "Aguarde..." or the list stuck on "Carregando"."""
        def runner():
            try:
                result, error = work(), None
            except Exception as exc:
                _log(f"background task failed: {exc}\n{traceback.format_exc()}")
                result, error = None, exc
            try:
                self.after(0, lambda: done(result, error))
            except Exception:
                pass  # window already closed

        threading.Thread(target=runner, daemon=True).start()

    @staticmethod
    def _bind_click(widgets, callback):
        for widget in widgets:
            widget.bind("<Button-1>", lambda _e: callback(), add="+")

    @staticmethod
    def _bind_hover(container, widgets, on_enter, on_leave):
        def leave(_e=None):
            try:
                x, y = container.winfo_pointerxy()
                hovered = container.winfo_containing(x, y)
            except Exception:
                hovered = None
            if hovered is None or not str(hovered).startswith(str(container)):
                on_leave()

        for widget in widgets:
            widget.bind("<Enter>", lambda _e: on_enter(), add="+")
            widget.bind("<Leave>", leave, add="+")

    @staticmethod
    def _clip(text, limit):
        text = str(text or "")
        return text if len(text) <= limit else f"{text[: max(limit - 1, 0)]}…"

    # -- data / rendering -------------------------------------------------

    def refresh(self):
        # File scanning + the tasklist check both do blocking I/O; run them
        # off the UI thread so the window stays responsive while loading.
        mode = self.session_mode
        self._refresh_generation += 1
        generation = self._refresh_generation
        self._set_refreshing(True)

        def work():
            return {
                "active": get_active_account_uuid(),
                "sessions": scan_cowork_sessions() if mode == "cowork" else scan_sessions(),
                "accounts": scan_account_ids(),
                "running": is_desktop_running(),
            }

        self._run_background(work, lambda result, error: self._apply_refresh(generation, mode, result, error))

    def _set_refreshing(self, busy):
        self._refreshing = busy
        self._refresh_btn.configure(text="Atualizando…" if busy else "↻  Atualizar lista", state="disabled" if busy else "normal")
        self._mode_switch.configure(state="disabled" if busy else "normal")

    def _apply_refresh(self, generation, mode, result, error):
        if generation != self._refresh_generation:
            return  # a newer refresh is in flight and will re-enable the controls
        self._set_refreshing(False)
        if mode != self.session_mode:
            return
        self._loaded = True
        if error is not None:
            self._load_error = error
            self._render_accounts()
            self._render_error(error)
            return
        self._load_error = None
        self.active_account = result["active"]
        self.sessions_by_account = result["sessions"]
        self.known_accounts = set(result["accounts"]) | set(result["sessions"])
        ensure_default_labels(self.known_accounts, self.labels)
        self.desktop_running = result["running"]
        self.duplicates = find_possible_duplicates(self.sessions_by_account, mode)
        self.link_groups = find_linked_session_groups(self.sessions_by_account)
        if self.selected_account is not None and self.selected_account not in self.known_accounts:
            self.selected_account = None
        if self.desktop_running:
            self._banner.grid(row=2, column=0, sticky="ew", padx=28, pady=(14, 0))
        else:
            self._banner.grid_forget()
        self._render_accounts()
        self._render_sessions()

    def _render_loading(self):
        for w in self._accounts_list.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self._accounts_list, text="Carregando contas…", font=self._f_x,
            text_color=RAIL_TXT3, anchor="w",
        ).pack(anchor="w", padx=8, pady=(4, 0), fill="x")
        self._filter_subtitle.configure(text="Lendo sessões locais…")
        for w in self._scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._scroll, text="Carregando sessões…", font=self._f_s, text_color=INK2, anchor="w").pack(anchor="w", padx=6, pady=20)

    def _render_error(self, error):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._filter_subtitle.configure(text="Não foi possível ler as sessões locais.")
        box = ctk.CTkFrame(self._scroll, fg_color=DANGER_BG, corner_radius=10, border_width=1, border_color=DANGER_LINE)
        box.pack(fill="x", padx=6, pady=(4, 0))
        ctk.CTkLabel(box, text="Falha ao carregar", font=self._f_b, text_color=DANGER, anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            box, text=f"{error}\n\nDetalhes técnicos foram gravados em .app/logs.", font=self._f_x,
            text_color=INK2, anchor="w", justify="left", wraplength=640,
        ).pack(anchor="w", padx=16)
        self._button(box, "Tentar novamente", self.refresh, "secondary").pack(anchor="w", padx=16, pady=(10, 14))

    def _on_mode_switch(self, value):
        mode = "cowork" if value == "Cowork" else "code"
        if mode == self.session_mode:
            return
        self.session_mode = mode
        self.selected_account = None
        self.visible_limit = PAGE_SIZE
        self._render_loading()
        self.refresh()

    def _set_mode(self, mode):
        self._mode_switch.set("Cowork" if mode == "cowork" else "Code")
        self._on_mode_switch("Cowork" if mode == "cowork" else "Code")

    def _on_search_changed(self):
        if self._search_entry.get():
            self._search_clear.grid(row=0, column=2, padx=(0, 6))
        else:
            self._search_clear.grid_forget()
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.after(180, self._apply_search)

    def _apply_search(self):
        self._search_after = None
        query = self._search_entry.get().strip()
        if query != self.search_query:
            self.search_query = query
            self.visible_limit = PAGE_SIZE
            if self._loaded and self._load_error is None:
                self._render_sessions()

    def _clear_search(self):
        if self._search_entry.get():
            self._search_entry.delete(0, "end")
            self._on_search_changed()
        self.focus_set()  # lets CTkEntry show its placeholder again
        return "break"

    def _on_filter_changed(self):
        self.visible_limit = PAGE_SIZE
        if self._loaded and self._load_error is None:
            self._render_sessions()

    def _open_backups(self):
        try:
            open_folder(BACKUPS_DIR)
        except Exception as exc:
            self._toast(f"Não foi possível abrir a pasta de backups: {exc}")

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

    def _sorted_accounts(self):
        return sorted(self.known_accounts, key=lambda a: (a != self.active_account, self._account_label(a).casefold()))

    def _link_badges(self, account_id, session):
        origin = session.get("originAccount")
        linked_from = session.get("linkedFromAccount")
        badges = []
        if origin and origin != account_id:
            badges.append((f"Origem: {self._account_label(origin)}", "origin"))
        if linked_from and linked_from != account_id and linked_from != origin:
            badges.append((f"Veio de: {self._account_label(linked_from)}", "link"))
        if origin or linked_from:
            return badges

        entries = self.link_groups.get(session.get("cliSessionId"), [])
        other_accounts = sorted({a for a, _ in entries if a != account_id})
        if other_accounts:
            names = ", ".join(self._account_label(a) for a in other_accounts[:3])
            if len(other_accounts) > 3:
                names += f" +{len(other_accounts) - 3}"
            return [(f"Também em: {names}", "link")]
        return []

    def _render_accounts(self):
        self._hide_tooltip()
        for w in self._accounts_list.winfo_children():
            w.destroy()
        accounts = self._sorted_accounts()
        self._accounts_count.configure(text=str(len(accounts)) if accounts else "")
        total = sum(len(v) for v in self.sessions_by_account.values())
        self._account_row(None, "Todas as contas", self._plural_sessions(total), self.selected_account is None)
        for account_id in accounts:
            n = len(self.sessions_by_account.get(account_id, []))
            meta = self._plural_sessions(n)
            if account_id == self.active_account:
                meta = f"● ativa  ·  {meta}"
            self._account_row(account_id, self._account_label(account_id), meta, account_id == self.selected_account)
        if not accounts and self._loaded:
            ctk.CTkLabel(
                self._accounts_list, text="Nenhuma conta encontrada. Abra o Claude Desktop e use a aba Code ou Cowork em cada conta.",
                font=self._f_xs, text_color=RAIL_TXT3, anchor="w", justify="left", wraplength=210,
            ).pack(anchor="w", padx=8, pady=(8, 0))

    def _account_row(self, account_id, label, meta, selected):
        idle_bg = RAIL3 if selected else RAIL
        row = ctk.CTkFrame(self._accounts_list, fg_color=idle_bg, corner_radius=8, cursor="hand2")
        row.pack(fill="x", pady=(0, 2))
        row.grid_columnconfigure(1, weight=1)
        avatar = ctk.CTkLabel(
            row, text="≡" if account_id is None else avatar_initial(label), width=34, height=34, corner_radius=9,
            fg_color=avatar_color(account_id) if account_id else RAIL2, text_color=WHITE, font=self._f_b, cursor="hand2",
        )
        avatar.grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=9)
        name = ctk.CTkLabel(row, text=self._clip(label, 26), font=self._f_b, text_color=RAIL_TXT, anchor="w", cursor="hand2")
        name.grid(row=0, column=1, sticky="sw", pady=(8, 0))
        is_active = account_id is not None and account_id == self.active_account
        meta_label = ctk.CTkLabel(
            row, text=meta, font=self._f_xs, text_color=LIVE if is_active else RAIL_TXT3, anchor="w", cursor="hand2",
        )
        meta_label.grid(row=1, column=1, sticky="nw", pady=(0, 8))
        widgets = [row, avatar, name, meta_label]
        self._bind_click(widgets, lambda a=account_id: self._select_account(a))
        if not selected:
            self._bind_hover(row, widgets, lambda: row.configure(fg_color=RAIL2), lambda: row.configure(fg_color=idle_bg))
        if account_id is not None:
            edit_btn = ctk.CTkButton(
                row, text="✎", width=28, height=28, corner_radius=6, cursor="hand2",
                fg_color="transparent", hover_color=RAIL_LINE, text_color=RAIL_TXT3, font=self._f_x,
                command=lambda a=account_id: self._rename_account(a),
            )
            edit_btn.grid(row=0, column=2, rowspan=2, padx=(4, 8))
            self._add_tooltip(edit_btn, "Renomear esta conta no Session Linker")
            if label != self._clip(label, 26):
                self._add_tooltip(name, label)

    def _select_account(self, account_id):
        if account_id == self.selected_account:
            return
        self.selected_account = account_id
        self.visible_limit = PAGE_SIZE
        self._render_accounts()
        self._render_sessions()

    def _filtered_items(self):
        if self.selected_account is None:
            items = [(a, s) for a, sessions in self.sessions_by_account.items() for s in sessions]
        else:
            items = [(self.selected_account, s) for s in self.sessions_by_account.get(self.selected_account, [])]
        if not self._archived_var.get():
            items = [(a, s) for a, s in items if not s.get("isArchived")]
        if self.search_query:
            items = [(a, s) for a, s in items if session_matches(s, self.search_query, self._account_label(a))]
        items.sort(key=lambda t: t[1].get("lastActivityAt", 0), reverse=True)
        return items

    def _render_sessions(self, keep_scroll=False):
        self._hide_tooltip()
        for w in self._scroll.winfo_children():
            w.destroy()
        if not keep_scroll:
            try:
                self._scroll._parent_canvas.yview_moveto(0)
            except Exception:
                pass

        mode_name = "Cowork" if self.session_mode == "cowork" else "Code"
        if self.selected_account is None:
            self._filter_title.configure(text=f"Sessões do {mode_name}")
        else:
            self._filter_title.configure(text=self._account_label(self.selected_account))

        items = self._filtered_items()
        bits = [self._plural_sessions(len(items))]
        if self.selected_account is not None:
            bits.append(mode_name)
            if self.selected_account == self.active_account:
                bits.append("conta ativa no Claude Desktop")
        else:
            accounts_with_sessions = {a for a, _ in items}
            bits.append(f"{len(accounts_with_sessions)} conta" + ("" if len(accounts_with_sessions) == 1 else "s"))
        if self.search_query:
            bits.append(f"busca: “{self._clip(self.search_query, 40)}”")
        self._filter_subtitle.configure(text="  ·  ".join(bits))

        if not items:
            self._render_empty(mode_name)
            return

        self._title_wrap = self._wrap_for_width(self._scroll.winfo_width())
        for account_id, session in items[: self.visible_limit]:
            self._build_session_card(account_id, session)
        remaining = len(items) - self.visible_limit
        if remaining > 0:
            self._button(
                self._scroll, f"Mostrar mais {min(remaining, PAGE_SIZE)} de {remaining} restantes",
                self._show_more, "secondary", height=36,
            ).pack(fill="x", padx=6, pady=(4, 12))

    def _wrap_for_width(self, width):
        return max(260, width - (80 if self._compact_layout else 400))

    def _on_list_resized(self, event):
        # Titles wrap at a fixed pixel width; re-render once the window has
        # settled at a noticeably different size so they use the new space.
        if not self._loaded or self._load_error is not None:
            return
        if abs(self._wrap_for_width(event.width) - getattr(self, "_title_wrap", 0)) < 60:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(250, self._rewrap_after_resize)

    def _rewrap_after_resize(self):
        self._resize_after = None
        self._render_sessions(keep_scroll=True)

    def _show_more(self):
        self.visible_limit += PAGE_SIZE
        self._render_sessions(keep_scroll=True)

    def _render_empty(self, mode_name):
        empty = ctk.CTkFrame(self._scroll, fg_color=CARD, corner_radius=12, border_width=1, border_color=LINE)
        empty.pack(fill="x", padx=6, pady=(4, 0))
        if self.search_query or not self._archived_var.get() and any(self.sessions_by_account.values()):
            title = "Nenhuma sessão corresponde aos filtros"
            text = "Revise a busca ou inclua as sessões arquivadas."
            action = ("Limpar filtros", self._reset_filters)
        elif self.selected_account is not None:
            title = f"Esta conta ainda não tem sessões do {mode_name}"
            text = (
                "Ela já pode receber sessões vinculadas de outras contas. "
                f"Para criar uma conversa própria, use a aba {mode_name} com esta conta no Claude Desktop."
            )
            action = None
        else:
            title = f"Nenhuma sessão do {mode_name} encontrada"
            text = (
                f"Abra o Claude Desktop, entre em cada conta e use a aba {mode_name} pelo menos uma vez. "
                "Depois clique em Atualizar lista."
            )
            action = None
        ctk.CTkLabel(empty, text=title, font=self._f_h, text_color=INK, anchor="w").pack(anchor="w", padx=22, pady=(22, 4))
        ctk.CTkLabel(empty, text=text, font=self._f_s, text_color=INK2, anchor="w", justify="left", wraplength=620).pack(anchor="w", padx=22, pady=(0, 18 if action is None else 10))
        if action:
            self._button(empty, action[0], action[1], "secondary").pack(anchor="w", padx=22, pady=(0, 20))

    def _reset_filters(self):
        self._archived_var.set(True)
        self._search_entry.delete(0, "end")
        self._search_clear.grid_forget()
        self.focus_set()
        self.search_query = ""
        self.visible_limit = PAGE_SIZE
        self._render_sessions()

    def _duplicate_others(self, account_id, session):
        cwd_key = (session.get("cwd") or "").rstrip("\\/").lower()
        group = self.duplicates.get(cwd_key) or []
        return [
            (a, s) for a, s in group
            if s.get("cliSessionId") != session.get("cliSessionId")
            and not is_direct_linked_counterpart(account_id, session, a, s, self.session_mode)
        ]

    def _build_session_card(self, account_id, session):
        card_mode = self.session_mode
        card = ctk.CTkFrame(self._scroll, fg_color=CARD, corner_radius=10, border_width=1, border_color=LINE)
        card.pack(fill="x", padx=6, pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=(18, 10), pady=14)
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            body, text=session["title"], font=self._f_b, text_color=INK,
            anchor="w", justify="left", wraplength=self._title_wrap,
        ).grid(row=0, column=0, sticky="w")

        meta_bits = []
        if self.selected_account is None:
            meta_bits.append(self._account_label(account_id))
        meta_bits.append(project_name(session.get("cwd")) or "sem pasta")
        meta_bits.append(fmt_relative(session.get("lastActivityAt", 0)))
        meta_label = ctk.CTkLabel(
            body, text="  ·  ".join(meta_bits), font=self._f_x, text_color=INK2,
            anchor="w", justify="left", cursor="hand2",
        )
        meta_label.grid(row=1, column=0, sticky="w", pady=(3, 0))
        meta_label.bind("<Enter>", lambda _e: meta_label.configure(text_color=ACCENT), add="+")
        meta_label.bind("<Leave>", lambda _e: meta_label.configure(text_color=INK2), add="+")

        def copy_cwd(_e=None, cwd=session.get("cwd", "")):
            if cwd:
                self.clipboard_clear()
                self.clipboard_append(cwd)
                self._toast("Caminho do projeto copiado.")

        meta_label.bind("<Button-1>", copy_cwd, add="+")
        tip = [session.get("cwd") or "Sem pasta de projeto registrada."]
        tip.append(f"Última atividade: {fmt_ts(session.get('lastActivityAt', 0))}")
        if session.get("cliSessionId"):
            tip.append(f"ID: {session['cliSessionId']}")
        tip.append("Clique para copiar o caminho.")
        self._add_tooltip(meta_label, "\n".join(tip))

        chips = []
        if session.get("isArchived"):
            chips.append(("Arquivada", "neutral", None))
        for text, kind in self._link_badges(account_id, session):
            chips.append((text, "ok" if kind == "origin" else "info", None))
        others = self._duplicate_others(account_id, session)
        if others:
            n_accounts = len({a for a, _ in others})
            chips.append((
                f"Possível duplicata em {self._plural_other_accounts(n_accounts)}  →  comparar", "warn",
                lambda a=account_id, s=session, o=others, m=card_mode: self._open_compare_dialog((a, s), o, m),
            ))
        if chips:
            chip_row = ctk.CTkFrame(body, fg_color="transparent")
            chip_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
            for text, tone, command in chips:
                if command is None:
                    self._chip(chip_row, text, tone).pack(side="left", padx=(0, 6))
                else:
                    fg, bg, line = TONES[tone]
                    ctk.CTkButton(
                        chip_row, text=text, command=command, height=22, corner_radius=6, cursor="hand2",
                        font=self._f_xs, fg_color=bg, hover_color=line, text_color=fg, border_width=0,
                    ).pack(side="left", padx=(0, 6))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        if self._compact_layout:
            actions.grid(row=1, column=0, sticky="e", padx=14, pady=(0, 12))
        else:
            actions.grid(row=0, column=1, sticky="ne", padx=(0, 14), pady=14)
        remove_btn = self._button(
            actions, "Remover", lambda s=session, a=account_id, m=card_mode: self._open_remove_dialog(s, a, m),
            "danger-ghost", width=78, height=32,
        )
        remove_btn.pack(side="left", padx=(0, 4))
        compare_btn = self._button(
            actions, "Comparar", lambda s=session, a=account_id, m=card_mode: self._open_compare_picker((a, s), m),
            "secondary", width=92, height=32,
        )
        compare_btn.pack(side="left", padx=(0, 6))
        link_btn = self._button(
            actions, "Vincular a outra conta", lambda s=session, a=account_id, m=card_mode: self._open_link_dialog(s, a, m),
            "primary", width=150, height=32,
        )
        link_btn.pack(side="left")
        self._add_tooltip(link_btn, "Copia esta sessão para outra conta deste computador, com backup antes.")
        self._add_tooltip(
            compare_btn,
            "Compara o número de mensagens e a atividade mais recente com a cópia vinculada em outra conta. "
            "Sem vínculo direto, permite escolher outra sessão.",
        )
        self._add_tooltip(remove_btn, "Remove esta sessão apenas desta conta, com backup antes da alteração.")

    # -- actions ----------------------------------------------------------

    def _desktop_guard(self, dialog, status, button, label):
        """First click with Desktop open warns; the second click proceeds."""
        if not is_desktop_running():
            return True
        if getattr(dialog, "_confirmed_running", False):
            return True
        dialog._confirmed_running = True
        status.show(
            "O Claude Desktop ainda está aberto. Feche-o completamente (também pela bandeja ou pelo menu) "
            "para evitar que ele sobrescreva os arquivos. Se preferir continuar assim mesmo, clique de novo.",
            "warn",
        )
        button.configure(text=label)
        return False

    def _open_remove_dialog(self, session, account_id, mode=None):
        mode = mode or self.session_mode
        dialog, box = self._make_dialog("Remover sessão", 580, 380)
        self._dialog_header(box, "Remover esta sessão da conta?", f"{session['title']}\nConta: {self._account_label(account_id)}")

        if mode == "cowork":
            detail = (
                "Um backup ZIP do workspace será criado primeiro. Depois, o índice desta conta e a pasta local "
                "da conversa do Cowork serão apagados. Cópias vinculadas em outras contas continuam intactas."
            )
        else:
            detail = (
                "Um backup ZIP dos índices será criado primeiro. Depois, só o índice desta conta será apagado; "
                "o arquivo de conversa do Code permanece no computador."
            )
        ctk.CTkLabel(box, text=detail, font=self._f_x, text_color=INK2, wraplength=box.wrap, justify="left", anchor="w").pack(anchor="w", padx=22, pady=(14, 0))
        status = StatusBox(box, self._f_x, box.wrap - 24, fill="x", padx=22, pady=(14, 0))

        actions = self._dialog_actions(box)
        state = {"done": False}

        def do_remove():
            if not self._desktop_guard(dialog, status, remove_btn, "Remover mesmo assim"):
                return
            remove_btn.configure(state="disabled", text="Removendo…")
            cancel_btn.configure(state="disabled")
            status.show("Criando backup e removendo…", "neutral")

            def done(result, error):
                if not dialog.winfo_exists():
                    return
                ok, msg = result if error is None else (False, f"Falha inesperada: {error}")
                status.show(msg, "ok" if ok else "danger")
                cancel_btn.configure(state="normal")
                if ok:
                    state["done"] = True
                    remove_btn.pack_forget()
                    cancel_btn.configure(text="Fechar")
                    self.refresh()
                else:
                    remove_btn.configure(state="normal", text="Remover")

            self._run_background(lambda: remove_session_from_account(session, mode), done)

        def close_dialog():
            if cancel_btn.cget("state") == "disabled":
                return
            dialog.destroy()

        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        remove_btn = self._button(actions, "Remover", do_remove, "danger", width=150, height=38)
        remove_btn.pack(side="right")
        cancel_btn = self._button(actions, "Cancelar", close_dialog, "secondary", width=110, height=38)
        cancel_btn.pack(side="right", padx=(0, 8))

    def _open_link_dialog(self, session, source_account_id, mode=None):
        mode = mode or self.session_mode
        others = [a for a in self._sorted_accounts() if a != source_account_id]
        if not others:
            self._toast("Ainda não há outra conta detectada neste computador.")
            return

        dialog, box = self._make_dialog("Vincular sessão", 640, 370 + 48 * min(len(others), 5))
        self._dialog_header(box, "Vincular a outra conta", f"{session['title']}\nDe: {self._account_label(source_account_id)}")
        ctk.CTkLabel(box, text="CONTA DE DESTINO", font=self._f_label, text_color=INK3, anchor="w").pack(anchor="w", padx=22, pady=(18, 6))

        selected = {"id": others[0]}
        if len(others) > 5:
            target_rows = ctk.CTkScrollableFrame(box, fg_color="transparent", height=240, corner_radius=0)
        else:
            target_rows = ctk.CTkFrame(box, fg_color="transparent")
        target_rows.pack(fill="x", padx=16)
        row_buttons: dict[str, "ctk.CTkButton"] = {}

        def select_target(account_id):
            selected["id"] = account_id
            for aid, b in row_buttons.items():
                chosen = aid == account_id
                b.configure(
                    fg_color=ACCENT_SOFT if chosen else CARD,
                    border_color=ACCENT if chosen else LINE2,
                    text=("◉  " if chosen else "○  ") + display_name(aid),
                )

        def display_name(a):
            count = len(self.sessions_by_account.get(a, []))
            tag = "  ·  ativa agora" if a == self.active_account else ""
            return f"{self._account_label(a)}{tag}  ·  {self._plural_sessions(count)}"

        for a in others:
            b = ctk.CTkButton(
                target_rows, text=display_name(a), anchor="w", height=40, corner_radius=8, cursor="hand2",
                font=self._f_s, fg_color=CARD, hover_color=PAPER, text_color=INK,
                border_width=1, border_color=LINE2, command=lambda a=a: select_target(a),
            )
            b.pack(fill="x", padx=6, pady=(0, 6))
            row_buttons[a] = b
        select_target(others[0])

        if mode == "cowork":
            how = "Copia o índice e a pasta local da conversa para a conta escolhida. A origem não é alterada."
        else:
            how = ("Cria na conta escolhida uma cópia independente da conversa: cada conta poderá continuá-la "
                   "separadamente. A origem não é alterada.")
        ctk.CTkLabel(box, text=how + " Um backup ZIP é criado antes.", font=self._f_x, text_color=INK2,
                     wraplength=box.wrap, justify="left", anchor="w").pack(anchor="w", padx=22, pady=(8, 0))
        status = StatusBox(box, self._f_x, box.wrap - 24, fill="x", padx=22, pady=(12, 0))
        actions = self._dialog_actions(box)

        def do_link():
            target_id = selected["id"]
            if not target_id or not self._desktop_guard(dialog, status, link_btn, "Vincular mesmo assim"):
                return
            status.show("Vinculando e criando backup…", "neutral")
            link_btn.configure(state="disabled", text="Vinculando…")
            close_btn.configure(state="disabled")
            for button in row_buttons.values():
                button.configure(state="disabled")

            def work():
                if mode == "cowork":
                    return link_cowork_session_to_account(session, target_id)
                return link_session_to_account(session, target_id)

            def done(result, error):
                if not dialog.winfo_exists():
                    return
                ok, msg = result if error is None else (False, f"Falha inesperada: {error}")
                if ok:
                    msg += "\n\nReabra o Claude Desktop na conta de destino para ver a sessão na barra lateral."
                status.show(msg, "ok" if ok else "danger")
                close_btn.configure(state="normal")
                if ok:
                    link_btn.pack_forget()
                    close_btn.configure(text="Fechar")
                    self.refresh()
                else:
                    link_btn.configure(state="normal", text="Vincular")
                    for button in row_buttons.values():
                        button.configure(state="normal")

            self._run_background(work, done)

        def close_dialog():
            if close_btn.cget("state") == "disabled":
                return
            dialog.destroy()

        dialog.bind("<Escape>", lambda _e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        link_btn = self._button(actions, "Vincular", do_link, "primary", width=150, height=38)
        link_btn.pack(side="right")
        close_btn = self._button(actions, "Cancelar", close_dialog, "secondary", width=110, height=38)
        close_btn.pack(side="right", padx=(0, 8))

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
        """Entry point from the duplicate chip: `others` is already narrowed
        to sessions sharing this session's cwd."""
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
        source_account_id, source_session = source
        dialog, box = self._make_dialog("Comparar sessão", 600, min(620, 220 + 58 * min(len(candidates), 8)))
        self._dialog_header(box, "Comparar com qual sessão?", self._clip(source_session["title"], 90))

        query_var = ctk.StringVar(value="")
        entry = ctk.CTkEntry(
            box, textvariable=query_var, height=34, fg_color=CARD, border_color=LINE2, text_color=INK,
            font=self._f_x, placeholder_text="Filtrar por título, pasta ou conta", placeholder_text_color=INK3,
        )
        if len(candidates) > 6:
            entry.pack(fill="x", padx=22, pady=(12, 0))
        scroll = ctk.CTkScrollableFrame(box, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=16, pady=(10, 0))
        actions = self._dialog_actions(box)
        self._button(actions, "Cancelar", dialog.destroy, "secondary", width=110, height=38).pack(side="right")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        def choose(a, s):
            dialog.destroy()
            self._show_comparison(source, (a, s), mode)

        def render():
            for w in scroll.winfo_children():
                w.destroy()
            query = query_var.get()
            shown = [(a, s) for a, s in candidates if session_matches(s, query, self._account_label(a))][:50]
            if not shown:
                ctk.CTkLabel(scroll, text="Nenhuma sessão corresponde ao filtro.", font=self._f_x, text_color=INK3).pack(anchor="w", padx=6, pady=8)
            for a, s in shown:
                linked = is_direct_linked_counterpart(source_account_id, source_session, a, s, mode)
                prefix = "Cópia vinculada  ·  " if linked else ""
                meta = self._clip(f"{prefix}{self._account_label(a)}  ·  {project_name(s.get('cwd')) or 'sem pasta'}  ·  {fmt_relative(s.get('lastActivityAt', 0))}", 80)
                ctk.CTkButton(
                    scroll, text=f"{self._clip(s['title'], 64)}\n{meta}", anchor="w", height=50, corner_radius=8,
                    font=self._f_x, fg_color=ACCENT_SOFT if linked else CARD, hover_color=PAPER, text_color=INK,
                    border_width=1, border_color=LINE2, cursor="hand2",
                    command=lambda a=a, s=s: choose(a, s),
                ).pack(fill="x", padx=6, pady=(0, 6))

        query_var.trace_add("write", lambda *_: render())
        render()

    def _show_comparison(self, source, target, mode=None):
        mode = mode or self.session_mode
        dialog, box = self._make_dialog("Comparação de sessões", 680, 450)
        self._dialog_header(box, "Comparação de sessões", "Lida a partir dos arquivos de conversa, não do índice do Claude Desktop.")

        cols = ctk.CTkFrame(box, fg_color="transparent")
        cols.pack(fill="x", padx=22, pady=(16, 0))
        cols.grid_columnconfigure(0, weight=1, uniform="cmp")
        cols.grid_columnconfigure(1, weight=1, uniform="cmp")

        def make_column(col, account_id, session):
            c = ctk.CTkFrame(cols, fg_color=PAPER, corner_radius=10, border_width=1, border_color=LINE)
            c.grid(row=0, column=col, sticky="nsew", padx=(0, 6) if col == 0 else (6, 0))
            head = ctk.CTkFrame(c, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(14, 0))
            label = self._account_label(account_id)
            ctk.CTkLabel(
                head, text=avatar_initial(label), width=28, height=28, corner_radius=8,
                fg_color=avatar_color(account_id), text_color=WHITE, font=self._f_x,
            ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(head, text=self._clip(label, 24), font=self._f_b, text_color=INK).pack(side="left")
            if account_id == self.active_account:
                self._chip(head, "ativa", "ok").pack(side="left", padx=(8, 0))
            ctk.CTkLabel(
                c, text=self._clip(session["title"], 80), font=self._f_x, text_color=INK2,
                wraplength=260, justify="left", anchor="w",
            ).pack(anchor="w", padx=14, pady=(8, 0))
            count = ctk.CTkLabel(c, text="…", font=self._f_big, text_color=INK, anchor="w")
            count.pack(anchor="w", padx=14, pady=(8, 0))
            detail = ctk.CTkLabel(c, text="Lendo…", font=self._f_x, text_color=INK3, justify="left", anchor="w")
            detail.pack(anchor="w", padx=14, pady=(0, 14))
            return count, detail

        col_a = make_column(0, source[0], source[1])
        col_b = make_column(1, target[0], target[1])
        verdict = StatusBox(box, self._f_b, box.wrap - 24, fill="x", padx=22, pady=(14, 0))

        actions = self._dialog_actions(box)
        close_btn = self._button(actions, "Fechar", dialog.destroy, "secondary", width=110, height=38)
        close_btn.pack(side="right")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        def fill(column, p):
            count, detail = column
            if not p.get("found"):
                count.configure(text="—", text_color=INK3)
                detail.configure(text="Arquivo de conversa não encontrado neste computador.")
                return
            last = p["last_timestamp"]
            last_s = last.astimezone().strftime("%d/%m/%Y %H:%M") if last else "sem data"
            count.configure(text=str(p["message_count"]))
            noun = "mensagem" if p["message_count"] == 1 else "mensagens"
            detail.configure(text=f"{noun}\núltima atividade: {last_s}")

        def done(result, error):
            if not dialog.winfo_exists():
                return
            if error is not None:
                verdict.show(f"Não foi possível ler as conversas: {error}", "danger")
                return
            pa, pb = result
            fill(col_a, pa)
            fill(col_b, pb)
            a_label = self._account_label(source[0])
            b_label = self._account_label(target[0])
            if not (pa.get("found") and pb.get("found")):
                verdict.show("Não foi possível ler um dos arquivos de conversa para comparar.", "danger")
            elif pa["message_count"] != pb["message_count"]:
                ahead = a_label if pa["message_count"] > pb["message_count"] else b_label
                diff = abs(pa["message_count"] - pb["message_count"])
                verdict.show(f"{ahead} está mais avançada: {diff} mensage{'m' if diff == 1 else 'ns'} a mais.", "ok")
            elif pa["last_timestamp"] and pb["last_timestamp"] and pa["last_timestamp"] != pb["last_timestamp"]:
                ahead = a_label if pa["last_timestamp"] > pb["last_timestamp"] else b_label
                verdict.show(f"Mesmo número de mensagens; {ahead} tem a atividade mais recente.", "info")
            else:
                verdict.show("Empate: mesmo número de mensagens e mesma atividade.", "neutral")

        self._run_background(lambda: (read_session_progress(source[1], mode), read_session_progress(target[1], mode)), done)

    def _rename_account(self, account_id):
        current = self._account_label(account_id)
        dialog, box = self._make_dialog("Renomear conta", 460, 290)
        self._dialog_header(box, "Nome desta conta", f"Só muda o que você vê no Session Linker (ID interno {account_id[:8]}…).")

        entry = ctk.CTkEntry(box, height=36, fg_color=CARD, border_color=LINE2, text_color=INK, font=self._f_s)
        entry.pack(padx=22, pady=(14, 0), fill="x")
        entry.insert(0, current)
        entry.select_range(0, "end")
        entry.after(80, entry.focus_set)
        status = ctk.CTkLabel(box, text="", font=self._f_x, text_color=DANGER, anchor="w")
        status.pack(anchor="w", padx=22, pady=(6, 0), fill="x")

        def save_and_close(_event=None):
            new_label = entry.get().strip()
            if not new_label:
                status.configure(text="Informe um nome para salvar.")
                entry.focus_set()
                return
            if len(new_label) > 100:
                status.configure(text="O nome é muito longo (máximo de 100 caracteres).")
                entry.focus_set()
                return
            previous = self.labels.get(account_id)
            self.labels[account_id] = new_label
            try:
                save_labels(self.labels)
            except Exception as exc:
                if previous is None:
                    self.labels.pop(account_id, None)
                else:
                    self.labels[account_id] = previous
                status.configure(text=f"Não foi possível salvar: {exc}")
                return
            dialog.destroy()
            self._render_accounts()
            if self._loaded and self._load_error is None:
                self._render_sessions()
            self._toast("Conta renomeada.")

        entry.bind("<Return>", save_and_close)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        actions = self._dialog_actions(box)
        self._button(actions, "Salvar", save_and_close, "primary", width=120, height=38).pack(side="right")
        self._button(actions, "Cancelar", dialog.destroy, "secondary", width=110, height=38).pack(side="right", padx=(0, 8))

    # -- tooltip / toast ------------------------------------------------------

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
            win.configure(fg_color=INK)
            ctk.CTkLabel(
                win, text=text, font=self._f_xs, text_color=WHITE, fg_color=INK,
                justify="left", wraplength=min(380, max(180, win.winfo_screenwidth() - 48)), padx=12, pady=8,
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
            below_y = widget.winfo_rooty() + widget.winfo_height() + 6
            above_y = widget.winfo_rooty() - th - 6
            y = above_y if below_y + th > min(root_bottom, sh) and above_y >= root_y else below_y
            y = min(max(y, root_y + 8), max(min(root_bottom, sh) - th - 8, 0))
            win.geometry(f"+{x}+{y}")
            self._tooltip["win"] = win

        def show(_event=None):
            self._hide_tooltip()
            self._tooltip["widget"] = widget
            self._tooltip["after_id"] = self.after(500, show_now)

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", lambda _event=None: self._hide_tooltip(), add="+")
        widget.bind("<ButtonPress>", lambda _event=None: self._hide_tooltip(), add="+")
        widget.bind("<Destroy>", lambda _event=None: self._hide_tooltip(), add="+")

    def _toast(self, text):
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color=INK)
        win.attributes("-topmost", True)
        ctk.CTkLabel(
            win, text=text, font=self._f_x, text_color=WHITE, fg_color=INK, justify="left",
            wraplength=min(520, max(180, win.winfo_screenwidth() - 48)), padx=16, pady=10,
        ).pack()
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        tw = min(win.winfo_reqwidth(), 560)
        th = win.winfo_reqheight()
        x = self.winfo_rootx() + (self.winfo_width() - tw) // 2
        y = self.winfo_rooty() + self.winfo_height() - th - 28
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
