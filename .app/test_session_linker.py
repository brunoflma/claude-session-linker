import importlib.util
import json
import os
import re
import shutil
import tempfile
import time
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("session_linker.py")
spec = importlib.util.spec_from_file_location("session_linker", MODULE_PATH)
session_linker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session_linker)


class MacInitTests(unittest.TestCase):
    def test_module_imports_without_appdata_env(self):
        # Simulate macOS: no APPDATA/LOCALAPPDATA, platform forced to darwin.
        env = dict(os.environ)
        env.pop("APPDATA", None)
        env.pop("LOCALAPPDATA", None)
        env["CLAUDE_SESSION_LINKER_PLATFORM"] = "darwin"
        env.pop(CLAUDE_DIR_ENV, None)
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        try:
            spec_local = importlib.util.spec_from_file_location("session_linker_macinit", MODULE_PATH)
            module = importlib.util.module_from_spec(spec_local)
            spec_local.loader.exec_module(module)  # must not raise
            self.assertEqual(module._PLATFORM, "darwin")
            self.assertIsNone(module.APPDATA)
        finally:
            os.environ.clear()
            os.environ.update(saved)


CLAUDE_DIR_ENV = "CLAUDE_SESSION_LINKER_CLAUDE_DIR"


def load_session_linker_with_env(appdata: Path, localappdata: Path, claude_dir: Path | None = None):
    original_appdata = os.environ.get("APPDATA")
    original_localappdata = os.environ.get("LOCALAPPDATA")
    original_claude_dir = os.environ.get(CLAUDE_DIR_ENV)
    os.environ["APPDATA"] = str(appdata)
    os.environ["LOCALAPPDATA"] = str(localappdata)
    os.environ["CLAUDE_SESSION_LINKER_PLATFORM"] = "win32"
    if claude_dir is None:
        os.environ.pop(CLAUDE_DIR_ENV, None)
    else:
        os.environ[CLAUDE_DIR_ENV] = str(claude_dir)
    try:
        env_spec = importlib.util.spec_from_file_location("session_linker_env_test", MODULE_PATH)
        module = importlib.util.module_from_spec(env_spec)
        env_spec.loader.exec_module(module)
        return module
    finally:
        if original_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = original_appdata
        if original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = original_localappdata
        if original_claude_dir is None:
            os.environ.pop(CLAUDE_DIR_ENV, None)
        else:
            os.environ[CLAUDE_DIR_ENV] = original_claude_dir
        os.environ.pop("CLAUDE_SESSION_LINKER_PLATFORM", None)


def load_session_linker_macos(macos_base: Path, claude_dir: Path | None = None):
    saved = dict(os.environ)
    os.environ.pop("APPDATA", None)
    os.environ.pop("LOCALAPPDATA", None)
    os.environ["CLAUDE_SESSION_LINKER_PLATFORM"] = "darwin"
    os.environ["CLAUDE_SESSION_LINKER_MACOS_BASE"] = str(macos_base)
    if claude_dir is None:
        os.environ.pop(CLAUDE_DIR_ENV, None)
    else:
        os.environ[CLAUDE_DIR_ENV] = str(claude_dir)
    try:
        env_spec = importlib.util.spec_from_file_location("session_linker_macos_test", MODULE_PATH)
        module = importlib.util.module_from_spec(env_spec)
        env_spec.loader.exec_module(module)
        return module
    finally:
        os.environ.clear()
        os.environ.update(saved)


def make_session(name, cli_id, last_activity, path_name=None):
    return {
        "path": Path(path_name or f"{name}.json"),
        "sessionId": name,
        "cliSessionId": cli_id,
        "cwd": r"C:\project",
        "title": name,
        "lastActivityAt": last_activity,
        "isArchived": False,
        "workspaceUUID": "workspace",
        "linkedFromAccount": None,
        "originAccount": None,
    }


def write_code_session(root: Path, account_id: str, workspace_id: str, name: str, cli_id: str, last_activity: int):
    workspace = root / "claude-code-sessions" / account_id / workspace_id
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"local_{name}.json"
    path.write_text(
        json.dumps({
            "sessionId": name,
            "cliSessionId": cli_id,
            "cwd": rf"C:\project\{name}",
            "title": name,
            "lastActivityAt": last_activity,
        }),
        encoding="utf-8",
    )
    return path


def write_cowork_session(root: Path, account_id: str, workspace_id: str, name: str, cli_id: str, last_activity: int):
    workspace = root / "local-agent-mode-sessions" / account_id / workspace_id
    data_dir = workspace / f"local_{name}"
    data_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir = data_dir / "outputs"
    outputs_dir.mkdir()
    (data_dir / "audit.jsonl").write_text('{"type":"user","timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
    path = workspace / f"local_{name}.json"
    path.write_text(
        json.dumps({
            "sessionId": name,
            "cliSessionId": cli_id,
            "cwd": str(outputs_dir),
            "title": name,
            "lastActivityAt": last_activity,
        }),
        encoding="utf-8",
    )
    return path, data_dir


def encoded_project_dir(path: Path) -> str:
    # Mirror Claude Desktop exactly: each non-alphanumeric char becomes its own
    # dash (no collapsing), so a `C:\` drive prefix yields `C--`.
    return re.sub(r"[^A-Za-z0-9]", "-", str(path)).strip("-")


class ClaudeProjectDirNameTests(unittest.TestCase):
    def test_matches_claude_desktop_per_char_encoding(self):
        # Claude Desktop replaces EACH non-alphanumeric character with a dash;
        # it does not collapse consecutive separators. The `:\` after the drive
        # letter must therefore produce a double dash. If this collapses to a
        # single dash, normalize_cowork_session_copy computes the wrong project
        # folder name, the rename is skipped, and Claude reports
        # "No conversation found with session ID: ...".
        self.assertEqual(
            session_linker.claude_project_dir_name(
                r"C:\Users\bruno\AppData\Roaming\Claude\local_5a02\outputs"
            ),
            "C--Users-bruno-AppData-Roaming-Claude-local-5a02-outputs",
        )

    def test_agrees_with_real_cowork_folder_name(self):
        cwd = (
            r"C:\Users\bruno\AppData\Roaming\Claude\local-agent-mode-sessions"
            r"\d3175704-2ff0-40cf-9335-fe5ebcee0085"
            r"\32f37971-c6ed-47c6-89a5-8afe7e524fe1"
            r"\local_5a0266a6-d242-423f-aa1c-34bc9de1f2af\outputs"
        )
        real_folder = (
            "C--Users-bruno-AppData-Roaming-Claude-local-agent-mode-sessions-"
            "d3175704-2ff0-40cf-9335-fe5ebcee0085-"
            "32f37971-c6ed-47c6-89a5-8afe7e524fe1-"
            "local-5a0266a6-d242-423f-aa1c-34bc9de1f2af-outputs"
        )
        self.assertEqual(session_linker.claude_project_dir_name(cwd), real_folder)


class SessionLinkerLogicTests(unittest.TestCase):
    def test_find_transcript_path_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            projects_dir.mkdir()
            secret_file = Path(tmp) / "secret.jsonl"
            secret_file.write_text("secret", encoding="utf-8")

            original_projects_dir = session_linker.CLAUDE_PROJECTS_DIR
            session_linker.CLAUDE_PROJECTS_DIR = projects_dir
            try:
                self.assertIsNone(session_linker.find_transcript_path("../secret"))
                self.assertIsNone(session_linker.find_transcript_path("..\\secret"))
                self.assertIsNone(session_linker.find_transcript_path("/etc/passwd"))
                self.assertIsNone(session_linker.find_transcript_path("C:\\Windows\\System32\\cmd.exe"))
            finally:
                session_linker.CLAUDE_PROJECTS_DIR = original_projects_dir

    def test_backup_and_text_replacement_skip_symlinked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            outside = Path(tmp) / "outside.txt"
            regular = root / "regular.txt"
            linked = root / "linked.txt"
            root.mkdir()
            outside.write_text("old outside", encoding="utf-8")
            regular.write_text("old inside", encoding="utf-8")
            try:
                linked.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable on this host: {exc}")

            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                backup_path = session_linker.backup_dir_tree(root, "workspace")
                with zipfile.ZipFile(backup_path) as archive:
                    names = archive.namelist()
                self.assertIn("workspace/regular.txt", names)
                self.assertNotIn("workspace/linked.txt", names)

                session_linker._replace_text_in_tree(root, {"old": "new"})
                self.assertEqual(regular.read_text(encoding="utf-8"), "new inside")
                self.assertEqual(outside.read_text(encoding="utf-8"), "old outside")
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_module_uses_explicit_claude_profile_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            explicit_root = Path(tmp) / "PinnedClaude"

            module = load_session_linker_with_env(appdata, localappdata, explicit_root)

            self.assertEqual(module.CLAUDE_DIR, explicit_root)

    def test_module_uses_newest_valid_claude_profile_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            (default_root / "claude-code-sessions").mkdir(parents=True)
            (custom_root / "claude-code-sessions").mkdir(parents=True)
            default_config = default_root / "config.json"
            custom_config = custom_root / "config.json"
            default_config.write_text("{}", encoding="utf-8")
            custom_config.write_text("{}", encoding="utf-8")
            old_ts = time.time() - 300
            new_ts = time.time()
            os.utime(default_config, (old_ts, old_ts))
            os.utime(custom_config, (new_ts, new_ts))

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(module.CLAUDE_DIR, custom_root)
            self.assertEqual(module.CLAUDE_DIRS, [custom_root, default_root])
            self.assertEqual(module.SESSIONS_DIR, custom_root / "claude-code-sessions")
            self.assertEqual(module.COWORK_SESSIONS_DIR, custom_root / "local-agent-mode-sessions")
            self.assertEqual(module.CONFIG_JSON, custom_root / "config.json")

    def test_module_discovers_msix_and_3p_profile_roots_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            threep_root = localappdata / "Claude-3p"
            msix_root = (
                localappdata
                / "Packages"
                / "Claude_pzs8sxrjxfjjc"
                / "LocalCache"
                / "Roaming"
                / "Claude"
            )
            (threep_root / "config.json").parent.mkdir(parents=True)
            (threep_root / "config.json").write_text("{}", encoding="utf-8")
            write_code_session(threep_root, "threep-account", "workspace-3p", "threep", "cli-3p", 10)
            write_code_session(msix_root, "paid-account", "workspace-paid", "paid", "cli-paid", 20)
            (localappdata / "Packages" / "Claude_invalid").mkdir(parents=True)

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(set(module.CLAUDE_DIRS), {threep_root, msix_root})
            self.assertEqual(set(module.scan_sessions()), {"threep-account", "paid-account"})

    def test_scan_sessions_includes_accounts_from_all_valid_claude_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            (default_root / "config.json").parent.mkdir(parents=True)
            (custom_root / "config.json").parent.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")
            write_code_session(default_root, "official-account", "workspace-official", "official", "cli-official", 10)
            write_code_session(custom_root, "threep-account", "workspace-3p", "threep", "cli-3p", 20)

            module = load_session_linker_with_env(appdata, localappdata)
            sessions = module.scan_sessions()

            self.assertEqual(set(sessions), {"official-account", "threep-account"})
            self.assertEqual(sessions["official-account"][0]["claudeDir"], default_root)
            self.assertEqual(sessions["threep-account"][0]["claudeDir"], custom_root)

    def test_scan_cowork_sessions_includes_accounts_from_all_valid_claude_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            (default_root / "config.json").parent.mkdir(parents=True)
            (custom_root / "config.json").parent.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")
            write_cowork_session(default_root, "official-account", "workspace-official", "official", "cli-official", 10)
            _, custom_data_dir = write_cowork_session(custom_root, "threep-account", "workspace-3p", "threep", "cli-3p", 20)

            module = load_session_linker_with_env(appdata, localappdata)
            sessions = module.scan_cowork_sessions()

            self.assertEqual(set(sessions), {"official-account", "threep-account"})
            self.assertEqual(sessions["official-account"][0]["claudeDir"], default_root)
            self.assertEqual(sessions["threep-account"][0]["claudeDir"], custom_root)
            self.assertEqual(sessions["threep-account"][0]["data_dir"], custom_data_dir)

    def test_scan_cowork_sessions_ignores_empty_non_account_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            (default_root / "config.json").parent.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            write_cowork_session(default_root, "official-account", "workspace-official", "official", "cli-official", 10)
            (default_root / "local-agent-mode-sessions" / "skills-plugin" / "workspace").mkdir(parents=True)

            module = load_session_linker_with_env(appdata, localappdata)
            sessions = module.scan_cowork_sessions()

            self.assertEqual(set(sessions), {"official-account"})

    def test_link_session_to_account_can_copy_from_3p_root_to_official_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path = write_code_session(custom_root, "threep-account", "workspace-3p", "source", "cli-source", 20)
            target_workspace = default_root / "claude-code-sessions" / "official-account" / "workspace-official"
            target_workspace.mkdir(parents=True)
            default_config = default_root / "config.json"
            custom_config = custom_root / "config.json"
            default_config.write_text("{}", encoding="utf-8")
            custom_config.write_text("{}", encoding="utf-8")
            old_ts = time.time() - 300
            new_ts = time.time()
            os.utime(default_config, (old_ts, old_ts))
            os.utime(custom_config, (new_ts, new_ts))

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "accountId": "threep-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_session_to_account(source_session, "official-account")

                self.assertTrue(ok, message)
                self.assertTrue((target_workspace / source_path.name).exists())
                self.assertFalse((custom_root / "claude-code-sessions" / "official-account").exists())
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_link_session_to_account_can_copy_from_official_root_to_3p_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path = write_code_session(default_root, "official-account", "workspace-official", "source", "cli-source", 20)
            target_workspace = custom_root / "claude-code-sessions" / "threep-account" / "workspace-3p"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "accountId": "official-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_session_to_account(source_session, "threep-account")

                self.assertTrue(ok, message)
                self.assertTrue((target_workspace / source_path.name).exists())
                self.assertFalse((default_root / "claude-code-sessions" / "threep-account").exists())
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_code_link_clones_transcript_and_uses_new_cli_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path = write_code_session(default_root, "official-account", "workspace-official", "source", "cli-source", 20)
            target_workspace = custom_root / "claude-code-sessions" / "threep-account" / "workspace-3p"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")

            projects_dir = Path(tmp) / "projects"
            project_dir = projects_dir / "cwd-hash"
            project_dir.mkdir(parents=True)
            source_transcript = project_dir / "cli-source.jsonl"
            source_transcript.write_text(
                '{"type":"user","timestamp":"2026-01-01T00:00:00Z"}\n'
                '{"type":"assistant","timestamp":"2026-01-01T00:00:01Z"}\n',
                encoding="utf-8",
            )

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            original_projects_dir = module.CLAUDE_PROJECTS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.CLAUDE_PROJECTS_DIR = projects_dir
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "accountId": "official-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_session_to_account(source_session, "threep-account")

                self.assertTrue(ok, message)
                linked_index = target_workspace / source_path.name
                linked_data = json.loads(linked_index.read_text(encoding="utf-8"))
                self.assertNotEqual(linked_data["cliSessionId"], "cli-source")
                linked_transcript = project_dir / f'{linked_data["cliSessionId"]}.jsonl'
                self.assertTrue(linked_transcript.exists())
                self.assertEqual(linked_transcript.read_text(encoding="utf-8"), source_transcript.read_text(encoding="utf-8"))
                metadata = module.get_link_metadata(linked_index)
                self.assertEqual(metadata[module.LINKED_SOURCE_CLI_SESSION_ID_KEY], "cli-source")
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir
                module.CLAUDE_PROJECTS_DIR = original_projects_dir

    def test_link_cowork_session_to_account_can_copy_between_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path, source_data_dir = write_cowork_session(custom_root, "threep-account", "workspace-3p", "source", "cli-source", 20)
            target_workspace = default_root / "local-agent-mode-sessions" / "official-account" / "workspace-official"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "data_dir": source_data_dir,
                    "accountId": "threep-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_cowork_session_to_account(source_session, "official-account")

                self.assertTrue(ok, message)
                self.assertTrue((target_workspace / source_path.name).exists())
                self.assertTrue((target_workspace / source_data_dir.name / "audit.jsonl").exists())
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_link_cowork_session_rewrites_cwd_and_embedded_project_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path, source_data_dir = write_cowork_session(custom_root, "threep-account", "workspace-3p", "source", "cli-source", 20)
            target_workspace = default_root / "local-agent-mode-sessions" / "official-account" / "workspace-official"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")
            source_outputs = source_data_dir / "outputs"
            source_project = source_data_dir / ".claude" / "projects" / encoded_project_dir(source_outputs)
            source_project.mkdir(parents=True)
            (source_project / "cli-source.jsonl").write_text(str(source_outputs), encoding="utf-8")

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "data_dir": source_data_dir,
                    "accountId": "threep-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_cowork_session_to_account(source_session, "official-account")

                self.assertTrue(ok, message)
                linked_index = target_workspace / source_path.name
                linked_data_dir = target_workspace / source_data_dir.name
                linked_data = json.loads(linked_index.read_text(encoding="utf-8"))
                linked_outputs = linked_data_dir / "outputs"
                linked_project = linked_data_dir / ".claude" / "projects" / encoded_project_dir(linked_outputs)
                self.assertEqual(linked_data["cwd"], str(linked_outputs))
                self.assertTrue(linked_project.exists())
                self.assertFalse((linked_data_dir / ".claude" / "projects" / encoded_project_dir(source_outputs)).exists())
                self.assertIn(str(linked_outputs), (linked_project / "cli-source.jsonl").read_text(encoding="utf-8"))
                self.assertNotIn(str(source_outputs), (linked_project / "cli-source.jsonl").read_text(encoding="utf-8"))
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_existing_cowork_destination_is_repaired_when_relinked(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path, source_data_dir = write_cowork_session(custom_root, "threep-account", "workspace-3p", "source", "cli-source", 20)
            target_workspace = default_root / "local-agent-mode-sessions" / "official-account" / "workspace-official"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")
            source_outputs = source_data_dir / "outputs"
            source_project = source_data_dir / ".claude" / "projects" / encoded_project_dir(source_outputs)
            source_project.mkdir(parents=True)
            (source_project / "cli-source.jsonl").write_text(str(source_outputs), encoding="utf-8")
            dest_path = target_workspace / source_path.name
            dest_data_dir = target_workspace / source_data_dir.name
            shutil.copy2(source_path, dest_path)
            shutil.copytree(source_data_dir, dest_data_dir)

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            try:
                source_session = {
                    "path": source_path,
                    "data_dir": source_data_dir,
                    "accountId": "threep-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_cowork_session_to_account(source_session, "official-account")

                self.assertTrue(ok, message)
                linked_project = dest_data_dir / ".claude" / "projects" / encoded_project_dir(dest_data_dir / "outputs")
                self.assertTrue(linked_project.exists())
                self.assertEqual(json.loads(dest_path.read_text(encoding="utf-8"))["cwd"], str(dest_data_dir / "outputs"))
            finally:
                module.LINKS_FILE = original_links_file

    def test_remove_code_session_deletes_only_account_index_and_keeps_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path = write_code_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            transcript = Path(tmp) / "projects" / "workspace" / "cli-source.jsonl"
            transcript.parent.mkdir(parents=True)
            transcript.write_text('{"type":"user","timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "sessionsDir": root / "claude-code-sessions",
                        "title": "source",
                    },
                    "code",
                )

                self.assertTrue(ok, message)
                self.assertFalse(index_path.exists())
                self.assertTrue(transcript.exists())
                backups = list(session_linker.BACKUPS_DIR.glob("*.zip"))
                self.assertEqual(len(backups), 1)
                with zipfile.ZipFile(backups[0]) as zf:
                    self.assertIn(index_path.relative_to((root / "claude-code-sessions").parent).as_posix(), zf.namelist())
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_cowork_session_deletes_index_and_data_dir_after_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path, data_dir = write_cowork_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "data_dir": data_dir,
                        "sessionsDir": root / "local-agent-mode-sessions",
                        "title": "source",
                    },
                    "cowork",
                )

                self.assertTrue(ok, message)
                self.assertFalse(index_path.exists())
                self.assertFalse(data_dir.exists())
                backups = list(session_linker.BACKUPS_DIR.glob("*.zip"))
                self.assertEqual(len(backups), 1)
                with zipfile.ZipFile(backups[0]) as zf:
                    self.assertIn((index_path.parent.name + "/" + index_path.name), zf.namelist())
                    self.assertIn((index_path.parent.name + "/" + data_dir.name + "/audit.jsonl"), zf.namelist())
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_cowork_session_does_not_delete_index_if_data_dir_removal_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path, data_dir = write_cowork_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            links_file = Path(tmp) / "session_links.json"
            original_backups_dir = session_linker.BACKUPS_DIR
            original_links_file = session_linker.LINKS_FILE
            original_rmtree = session_linker.shutil.rmtree
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            session_linker.LINKS_FILE = links_file
            session_linker.record_link_metadata(index_path, "account-b", "account-a")
            session_linker.shutil.rmtree = lambda _path: (_ for _ in ()).throw(OSError("locked"))
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "data_dir": data_dir,
                        "sessionsDir": root / "local-agent-mode-sessions",
                        "title": "source",
                    },
                    "cowork",
                )

                self.assertFalse(ok, message)
                self.assertTrue(index_path.exists())
                self.assertTrue(data_dir.exists())
                self.assertIn(session_linker.LINKED_FROM_ACCOUNT_KEY, session_linker.get_link_metadata(index_path))
            finally:
                session_linker.shutil.rmtree = original_rmtree
                session_linker.LINKS_FILE = original_links_file
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_cowork_session_rejects_unexpected_data_dir_without_deleting_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path, data_dir = write_cowork_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            unsafe_dir = Path(tmp) / "elsewhere" / data_dir.name
            unsafe_dir.mkdir(parents=True)
            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "data_dir": unsafe_dir,
                        "sessionsDir": root / "local-agent-mode-sessions",
                        "title": "source",
                    },
                    "cowork",
                )

                self.assertFalse(ok, message)
                self.assertTrue(index_path.exists())
                self.assertTrue(data_dir.exists())
                self.assertTrue(unsafe_dir.exists())
                self.assertEqual(list(session_linker.BACKUPS_DIR.glob("*.zip")), [])
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_session_cleans_link_metadata_for_removed_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path = write_code_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            links_file = Path(tmp) / "session_links.json"
            original_backups_dir = session_linker.BACKUPS_DIR
            original_links_file = session_linker.LINKS_FILE
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            session_linker.LINKS_FILE = links_file
            session_linker.record_link_metadata(index_path, "account-b", "account-a")
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "sessionsDir": root / "claude-code-sessions",
                        "title": "source",
                    },
                    "code",
                )

                self.assertTrue(ok, message)
                self.assertEqual(session_linker.get_link_metadata(index_path), {})
            finally:
                session_linker.LINKS_FILE = original_links_file
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_module_falls_back_to_roaming_claude_when_it_is_the_only_valid_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            (default_root / "claude-code-sessions").mkdir(parents=True)
            (localappdata / "Claude-3p").mkdir(parents=True)

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(module.CLAUDE_DIR, default_root)

    def test_module_keeps_legacy_roaming_path_when_no_valid_root_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(module.CLAUDE_DIR, appdata / "Claude")

    def test_compare_candidates_include_linked_copy_with_same_cli_id(self):
        source = make_session("source", "same-cli", 10, "local_source.json")
        linked_copy = make_session("linked", "same-cli", 8, "local_source.json")
        unrelated = make_session("unrelated", "other-cli", 20, "local_other.json")

        candidates = session_linker.build_compare_candidates(
            {
                "account-a": [source],
                "account-b": [linked_copy],
                "account-c": [unrelated],
            },
            "account-a",
            source,
        )

        self.assertEqual(candidates[0], ("account-b", linked_copy))
        self.assertIn(("account-c", unrelated), candidates)
        self.assertNotIn(("account-a", source), candidates)

    def test_linked_compare_targets_filter_out_unrelated_sessions(self):
        source = make_session("source", "same-cli", 10, "local_source.json")
        linked_copy = make_session("linked", "same-cli", 8, "local_source.json")
        unrelated = make_session("unrelated", "other-cli", 20, "local_other.json")
        candidates = [("account-b", linked_copy), ("account-c", unrelated)]

        targets = session_linker.linked_compare_targets(candidates, "account-a", source)

        self.assertEqual(targets, [("account-b", linked_copy)])

    def test_code_sessions_resolving_to_same_transcript_are_not_comparable(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "same-cli.jsonl"
            transcript.write_text('{"type":"user","timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
            source = make_session("source", "same-cli", 10, "local_source.json")
            linked_alias = make_session("linked", "same-cli", 8, "local_source.json")
            original_find_transcript_path = session_linker.find_transcript_path
            session_linker.find_transcript_path = lambda cli_id: transcript if cli_id == "same-cli" else None

            try:
                targets = session_linker.linked_compare_targets(
                    [("account-b", linked_alias)],
                    "account-a",
                    source,
                    mode="code",
                )
            finally:
                session_linker.find_transcript_path = original_find_transcript_path

        self.assertEqual(targets, [])

    def test_link_groups_detect_same_cli_id_across_accounts(self):
        source = make_session("source", "same-cli", 10)
        linked_copy = make_session("linked", "same-cli", 8)
        unrelated = make_session("unrelated", "other-cli", 20)

        groups = session_linker.find_linked_session_groups(
            {
                "account-a": [source],
                "account-b": [linked_copy],
                "account-c": [unrelated],
            }
        )

        self.assertEqual(groups["same-cli"], [("account-a", source), ("account-b", linked_copy)])
        self.assertNotIn("other-cli", groups)

    def test_duplicate_detection_ignores_code_sessions_without_transcript_file(self):
        source = make_session("source", "source-cli", 10)
        missing = make_session("missing", "missing-cli", 8)
        original_find_transcript_path = session_linker.find_transcript_path
        session_linker.find_transcript_path = lambda cli_id: Path("found.jsonl") if cli_id == "source-cli" else None

        try:
            duplicates = session_linker.find_possible_duplicates(
                {
                    "account-a": [source],
                    "account-b": [missing],
                },
                mode="code",
            )
        finally:
            session_linker.find_transcript_path = original_find_transcript_path

        self.assertEqual(duplicates, {})

    def test_copy_index_preserves_json_and_records_origin_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "local_source.json"
            dest = Path(tmp) / "local_dest.json"
            links_file = Path(tmp) / "session_links.json"
            original_links_file = session_linker.LINKS_FILE
            session_linker.LINKS_FILE = links_file
            original = {"sessionId": "source", "cliSessionId": "same-cli"}
            src.write_text(json.dumps(original), encoding="utf-8")

            try:
                session_linker.copy_index_with_link_metadata(src, dest, "account-a", "account-a")

                copied = json.loads(dest.read_text(encoding="utf-8"))
                self.assertEqual(copied, original)
                metadata = session_linker.get_link_metadata(dest)
                self.assertEqual(metadata[session_linker.LINKED_FROM_ACCOUNT_KEY], "account-a")
                self.assertEqual(metadata[session_linker.ORIGIN_ACCOUNT_KEY], "account-a")
                self.assertIn(session_linker.LINKED_AT_KEY, metadata)
            finally:
                session_linker.LINKS_FILE = original_links_file

    def test_index_copy_and_clone_refuse_symlinked_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "local_source.json"
            outside = Path(tmp) / "outside.json"
            dest = Path(tmp) / "local_dest.json"
            src.write_text(json.dumps({"sessionId": "source"}), encoding="utf-8")
            outside.write_text('{"protected": true}', encoding="utf-8")
            try:
                dest.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable on this host: {exc}")

            with self.assertRaises(OSError):
                session_linker.copy_index_with_link_metadata(src, dest, "account-a")
            with self.assertRaises(OSError):
                session_linker.write_code_index_clone(src, dest, "account-a", "account-a")
            self.assertEqual(outside.read_text(encoding="utf-8"), '{"protected": true}')

    def test_existing_destination_updates_metadata_instead_of_failing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "local_source.json"
            dest = Path(tmp) / "local_dest.json"
            links_file = Path(tmp) / "session_links.json"
            original_links_file = session_linker.LINKS_FILE
            session_linker.LINKS_FILE = links_file
            src.write_text(json.dumps({"sessionId": "source"}), encoding="utf-8")
            dest.write_text(json.dumps({"sessionId": "source"}), encoding="utf-8")

            try:
                copied = session_linker.ensure_index_linked(src, dest, "account-b", "account-a")

                self.assertFalse(copied)
                metadata = session_linker.get_link_metadata(dest)
                self.assertEqual(metadata[session_linker.LINKED_FROM_ACCOUNT_KEY], "account-b")
                self.assertEqual(metadata[session_linker.ORIGIN_ACCOUNT_KEY], "account-a")
            finally:
                session_linker.LINKS_FILE = original_links_file

    def test_source_origin_prefers_existing_origin_metadata(self):
        source = make_session("linked", "same-cli", 10)
        source["accountId"] = "account-b"
        source["originAccount"] = "account-a"

        self.assertEqual(session_linker.source_origin_account(source), "account-a")

    def test_tasklist_uses_absolute_path_for_security(self):
        from unittest.mock import patch, Mock
        with patch.dict("os.environ", {"SystemRoot": r"C:\Poisoned", "PATH": r"C:\Poisoned"}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(stdout=b"")
                session_linker.is_desktop_running(platform="win32")
                tasklist_call = None
                for call in mock_run.call_args_list:
                    args = call[0][0]
                    if isinstance(args, list) and len(args) > 0 and 'tasklist.exe' in args[0].lower():
                        tasklist_call = call
                        break
                self.assertIsNotNone(tasklist_call, "tasklist was not called")
                cmd = tasklist_call[0][0][0]
                self.assertTrue(cmd.lower().endswith("tasklist.exe"))
                self.assertNotIn("poisoned", cmd.lower())
                self.assertTrue("system32" in cmd.lower())
                self.assertTrue(os.path.isabs(cmd) or cmd.startswith("C:\\") or cmd.startswith("c:\\"))


class MacDesktopDetectionTests(unittest.TestCase):
    def test_uses_pgrep_with_app_anchored_pattern(self):
        from unittest.mock import patch, Mock
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"1234\n")
            self.assertTrue(session_linker.is_desktop_running(platform="darwin"))
            args = mock_run.call_args[0][0]
            self.assertTrue(args[0].endswith("pgrep"))
            self.assertIn("-f", args)
            self.assertIn("Claude[.]app/Contents/MacOS/Claude($|[[:space:]])", args)

    def test_returns_false_when_only_cli_claude_running(self):
        from unittest.mock import patch, Mock
        with patch("subprocess.run") as mock_run:
            # pgrep with the capitalized .app pattern finds nothing -> returncode 1.
            mock_run.return_value = Mock(returncode=1, stdout=b"")
            self.assertFalse(session_linker.is_desktop_running(platform="darwin"))

    def test_get_system_executable_posix_prefers_usr_bin(self):
        path = session_linker._get_system_executable("pgrep", platform="darwin")
        self.assertTrue(path == "/usr/bin/pgrep" or path.endswith("/pgrep") or path == "pgrep")


class MacDiscoveryTests(unittest.TestCase):
    def test_rejects_unsupported_platform(self):
        with self.assertRaisesRegex(RuntimeError, "Unsupported platform"):
            session_linker.resolve_claude_dirs(None, platform="linux")

    def test_ignores_symlinked_claude_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "Application Support"
            outside = Path(tmp) / "outside-profile"
            base.mkdir()
            outside.mkdir()
            (outside / "config.json").write_text("{}", encoding="utf-8")
            try:
                (base / "Claude-evil").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable on this host: {exc}")

            found = session_linker.discover_claude_dirs(platform="darwin", macos_base=base)
            self.assertEqual(found, [])

    def test_discovers_claude_and_claude_3p(self):
        base = Path(tempfile.mkdtemp())
        try:
            for name in ("Claude", "Claude-3p"):
                d = base / name
                d.mkdir(parents=True)
                (d / "config.json").write_text("{}", encoding="utf-8")
            found = session_linker.discover_claude_dirs(platform="darwin", macos_base=base)
            names = {p.name for p in found}
            self.assertEqual(names, {"Claude", "Claude-3p"})
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_ignores_non_claude_dirs(self):
        base = Path(tempfile.mkdtemp())
        try:
            (base / "Claude").mkdir(parents=True)
            (base / "Claude" / "config.json").write_text("{}", encoding="utf-8")
            (base / "Spotify").mkdir(parents=True)  # not a Claude data dir
            found = session_linker.discover_claude_dirs(platform="darwin", macos_base=base)
            self.assertEqual([p.name for p in found], ["Claude"])
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_windows_branch_still_works_on_any_host(self):
        appdata = Path(tempfile.mkdtemp())
        try:
            d = appdata / "Claude"
            d.mkdir(parents=True)
            (d / "config.json").write_text("{}", encoding="utf-8")
            found = session_linker.discover_claude_dirs(appdata, None, platform="win32")
            self.assertIn("Claude", {p.name for p in found})
        finally:
            shutil.rmtree(appdata, ignore_errors=True)

    def test_module_init_resolves_macos_roots(self):
        base = Path(tempfile.mkdtemp())
        try:
            d = base / "Claude"
            (d / "claude-code-sessions").mkdir(parents=True)
            module = load_session_linker_macos(base)
            self.assertEqual(module.CLAUDE_DIR.name, "Claude")
            self.assertEqual(module.SESSIONS_DIR, d / "claude-code-sessions")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
